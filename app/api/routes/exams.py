from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import ExamStatusEnum, User
from app.schemas.schemas import (
    ExamCreate, ExamUpdate, ExamResponse, ExamAssign,
    UserResponse, ResultResponse, ResultSummary
)
from app.services.exam_service import ExamService
from app.services.result_service import ResultService
from app.api.deps.auth import AdminOnly, InvigilatorOrAdmin, StudentOnly, AnyAuthenticated

router = APIRouter(prefix="/exams", tags=["Exams"])


# ============ ADMIN EXAM MANAGEMENT ============

@router.post("", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
async def create_exam(
    data: ExamCreate,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Create a new exam (admin only)."""
    service = ExamService(db)
    exam = await service.create(data, current_user)
    
    return ExamResponse(
        id=exam.id,
        title=exam.title,
        description=exam.description,
        question_bank_id=exam.question_bank_id,
        total_questions=exam.total_questions,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        passing_marks=exam.passing_marks,
        start_time=exam.start_time,
        end_time=exam.end_time,
        status=exam.status,
        shuffle_questions=exam.shuffle_questions,
        shuffle_options=exam.shuffle_options,
        show_result_immediately=exam.show_result_immediately,
        allow_review=exam.allow_review,
        max_attempts=exam.max_attempts,
        difficulty_distribution=exam.difficulty_distribution,
        created_by=exam.created_by,
        created_at=exam.created_at
    )


@router.get("", response_model=List[ExamResponse])
async def list_exams(
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Optional[ExamStatusEnum] = None
):
    """List all exams (admin/invigilator)."""
    service = ExamService(db)
    exams = await service.get_all(status_filter=status_filter)
    
    return [
        ExamResponse(
            id=e.id,
            title=e.title,
            description=e.description,
            question_bank_id=e.question_bank_id,
            total_questions=e.total_questions,
            duration_minutes=e.duration_minutes,
            total_marks=e.total_marks,
            passing_marks=e.passing_marks,
            start_time=e.start_time,
            end_time=e.end_time,
            status=e.status,
            shuffle_questions=e.shuffle_questions,
            shuffle_options=e.shuffle_options,
            show_result_immediately=e.show_result_immediately,
            allow_review=e.allow_review,
            max_attempts=e.max_attempts,
            difficulty_distribution=e.difficulty_distribution,
            created_by=e.created_by,
            created_at=e.created_at
        )
        for e in exams
    ]


@router.get("/my-exams")
async def get_my_exams(
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get exam assignments for current student with completion status."""
    service = ExamService(db)
    return await service.get_student_exam_assignments(current_user.id)


@router.get("/student/available", response_model=List[ExamResponse])
async def get_student_available_exams(
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get all currently active exams within the time window for students.
    No assignment required — filters by status=ACTIVE + start_time <= now <= end_time."""
    service = ExamService(db)
    exams = await service.get_available_exams_for_student()
    
    return [
        ExamResponse(
            id=e.id,
            title=e.title,
            description=e.description,
            question_bank_id=e.question_bank_id,
            total_questions=e.total_questions,
            duration_minutes=e.duration_minutes,
            total_marks=e.total_marks,
            passing_marks=e.passing_marks,
            start_time=e.start_time,
            end_time=e.end_time,
            status=e.status,
            shuffle_questions=e.shuffle_questions,
            shuffle_options=e.shuffle_options,
            show_result_immediately=e.show_result_immediately,
            allow_review=e.allow_review,
            max_attempts=e.max_attempts,
            difficulty_distribution=e.difficulty_distribution,
            created_by=e.created_by,
            created_at=e.created_at
        )
        for e in exams
    ]


@router.get("/available", response_model=List[ExamResponse])
async def list_available_exams(
    current_user: StudentOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Legacy endpoint — redirects to student/available logic."""
    service = ExamService(db)
    exams = await service.get_available_exams_for_student()
    
    return [
        ExamResponse(
            id=e.id,
            title=e.title,
            description=e.description,
            question_bank_id=e.question_bank_id,
            total_questions=e.total_questions,
            duration_minutes=e.duration_minutes,
            total_marks=e.total_marks,
            passing_marks=e.passing_marks,
            start_time=e.start_time,
            end_time=e.end_time,
            status=e.status,
            shuffle_questions=e.shuffle_questions,
            shuffle_options=e.shuffle_options,
            show_result_immediately=e.show_result_immediately,
            allow_review=e.allow_review,
            max_attempts=e.max_attempts,
            difficulty_distribution=e.difficulty_distribution,
            created_by=e.created_by,
            created_at=e.created_at
        )
        for e in exams
    ]


@router.get("/{exam_id}", response_model=ExamResponse)
async def get_exam(
    exam_id: int,
    current_user: AnyAuthenticated,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get exam details."""
    service = ExamService(db)
    exam = await service.get_by_id(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    
    return ExamResponse(
        id=exam.id,
        title=exam.title,
        description=exam.description,
        question_bank_id=exam.question_bank_id,
        total_questions=exam.total_questions,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        passing_marks=exam.passing_marks,
        start_time=exam.start_time,
        end_time=exam.end_time,
        status=exam.status,
        shuffle_questions=exam.shuffle_questions,
        shuffle_options=exam.shuffle_options,
        show_result_immediately=exam.show_result_immediately,
        allow_review=exam.allow_review,
        max_attempts=exam.max_attempts,
        difficulty_distribution=exam.difficulty_distribution,
        created_by=exam.created_by,
        created_at=exam.created_at
    )


@router.patch("/{exam_id}", response_model=ExamResponse)
async def update_exam(
    exam_id: int,
    data: ExamUpdate,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Update exam (admin only)."""
    service = ExamService(db)
    exam = await service.update(exam_id, data)
    
    return ExamResponse(
        id=exam.id,
        title=exam.title,
        description=exam.description,
        question_bank_id=exam.question_bank_id,
        total_questions=exam.total_questions,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        passing_marks=exam.passing_marks,
        start_time=exam.start_time,
        end_time=exam.end_time,
        status=exam.status,
        shuffle_questions=exam.shuffle_questions,
        shuffle_options=exam.shuffle_options,
        show_result_immediately=exam.show_result_immediately,
        allow_review=exam.allow_review,
        max_attempts=exam.max_attempts,
        difficulty_distribution=exam.difficulty_distribution,
        created_by=exam.created_by,
        created_at=exam.created_at
    )


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(
    exam_id: int,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Delete exam (admin only, draft/cancelled only)."""
    service = ExamService(db)
    await service.delete(exam_id)
    return None


# ============ EXAM LIFECYCLE ============

@router.post("/{exam_id}/schedule", response_model=ExamResponse)
async def schedule_exam(
    exam_id: int,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Schedule a draft exam (admin only)."""
    service = ExamService(db)
    exam = await service.schedule_exam(exam_id)
    
    return ExamResponse(
        id=exam.id,
        title=exam.title,
        description=exam.description,
        question_bank_id=exam.question_bank_id,
        total_questions=exam.total_questions,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        passing_marks=exam.passing_marks,
        start_time=exam.start_time,
        end_time=exam.end_time,
        status=exam.status,
        shuffle_questions=exam.shuffle_questions,
        shuffle_options=exam.shuffle_options,
        show_result_immediately=exam.show_result_immediately,
        allow_review=exam.allow_review,
        max_attempts=exam.max_attempts,
        difficulty_distribution=exam.difficulty_distribution,
        created_by=exam.created_by,
        created_at=exam.created_at
    )


@router.post("/{exam_id}/activate", response_model=ExamResponse)
async def activate_exam(
    exam_id: int,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Activate a scheduled exam (admin only)."""
    service = ExamService(db)
    exam = await service.activate_exam(exam_id)
    
    return ExamResponse(
        id=exam.id,
        title=exam.title,
        description=exam.description,
        question_bank_id=exam.question_bank_id,
        total_questions=exam.total_questions,
        duration_minutes=exam.duration_minutes,
        total_marks=exam.total_marks,
        passing_marks=exam.passing_marks,
        start_time=exam.start_time,
        end_time=exam.end_time,
        status=exam.status,
        shuffle_questions=exam.shuffle_questions,
        shuffle_options=exam.shuffle_options,
        show_result_immediately=exam.show_result_immediately,
        allow_review=exam.allow_review,
        max_attempts=exam.max_attempts,
        difficulty_distribution=exam.difficulty_distribution,
        created_by=exam.created_by,
        created_at=exam.created_at
    )


# ============ STUDENT ASSIGNMENT ============

@router.post("/{exam_id}/assign", status_code=status.HTTP_200_OK)
async def assign_students(
    exam_id: int,
    data: ExamAssign,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Assign students to an exam (admin only)."""
    service = ExamService(db)
    count = await service.assign_students(exam_id, data)
    return {"message": f"Assigned {count} students to exam", "assigned_count": count}


@router.get("/{exam_id}/students", response_model=List[UserResponse])
async def get_assigned_students(
    exam_id: int,
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get students assigned to an exam."""
    service = ExamService(db)
    students = await service.get_assigned_students(exam_id)
    return students


# ============ RESULTS ============

@router.get("/{exam_id}/results", response_model=List[ResultResponse])
async def get_exam_results(
    exam_id: int,
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get all results for an exam (admin/invigilator)."""
    service = ResultService(db)
    return await service.get_exam_results(exam_id)


@router.get("/{exam_id}/results/summary", response_model=ResultSummary)
async def get_exam_results_summary(
    exam_id: int,
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get summary statistics for an exam (admin/invigilator)."""
    service = ResultService(db)
    return await service.get_exam_summary(exam_id)
