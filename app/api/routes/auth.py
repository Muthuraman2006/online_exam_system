from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import User, RoleEnum
from app.schemas.schemas import (
    UserCreate, UserUpdate, UserResponse, TokenWithUser
)
from app.services.auth_service import AuthService
from app.api.deps.auth import AdminOnly, AnyAuthenticated

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Register a new STUDENT account (public endpoint).
    Admin signup is disabled - all registrations create student accounts.
    """
    service = AuthService(db)
    user = await service.register(user_data)
    return user


@router.post("/login", response_model=TokenWithUser)
async def login(
    db: Annotated[AsyncSession, Depends(get_db)],
    username: str = Form(..., description="Email address"),
    password: str = Form(..., description="Password")
):
    """
    Authenticate and get JWT token with user info.
    Accepts form data with 'username' (email) and 'password'.
    Role is determined from database - not from request.
    """
    service = AuthService(db)
    return await service.login(email=username, password=password)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: AnyAuthenticated):
    """
    Get current authenticated user's info.
    """
    return current_user


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)],
    role: Optional[RoleEnum] = None
):
    """
    List all users (admin only). Optionally filter by role.
    """
    service = AuthService(db)
    return await service.get_all_users(role=role)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: UserUpdate,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Update user profile/status (admin only). Accepts JSON body with
    optional fields: full_name, email, is_active.
    """
    service = AuthService(db)
    return await service.update_user(user_id, data)


@router.patch("/users/{user_id}/status", response_model=UserResponse)
async def update_user_status(
    user_id: int,
    is_active: bool,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Activate/deactivate user account (admin only). Legacy endpoint.
    """
    service = AuthService(db)
    return await service.update_user_status(user_id, is_active)
