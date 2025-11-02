# auth.py
from fastapi import Depends, Header, HTTPException
from clerk_backend_api import Clerk, AuthenticateRequestOptions, authenticate_request
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User

clerk = Clerk(api_key="YOUR_CLERK_SECRET_KEY")

async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db)
) -> int:
    """
    Validates Clerk token, ensures user exists in DB,
    returns internal DB user.id (int).
    """

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization")

    token = authorization.split(" ")[1]

    try:
        auth_state = authenticate_request(
            clerk,
            token=token,
            options=AuthenticateRequestOptions(jwt_key=None)
        )

        if not auth_state.is_signed_in:
            raise HTTPException(status_code=401, detail="User not signed in")

        clerk_user_id = auth_state.user_id

        # Find local user
        result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
        user = result.scalar_one_or_none()

        # Auto-create local user on first login
        if not user:
            user = User(clerk_user_id=clerk_user_id)
            db.add(user)
            await db.commit()
            await db.refresh(user)

        return user.id  # internal DB id

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Clerk token: {e}")
