# Authentication API routes for user registration, login, and profile management

from fastapi import APIRouter, Depends, HTTPException, status

from app.db_handlers.base import UserDBHandler
from app.dependencies.auth import get_current_user
from app.models import User
from app.schemas import MessageResponse, Token, UserInfo, UserLogin, UserRegister
from app.utils.auth import create_access_token, get_password_hash, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED
)
async def register_user(
    user_data: UserRegister,
    user_db_handler: UserDBHandler = Depends(),
):
    """Register a new user with username and password."""
    # Password is automatically hashed using bcrypt before storage
    existing_user = await user_db_handler.get_by_attributes(username=user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    await user_db_handler.create(
        {"username": user_data.username, "hashed_password": hashed_password}
    )

    return MessageResponse(message="User registered successfully")


@router.post("/login", response_model=Token)
async def login_user(
    user_data: UserLogin,
    user_db_handler: UserDBHandler = Depends(),
):
    """Authenticate user and return JWT token for API access."""
    user = await user_db_handler.get_by_attributes(username=user_data.username)

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(data={"sub": user.username})

    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Retrieve current authenticated user's profile information."""
    return UserInfo(
        id=current_user.id,
        username=current_user.username,
        created_at=current_user.created_at.isoformat(),
    )
