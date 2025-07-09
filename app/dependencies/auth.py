"""
Authentication dependencies for FastAPI route protection.
"""


from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_app_db
from app.db_handlers.base import UserDBHandler
from app.models import User
from app.utils.auth import extract_username_from_token

# HTTP Bearer token extraction
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_app_db),
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    """
    # Extract username from token
    username = extract_username_from_token(credentials.credentials)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Find user in database using UserDBHandler
    user_handler = UserDBHandler()
    user = await user_handler.get_user_by_username(username, db=db)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials
    | None = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_app_db),
) -> User | None:
    """
    Optional dependency to get the current authenticated user.
    Returns None if no valid token is provided instead of raising an exception.
    """
    if credentials is None:
        return None

    try:
        # Extract username from token
        username = extract_username_from_token(credentials.credentials)
        if username is None:
            return None

        # Find user in database using UserDBHandler
        user_handler = UserDBHandler()
        user = await user_handler.get_user_by_username(username, db=db)

        return user
    except Exception:
        return None
