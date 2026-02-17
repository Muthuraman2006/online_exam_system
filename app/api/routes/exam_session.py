from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import (
    ExamPaperResponse, SingleAnswerSave, AnswerSubmit, ResultResponse
)
from app.services.exam_engine_service import ExamEngineService
from app.api.deps.auth import StudentOnly

router = APIRouter(prefix="/exam-session", tags=["Student Exam Session"])


@router.post("/{exam_id}/start", response_model=ExamPaperResponse)
async def start_exam(
    exam_id: int,
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Start an exam. Generates unique randomized paper for student.
    Paper is generated ONCE and stored. Multiple calls return same paper.
    """
    service = ExamEngineService(db)
    return await service.start_exam(exam_id, current_user)


@router.get("/{exam_id}/paper", response_model=ExamPaperResponse)
async def get_paper(
    exam_id: int,
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Get current paper. Use this to RESUME on page refresh.
    Returns paper with updated server-side time remaining.
    Auto-submits if time has expired.
    """
    service = ExamEngineService(db)
    return await service.get_paper(exam_id, current_user)


@router.post("/{exam_id}/answer", status_code=status.HTTP_200_OK)
async def save_answer(
    exam_id: int,
    answer: SingleAnswerSave,
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Auto-save single answer. Call this on every answer change.
    Returns updated time remaining.
    Auto-submits if time has expired.
    """
    service = ExamEngineService(db)
    return await service.save_answer(exam_id, current_user, answer)


@router.post("/{exam_id}/answers", status_code=status.HTTP_200_OK)
async def save_all_answers(
    exam_id: int,
    answers: AnswerSubmit,
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Bulk save all answers. Use for periodic sync or before submit.
    """
    service = ExamEngineService(db)
    return await service.save_all_answers(exam_id, current_user, answers)


@router.post("/{exam_id}/submit", response_model=ResultResponse)
async def submit_exam(
    exam_id: int,
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Manually submit exam. Evaluates all answers and returns result.
    """
    service = ExamEngineService(db)
    return await service.submit_exam(exam_id, current_user)


@router.get("/{exam_id}/time", status_code=status.HTTP_200_OK)
async def get_remaining_time(
    exam_id: int,
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Get remaining time (server-side calculated).
    Use this for client-side timer sync.
    """
    service = ExamEngineService(db)
    paper = await service.get_paper(exam_id, current_user)
    return {
        "time_remaining_seconds": paper.time_remaining_seconds,
        "status": paper.status.value
    }


@router.post("/{exam_id}/violation", status_code=status.HTTP_200_OK)
async def log_violation(
    exam_id: int,
    violation: dict,
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Log exam violation (tab switch, focus lost, etc.).
    Used for proctoring/monitoring purposes.
    """
    # For now, just acknowledge the violation
    # In production, this would be stored in a violations table
    import logging
    logging.getLogger(__name__).warning(f"[VIOLATION] Student {current_user.id} in exam {exam_id}: {violation}")
    return {"status": "logged", "message": "Violation recorded"}
