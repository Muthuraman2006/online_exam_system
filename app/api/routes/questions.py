from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import RoleEnum
from app.schemas.schemas import (
    QuestionBankCreate, QuestionBankUpdate, QuestionBankResponse,
    QuestionCreate, QuestionUpdate, QuestionResponse, QuestionWithAnswer
)
from app.services.question_service import QuestionBankService, QuestionService
from app.api.deps.auth import AdminOnly, InvigilatorOrAdmin

router = APIRouter(prefix="/question-banks", tags=["Question Banks"])


# ============ QUESTION BANK ENDPOINTS ============

@router.post("", response_model=QuestionBankResponse, status_code=status.HTTP_201_CREATED)
async def create_question_bank(
    data: QuestionBankCreate,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Create a new question bank (admin only)."""
    service = QuestionBankService(db)
    qbank = await service.create(data, current_user)
    question_count = await service.get_question_count(qbank.id)
    
    return QuestionBankResponse(
        id=qbank.id,
        name=qbank.name,
        description=qbank.description,
        subject=qbank.subject,
        created_by=qbank.created_by,
        is_active=qbank.is_active,
        created_at=qbank.created_at,
        question_count=question_count
    )


@router.get("", response_model=List[QuestionBankResponse])
async def list_question_banks(
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    subject: Optional[str] = None,
    active_only: bool = True
):
    """List all question banks with counts (optimized single query)."""
    service = QuestionBankService(db)
    banks_with_counts = await service.get_all_with_counts(subject=subject, active_only=active_only)
    
    return [
        QuestionBankResponse(
            id=item['bank'].id,
            name=item['bank'].name,
            description=item['bank'].description,
            subject=item['bank'].subject,
            created_by=item['bank'].created_by,
            is_active=item['bank'].is_active,
            created_at=item['bank'].created_at,
            question_count=item['question_count']
        )
        for item in banks_with_counts
    ]


@router.get("/{qbank_id}", response_model=QuestionBankResponse)
async def get_question_bank(
    qbank_id: int,
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get a specific question bank."""
    service = QuestionBankService(db)
    qbank = await service.get_by_id(qbank_id)
    if not qbank:
        raise HTTPException(status_code=404, detail="Question bank not found")
    
    count = await service.get_question_count(qbank.id)
    return QuestionBankResponse(
        id=qbank.id,
        name=qbank.name,
        description=qbank.description,
        subject=qbank.subject,
        created_by=qbank.created_by,
        is_active=qbank.is_active,
        created_at=qbank.created_at,
        question_count=count
    )


@router.patch("/{qbank_id}", response_model=QuestionBankResponse)
async def update_question_bank(
    qbank_id: int,
    data: QuestionBankUpdate,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Update a question bank (admin only)."""
    service = QuestionBankService(db)
    qbank = await service.update(qbank_id, data)
    count = await service.get_question_count(qbank.id)
    
    return QuestionBankResponse(
        id=qbank.id,
        name=qbank.name,
        description=qbank.description,
        subject=qbank.subject,
        created_by=qbank.created_by,
        is_active=qbank.is_active,
        created_at=qbank.created_at,
        question_count=count
    )


@router.delete("/{qbank_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question_bank(
    qbank_id: int,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Delete a question bank (admin only)."""
    service = QuestionBankService(db)
    await service.delete(qbank_id)
    return None


# ============ QUESTION ENDPOINTS ============

@router.post("/{qbank_id}/questions", response_model=QuestionWithAnswer, status_code=status.HTTP_201_CREATED)
async def create_question(
    qbank_id: int,
    data: QuestionCreate,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Add a question to a question bank (admin only)."""
    if data.question_bank_id != qbank_id:
        data.question_bank_id = qbank_id
    
    service = QuestionService(db)
    question = await service.create(data)
    
    return QuestionWithAnswer(
        id=question.id,
        question_bank_id=question.question_bank_id,
        question_text=question.question_text,
        question_type=question.question_type,
        difficulty=question.difficulty,
        options=question.options,
        correct_answer=question.correct_answer,
        marks=question.marks,
        negative_marks=question.negative_marks,
        explanation=question.explanation,
        tags=question.tags,
        is_active=question.is_active,
        created_at=question.created_at
    )


@router.post("/{qbank_id}/questions/bulk", response_model=List[QuestionWithAnswer], status_code=status.HTTP_201_CREATED)
async def create_questions_bulk(
    qbank_id: int,
    questions: List[QuestionCreate],
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Bulk add questions to a question bank (admin only)."""
    for q in questions:
        q.question_bank_id = qbank_id
    
    service = QuestionService(db)
    created = await service.create_bulk(questions)
    
    return [
        QuestionWithAnswer(
            id=q.id,
            question_bank_id=q.question_bank_id,
            question_text=q.question_text,
            question_type=q.question_type,
            difficulty=q.difficulty,
            options=q.options,
            correct_answer=q.correct_answer,
            marks=q.marks,
            negative_marks=q.negative_marks,
            explanation=q.explanation,
            tags=q.tags,
            is_active=q.is_active,
            created_at=q.created_at
        )
        for q in created
    ]


@router.get("/{qbank_id}/questions", response_model=List[QuestionWithAnswer])
async def list_questions(
    qbank_id: int,
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    difficulty: Optional[str] = None,
    question_type: Optional[str] = None,
    active_only: bool = True
):
    """List all questions in a question bank."""
    service = QuestionService(db)
    questions = await service.get_by_bank(
        qbank_id,
        difficulty=difficulty,
        question_type=question_type,
        active_only=active_only
    )
    
    return [
        QuestionWithAnswer(
            id=q.id,
            question_bank_id=q.question_bank_id,
            question_text=q.question_text,
            question_type=q.question_type,
            difficulty=q.difficulty,
            options=q.options,
            correct_answer=q.correct_answer,
            marks=q.marks,
            negative_marks=q.negative_marks,
            explanation=q.explanation,
            tags=q.tags,
            is_active=q.is_active,
            created_at=q.created_at
        )
        for q in questions
    ]


questions_router = APIRouter(prefix="/questions", tags=["Questions"])


@questions_router.get("/{question_id}", response_model=QuestionWithAnswer)
async def get_question(
    question_id: int,
    current_user: InvigilatorOrAdmin,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get a specific question."""
    service = QuestionService(db)
    question = await service.get_by_id(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    return QuestionWithAnswer(
        id=question.id,
        question_bank_id=question.question_bank_id,
        question_text=question.question_text,
        question_type=question.question_type,
        difficulty=question.difficulty,
        options=question.options,
        correct_answer=question.correct_answer,
        marks=question.marks,
        negative_marks=question.negative_marks,
        explanation=question.explanation,
        tags=question.tags,
        is_active=question.is_active,
        created_at=question.created_at
    )


@questions_router.patch("/{question_id}", response_model=QuestionWithAnswer)
async def update_question(
    question_id: int,
    data: QuestionUpdate,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Update a question (admin only)."""
    service = QuestionService(db)
    question = await service.update(question_id, data)
    
    return QuestionWithAnswer(
        id=question.id,
        question_bank_id=question.question_bank_id,
        question_text=question.question_text,
        question_type=question.question_type,
        difficulty=question.difficulty,
        options=question.options,
        correct_answer=question.correct_answer,
        marks=question.marks,
        negative_marks=question.negative_marks,
        explanation=question.explanation,
        tags=question.tags,
        is_active=question.is_active,
        created_at=question.created_at
    )


@questions_router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: int,
    current_user: AdminOnly,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Delete a question (admin only)."""
    service = QuestionService(db)
    await service.delete(question_id)
    return None
