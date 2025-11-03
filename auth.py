from fastapi import Header, HTTPException
from clerk_backend_api import Clerk, AuthenticateRequestOptions, ClerkError
import os

clerk = Clerk()

async def get_current_user(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.split(" ")[1]

    try:
        auth_state = clerk.authenticate_request(
            token=token,
            options=AuthenticateRequestOptions()
        )

        if not auth_state.is_authenticated:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        return auth_state.user_id

    except ClerkError as e:
        raise HTTPException(status_code=401, detail=f"Clerk auth failed: {str(e)}")
