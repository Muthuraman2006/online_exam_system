from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from app.models.models import (
    Result, Exam, User, StudentExamPaper, ExamSession, SessionFlag,
    StudentResponse, PaperStatusEnum, RoleEnum
)
from app.schemas.schemas import (
    ResultResponse, ResultSummary, ExamSessionResponse, StudentProgress, FlagCreate, FlagResponse
)


def _build_result_response(result: Result, exam_title: str, student_name: str, student_email: str = None) -> ResultResponse:
    """Pure function — no DB call."""
    return ResultResponse(
        id=result.id,
        exam_id=result.exam_id,
        exam_title=exam_title,
        student_id=result.student_id,
        student_name=student_name,
        student_email=student_email,
        total_questions=result.total_questions,
        attempted=result.attempted,
        correct=result.correct,
        wrong=result.wrong,
        total_marks=result.total_marks,
        marks_obtained=result.marks_obtained,
        percentage=result.percentage,
        is_passed=result.is_passed,
        rank=result.rank,
        category_wise_score=result.category_wise_score,
        difficulty_wise_score=result.difficulty_wise_score,
        evaluated_at=result.evaluated_at
    )


class ResultService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_student_results(self, student_id: int) -> List[ResultResponse]:
        """Get all results for a student — single query with JOINs."""
        query = (
            select(Result, Exam.title, User.full_name, User.email)
            .join(Exam, Result.exam_id == Exam.id)
            .join(User, Result.student_id == User.id)
            .where(Result.student_id == student_id)
            .order_by(Result.evaluated_at.desc())
        )
        rows = await self.db.execute(query)
        return [
            _build_result_response(result, exam_title, student_name, student_email)
            for result, exam_title, student_name, student_email in rows.all()
        ]

    async def get_exam_results(self, exam_id: int) -> List[ResultResponse]:
        """Get all results for an exam — single query with JOINs."""
        query = (
            select(Result, Exam.title, User.full_name, User.email)
            .join(Exam, Result.exam_id == Exam.id)
            .join(User, Result.student_id == User.id)
            .where(Result.exam_id == exam_id)
            .order_by(Result.rank.asc())
        )
        rows = await self.db.execute(query)
        return [
            _build_result_response(result, exam_title, student_name, student_email)
            for result, exam_title, student_name, student_email in rows.all()
        ]

    async def get_exam_summary(self, exam_id: int) -> ResultSummary:
        """Get summary statistics for an exam — optimized aggregation."""
        exam_q = await self.db.execute(select(Exam).where(Exam.id == exam_id))
        exam = exam_q.scalar_one_or_none()
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")

        # Single aggregation query
        from app.models.models import ExamAssignment
        stats_q = await self.db.execute(
            select(
                func.count(Result.id),
                func.sum(Result.marks_obtained),
                func.max(Result.marks_obtained),
                func.min(Result.marks_obtained),
                func.count(Result.id).filter(Result.is_passed == True),
            ).where(Result.exam_id == exam_id)
        )
        row = stats_q.one()
        count, total_sum, highest, lowest, passed = row

        assigned_q = await self.db.execute(
            select(func.count(ExamAssignment.id)).where(ExamAssignment.exam_id == exam_id)
        )
        total_students = assigned_q.scalar() or 0

        return ResultSummary(
            exam_id=exam_id,
            exam_title=exam.title,
            total_students=total_students,
            students_appeared=count or 0,
            students_passed=passed or 0,
            average_score=round((total_sum or 0) / count, 2) if count else 0.0,
            highest_score=highest or 0.0,
            lowest_score=lowest or 0.0
        )

    async def get_result_by_id(self, result_id: int, user: User) -> ResultResponse:
        """Get specific result — single query with JOINs."""
        query = (
            select(Result, Exam.title, User.full_name, User.email)
            .join(Exam, Result.exam_id == Exam.id)
            .join(User, Result.student_id == User.id)
            .where(Result.id == result_id)
        )
        row = (await self.db.execute(query)).one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Result not found")

        result, exam_title, student_name, student_email = row
        if user.role == RoleEnum.STUDENT and result.student_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied")

        return _build_result_response(result, exam_title, student_name, student_email)


class SessionService:
    """Service for invigilator exam session monitoring"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_sessions(self) -> List[ExamSessionResponse]:
        """Get all active exam sessions — single JOIN query."""
        query = (
            select(ExamSession, Exam.title)
            .join(Exam, ExamSession.exam_id == Exam.id)
            .where(ExamSession.is_active == True)
            .order_by(ExamSession.started_at.desc())
        )
        rows = await self.db.execute(query)
        return [
            ExamSessionResponse(
                id=session.id,
                exam_id=session.exam_id,
                exam_title=exam_title,
                started_at=session.started_at,
                ended_at=session.ended_at,
                total_students=session.total_students,
                students_started=session.students_started,
                students_submitted=session.students_submitted,
                is_active=session.is_active
            )
            for session, exam_title in rows.all()
        ]

    async def get_session_students(self, session_id: int) -> List[StudentProgress]:
        """Get progress of all students in a session — single JOIN + subquery."""
        session_query = await self.db.execute(
            select(ExamSession).where(ExamSession.id == session_id)
        )
        session = session_query.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Subquery: count attempted questions per paper
        attempted_subq = (
            select(
                StudentResponse.paper_id,
                func.count(StudentResponse.id).label("attempted")
            )
            .where(StudentResponse.selected_answer.isnot(None))
            .group_by(StudentResponse.paper_id)
            .subquery()
        )

        # Single JOIN: papers + users + attempted counts
        query = (
            select(
                StudentExamPaper,
                User.full_name,
                func.coalesce(attempted_subq.c.attempted, 0).label("attempted")
            )
            .join(User, StudentExamPaper.student_id == User.id)
            .outerjoin(attempted_subq, StudentExamPaper.id == attempted_subq.c.paper_id)
            .where(StudentExamPaper.exam_id == session.exam_id)
        )
        rows = await self.db.execute(query)
        return [
            StudentProgress(
                student_id=paper.student_id,
                student_name=student_name,
                status=paper.status,
                questions_attempted=attempted,
                time_remaining_seconds=paper.time_remaining_seconds,
                last_activity_at=paper.last_activity_at
            )
            for paper, student_name, attempted in rows.all()
        ]

    async def flag_student(self, session_id: int, data: FlagCreate, flagged_by: User) -> FlagResponse:
        """Flag a student for suspicious activity"""
        session_query = await self.db.execute(
            select(ExamSession).where(ExamSession.id == session_id)
        )
        session = session_query.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        flag = SessionFlag(
            session_id=session_id,
            student_id=data.student_id,
            flagged_by=flagged_by.id,
            flag_type=data.flag_type,
            description=data.description
        )
        
        self.db.add(flag)
        await self.db.flush()
        await self.db.refresh(flag)
        
        return FlagResponse(
            id=flag.id,
            session_id=flag.session_id,
            student_id=flag.student_id,
            flagged_by=flag.flagged_by,
            flag_type=flag.flag_type,
            description=flag.description,
            created_at=flag.created_at
        )

    async def get_session_flags(self, session_id: int) -> List[FlagResponse]:
        """Get all flags for a session"""
        flags_query = await self.db.execute(
            select(SessionFlag).where(SessionFlag.session_id == session_id).order_by(SessionFlag.created_at.desc())
        )
        flags = list(flags_query.scalars().all())
        
        return [
            FlagResponse(
                id=f.id,
                session_id=f.session_id,
                student_id=f.student_id,
                flagged_by=f.flagged_by,
                flag_type=f.flag_type,
                description=f.description,
                created_at=f.created_at
            )
            for f in flags
        ]
