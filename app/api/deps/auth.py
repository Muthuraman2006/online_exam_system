from typing import Annotated, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import time

from app.core.database import get_db
from app.core.security import decode_token
from app.models.models import User, RoleEnum
from app.schemas.schemas import TokenData

security = HTTPBearer()

# In-memory user cache — avoids DB round-trip on every authenticated request.
# Safe for single-server local dev. TTL ensures stale data expires.
_user_cache: dict[int, tuple[User, float]] = {}
_USER_CACHE_TTL = 300  # 5 minutes


def _get_cached_user(user_id: int) -> Optional[User]:
    entry = _user_cache.get(user_id)
    if entry and (time.time() - entry[1]) < _USER_CACHE_TTL:
        return entry[0]
    if entry:
        del _user_cache[user_id]
    return None


def _cache_user(user: User):
    _user_cache[user.id] = (user, time.time())


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    user_id_int = int(user_id)
    
    # Check cache first — eliminates a DB round-trip (~400-600ms to Supabase)
    cached = _get_cached_user(user_id_int)
    if cached and cached.is_active:
        return cached
    
    result = await db.execute(select(User).where(User.id == user_id_int))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    
    _cache_user(user)
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    return current_user


def require_roles(*roles: RoleEnum):
    """Dependency factory for role-based access control"""
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)]
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in roles]}",
            )
        return current_user
    return role_checker


# Pre-defined role dependencies
AdminOnly = Annotated[User, Depends(require_roles(RoleEnum.ADMIN))]
InvigilatorOrAdmin = Annotated[User, Depends(require_roles(RoleEnum.ADMIN, RoleEnum.INVIGILATOR))]
StudentOnly = Annotated[User, Depends(require_roles(RoleEnum.STUDENT))]
AnyAuthenticated = Annotated[User, Depends(get_current_active_user)]
