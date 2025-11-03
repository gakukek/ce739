from fastapi import Header, HTTPException
import os
import jwt
import requests
from functools import lru_cache
from typing import Dict

# Get Clerk frontend API from environment or construct from publishable key
CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZmFjdHVhbC1wbGF0eXB1cy01Ny5jbGVyay5hY2NvdW50cy5kZXYk")

# Extract the domain from publishable key
# Format: pk_test_<base64>
# The base64 decodes to something like: factual-platypus-57.clerk.accounts.dev$
import base64
try:
    decoded_key = base64.b64decode(CLERK_PUBLISHABLE_KEY.replace("pk_test_", "").replace("pk_live_", "")).decode('utf-8')
    clerk_domain = decoded_key.rstrip('$')
    CLERK_JWKS_URL = f"https://{clerk_domain}/.well-known/jwks.json"
except:
    # Fallback - extract from your key
    CLERK_JWKS_URL = "https://factual-platypus-57.clerk.accounts.dev/.well-known/jwks.json"

print(f"🔑 Using Clerk JWKS URL: {CLERK_JWKS_URL}")

@lru_cache(maxsize=1)
def get_clerk_jwks() -> Dict:
    """Fetch and cache Clerk's public keys for JWT verification"""
    try:
        response = requests.get(CLERK_JWKS_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Failed to fetch JWKS: {e}")
        raise

def get_signing_key(token: str) -> str:
    """Get the public key for verifying the JWT"""
    jwks = get_clerk_jwks()
    unverified_header = jwt.get_unverified_header(token)
    
    # Find the key with matching kid
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            # Convert JWK to PEM format
            return jwt.algorithms.RSAAlgorithm.from_jwk(key)
    
    raise HTTPException(status_code=401, detail="Unable to find appropriate key")

async def get_current_user(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.split(" ")[1]

    try:
        # Get the signing key
        signing_key = get_signing_key(token)
        
        # Decode and verify the token with RS256
        decoded = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            options={"verify_signature": True, "verify_exp": True}
        )
        
        user_id = decoded.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user_id")
        
        print(f"✅ Authenticated user: {user_id}")
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        print(f"❌ JWT error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        print(f"❌ Auth error: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")