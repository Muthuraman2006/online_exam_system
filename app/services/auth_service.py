from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.models import User, RoleEnum
from app.schemas.schemas import UserCreate, UserUpdate, UserLogin, Token, TokenWithUser, UserResponse, ADMIN_EMAIL
from app.core.security import verify_password_async, get_password_hash, create_access_token


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, user_data: UserCreate) -> User:
        """
        Register a new STUDENT account.
        Admin signup is completely disabled - role is always STUDENT.
        """
        # Check if email exists
        result = await self.db.execute(select(User).where(User.email == user_data.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # CRITICAL: Block anyone trying to register with admin email
        if user_data.email.lower() == ADMIN_EMAIL.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This email cannot be used for registration"
            )
        
        # Always create as STUDENT - role is enforced by backend, not frontend
        user = User(
            email=user_data.email,
            hashed_password=get_password_hash(user_data.password),
            full_name=user_data.full_name,
            role=RoleEnum.STUDENT  # HARDCODED - no role from frontend
        )
        
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def login(self, email: str, password: str) -> TokenWithUser:
        """
        Authenticate user and return JWT token with user info.
        Role is determined from database, not from request.
        """
        # Check if user exists
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email"
            )
        
        # Verify password (async — offloaded to thread pool)
        if not await verify_password_async(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )
        
        # Check if account is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated"
            )
        
        # Create JWT token with role from database
        access_token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role.value
            }
        )
        
        # Return token WITH user data for frontend
        return TokenWithUser(
            access_token=access_token,
            user=UserResponse.model_validate(user)
        )

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_all_users(self, role: Optional[RoleEnum] = None) -> list[User]:
        query = select(User)
        if role:
            query = query.where(User.role == role)
        result = await self.db.execute(query.order_by(User.created_at.desc()))
        return list(result.scalars().all())

    async def update_user_status(self, user_id: int, is_active: bool) -> User:
        user = await self.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user.is_active = is_active
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update_user(self, user_id: int, data: UserUpdate) -> User:
        user = await self.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if data.email is not None and data.email != user.email:
            existing = await self.db.execute(select(User).where(User.email == data.email))
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Email already in use")
            user.email = data.email
        
        if data.full_name is not None:
            user.full_name = data.full_name
        
        if data.is_active is not None:
            user.is_active = data.is_active
        
        await self.db.flush()
        await self.db.refresh(user)
        return user
