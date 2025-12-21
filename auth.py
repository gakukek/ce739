from fastapi import Header, HTTPException
import os
import jwt
import httpx
from functools import lru_cache
from typing import Dict
import asyncio

# Get Clerk frontend API from environment or construct from publishable key
CLERK_PUBLISHABLE_KEY = os.getenv(
    "CLERK_PUBLISHABLE_KEY", 
    "pk_test_ZmFjdHVhbC1wbGF0eXB1cy01Ny5jbGVyay5hY2NvdW50cy5kZXYk"
)
CLERK_BACKEND_KEY = os.getenv("CLERK_SECRET_KEY")

# Extract the domain from publishable key
import base64
try:
    decoded_key = base64.b64decode(
        CLERK_PUBLISHABLE_KEY.replace("pk_test_", "").replace("pk_live_", "")
    ).decode('utf-8')
    clerk_domain = decoded_key.rstrip('$')
    CLERK_JWKS_URL = f"https://{clerk_domain}/.well-known/jwks.json"
except Exception as e:
    print(f"⚠️  Could not decode key, using fallback: {e}")
    CLERK_JWKS_URL = "https://factual-platypus-57.clerk.accounts.dev/.well-known/jwks.json"

print(f"🔑 Using Clerk JWKS URL: {CLERK_JWKS_URL}")

# Cache for JWKS - expires after 1 hour
_jwks_cache = {"data": None, "timestamp": 0}
CACHE_DURATION = 3600  # 1 hour in seconds

async def get_clerk_jwks() -> Dict:
    """Fetch and cache Clerk's public keys for JWT verification"""
    import time
    current_time = time.time()
    
    # Return cached data if still valid
    if _jwks_cache["data"] and (current_time - _jwks_cache["timestamp"]) < CACHE_DURATION:
        return _jwks_cache["data"]
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(CLERK_JWKS_URL, timeout=10.0)
            response.raise_for_status()
            jwks_data = response.json()
            
            # Update cache
            _jwks_cache["data"] = jwks_data
            _jwks_cache["timestamp"] = current_time
            
            return jwks_data
    except Exception as e:
        print(f"❌ Failed to fetch JWKS: {e}")
        # If cache exists, return it even if expired
        if _jwks_cache["data"]:
            print("⚠️  Using expired JWKS cache")
            return _jwks_cache["data"]
        raise HTTPException(
            status_code=503, 
            detail="Unable to fetch authentication keys"
        )

async def get_signing_key(token: str) -> str:
    """Get the public key for verifying the JWT"""
    try:
        jwks = await get_clerk_jwks()
        unverified_header = jwt.get_unverified_header(token)
        
        # Find the key with matching kid
        for key in jwks.get("keys", []):
            if key.get("kid") == unverified_header.get("kid"):
                # Convert JWK to PEM format
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
        
        raise HTTPException(
            status_code=401, 
            detail="Unable to find appropriate key"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting signing key: {e}")
        raise HTTPException(
            status_code=401, 
            detail=f"Key retrieval error: {str(e)}"
        )

async def get_current_user(authorization: str = Header(None)) -> str:
    if authorization == f"Bearer {CLERK_BACKEND_KEY}":
        return "system_simulator"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, 
            detail="Missing Authorization header"
        )

    token = authorization.split(" ")[1]

    try:
        # Get the signing key
        signing_key = await get_signing_key(token)
        
        # Decode and verify the token with RS256
        decoded = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            options={"verify_signature": True, "verify_exp": True}
        )
        
        user_id = decoded.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401, 
                detail="Invalid token: no user_id"
            )
        
        print(f"✅ Authenticated user: {user_id}")
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        print(f"❌ JWT error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Auth error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=401, 
            detail=f"Authentication failed: {str(e)}"
        )