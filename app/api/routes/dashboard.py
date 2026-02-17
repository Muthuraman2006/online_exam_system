from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, literal_column, text

from app.core.database import get_db
from app.models.models import (
    QuestionBank, Question, Exam, User, 
    ExamStatusEnum, RoleEnum
)
from app.api.deps.auth import AdminOnly
from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_question_banks: int
    total_questions: int
    total_exams: int
    active_exams: int
    total_students: int
    total_admins: int


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get dashboard statistics — single round-trip with scalar subqueries."""
    
    result = await db.execute(
        select(
            select(func.count(QuestionBank.id)).where(QuestionBank.is_active == True).correlate(None).scalar_subquery().label("qb"),
            select(func.count(Question.id)).where(Question.is_active == True).correlate(None).scalar_subquery().label("q"),
            select(func.count(Exam.id)).correlate(None).scalar_subquery().label("exams"),
            select(func.count(Exam.id)).where(Exam.status == ExamStatusEnum.ACTIVE).correlate(None).scalar_subquery().label("active"),
            select(func.count(User.id)).where(User.role == RoleEnum.STUDENT, User.is_active == True).correlate(None).scalar_subquery().label("students"),
            select(func.count(User.id)).where(User.role == RoleEnum.ADMIN, User.is_active == True).correlate(None).scalar_subquery().label("admins"),
        )
    )
    row = result.one()
    
    return DashboardStats(
        total_question_banks=row[0] or 0,
        total_questions=row[1] or 0,
        total_exams=row[2] or 0,
        active_exams=row[3] or 0,
        total_students=row[4] or 0,
        total_admins=row[5] or 0
    )
