from fastapi import Header, HTTPException
from clerk_backend_api import Clerk
import os

# Initialize Clerk with secret key
clerk = Clerk(bearer_auth=os.getenv("CLERK_SECRET_KEY"))

async def get_current_user(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.split(" ")[1]

    try:
        # Verify the session token
        jwt_claims = clerk.verify_token(token)
        
        if not jwt_claims or not jwt_claims.get("sub"):
            raise HTTPException(status_code=401, detail="Invalid token")

        return jwt_claims["sub"]  # This is the user_id

    except Exception as e:
        print(f"❌ Auth error: {e}")  # For debugging
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")