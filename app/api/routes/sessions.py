from typing import Annotated, List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import (
    ExamSessionResponse, StudentProgress, FlagCreate, FlagResponse
)
from app.services.result_service import SessionService
from app.api.deps.auth import InvigilatorOrAdmin

router = APIRouter(prefix="/sessions", tags=["Invigilator Sessions"])


@router.get("/active", response_model=List[ExamSessionResponse])
async def get_active_sessions(
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get all active exam sessions for monitoring."""
    service = SessionService(db)
    return await service.get_active_sessions()


@router.get("/{session_id}/students", response_model=List[StudentProgress])
async def get_session_students(
    session_id: int,
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get progress of all students in a session."""
    service = SessionService(db)
    return await service.get_session_students(session_id)


@router.post("/{session_id}/flag", response_model=FlagResponse, status_code=201)
async def flag_student(
    session_id: int,
    data: FlagCreate,
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Flag a student for suspicious activity."""
    service = SessionService(db)
    return await service.flag_student(session_id, data, current_user)


@router.get("/{session_id}/flags", response_model=List[FlagResponse])
async def get_session_flags(
    session_id: int,
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get all flags for a session."""
    service = SessionService(db)
    return await service.get_session_flags(session_id)
