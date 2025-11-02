import os
from fastapi import Header, HTTPException, Depends
from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from dotenv import load_dotenv

load_dotenv()

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
if not CLERK_SECRET_KEY:
    raise RuntimeError("CLERK_SECRET_KEY environment variable is required")

clerk = Clerk(bearer_auth=CLERK_SECRET_KEY)

async def get_current_user(authorization: str = Header(None)) -> str:
    """
    Validates Clerk session token using clerk-backend-api SDK.
    Returns the Clerk user_id if valid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ")[1]

    try:
        auth_opts = AuthenticateRequestOptions(
            jwt_key=None,  # uses Clerk's default JWKS
            authorized_parties=None
        )
        auth_state = authenticate_request(
            clerk, 
            token=token,
            options=auth_opts
        )
        if not auth_state.is_signed_in:
            raise HTTPException(status_code=401, detail="User is not signed in")

        user_id = auth_state.user_id
        return user_id

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Clerk token: {e}")
