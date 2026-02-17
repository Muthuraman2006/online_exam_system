from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from jose import jwt, JWTError
import asyncio
import bcrypt
from app.core.config import settings


def _verify_password_sync(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode('utf-8')[:72]
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Sync wrapper — used by auth service. Safe because FastAPI runs
    sync route deps in threadpool automatically."""
    return _verify_password_sync(plain_password, hashed_password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Async version — offloads bcrypt to thread pool so it doesn't block the event loop."""
    return await asyncio.to_thread(_verify_password_sync, plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    # Truncate password to 72 bytes (bcrypt limitation)
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None
