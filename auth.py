from fastapi import Header, HTTPException
import os
import jwt
import requests
from functools import lru_cache

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
if not CLERK_SECRET_KEY:
    raise RuntimeError("CLERK_SECRET_KEY environment variable is not set")

# Cache the JWKS for 1 hour
@lru_cache(maxsize=1)
def get_clerk_jwks():
    # Extract the instance from the secret key or use your Clerk domain
    # For testing, we'll use the secret key directly
    return None

async def get_current_user(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.split(" ")[1]

    try:
        # Decode the JWT without verification first to get the kid
        unverified = jwt.decode(token, options={"verify_signature": False})
        
        # For development with secret key, decode and verify
        decoded = jwt.decode(
            token,
            CLERK_SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_signature": True}
        )
        
        user_id = decoded.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user_id")
        
        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        print(f"❌ JWT error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        print(f"❌ Auth error: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")