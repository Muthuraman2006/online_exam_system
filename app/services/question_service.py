from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from fastapi import HTTPException, status

from app.models.models import QuestionBank, Question, User, Exam, StudentExamPaper, StudentResponse, Result, ExamAssignment, ExamSession
from app.schemas.schemas import (
    QuestionBankCreate, QuestionBankUpdate, QuestionBankResponse,
    QuestionCreate, QuestionUpdate, QuestionResponse
)


class QuestionBankService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: QuestionBankCreate, user: User) -> QuestionBank:
        qbank = QuestionBank(
            name=data.name,
            description=data.description,
            subject=data.subject,
            created_by=user.id
        )
        self.db.add(qbank)
        await self.db.flush()
        await self.db.refresh(qbank)
        return qbank

    async def get_by_id(self, qbank_id: int) -> Optional[QuestionBank]:
        result = await self.db.execute(
            select(QuestionBank).where(QuestionBank.id == qbank_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, subject: Optional[str] = None, active_only: bool = True) -> List[QuestionBank]:
        query = select(QuestionBank)
        if active_only:
            query = query.where(QuestionBank.is_active == True)
        if subject:
            query = query.where(QuestionBank.subject == subject)
        result = await self.db.execute(query.order_by(QuestionBank.created_at.desc()))
        return list(result.scalars().all())

    async def get_all_with_counts(self, subject: Optional[str] = None, active_only: bool = True) -> List[dict]:
        """Get all question banks with question counts in a single query (avoids N+1)."""
        count_subq = (
            select(
                Question.question_bank_id,
                func.count(Question.id).label('question_count')
            )
            .where(Question.is_active == True)
            .group_by(Question.question_bank_id)
            .subquery()
        )
        
        query = (
            select(QuestionBank, func.coalesce(count_subq.c.question_count, 0).label('question_count'))
            .outerjoin(count_subq, QuestionBank.id == count_subq.c.question_bank_id)
        )
        
        if active_only:
            query = query.where(QuestionBank.is_active == True)
        if subject:
            query = query.where(QuestionBank.subject == subject)
        
        result = await self.db.execute(query.order_by(QuestionBank.created_at.desc()))
        rows = result.all()
        
        return [
            {
                'bank': row[0],
                'question_count': row[1]
            }
            for row in rows
        ]

    async def update(self, qbank_id: int, data: QuestionBankUpdate) -> QuestionBank:
        qbank = await self.get_by_id(qbank_id)
        if not qbank:
            raise HTTPException(status_code=404, detail="Question bank not found")
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(qbank, field, value)
        
        await self.db.flush()
        await self.db.refresh(qbank)
        return qbank

    async def delete(self, qbank_id: int) -> bool:
        qbank = await self.get_by_id(qbank_id)
        if not qbank:
            raise HTTPException(status_code=404, detail="Question bank not found")
        
        # Get all exams linked to this question bank
        exam_result = await self.db.execute(
            select(Exam.id).where(Exam.question_bank_id == qbank_id)
        )
        exam_ids = [row[0] for row in exam_result.fetchall()]
        
        if exam_ids:
            # Get all papers for these exams
            paper_result = await self.db.execute(
                select(StudentExamPaper.id).where(StudentExamPaper.exam_id.in_(exam_ids))
            )
            paper_ids = [row[0] for row in paper_result.fetchall()]
            
            # Delete in order to respect foreign key constraints
            if paper_ids:
                await self.db.execute(
                    delete(StudentResponse).where(StudentResponse.paper_id.in_(paper_ids))
                )
                await self.db.execute(
                    delete(Result).where(Result.paper_id.in_(paper_ids))
                )
                await self.db.execute(
                    delete(StudentExamPaper).where(StudentExamPaper.id.in_(paper_ids))
                )
            
            # Delete exam sessions (cascade will handle session_flags)
            await self.db.execute(
                delete(ExamSession).where(ExamSession.exam_id.in_(exam_ids))
            )
            
            # Delete exam assignments
            await self.db.execute(
                delete(ExamAssignment).where(ExamAssignment.exam_id.in_(exam_ids))
            )
            
            # Delete exams
            await self.db.execute(
                delete(Exam).where(Exam.id.in_(exam_ids))
            )
        
        # Delete questions (should cascade but being explicit)
        await self.db.execute(
            delete(Question).where(Question.question_bank_id == qbank_id)
        )
        
        # Finally delete the question bank
        await self.db.delete(qbank)
        await self.db.flush()
        return True

    async def get_question_count(self, qbank_id: int) -> int:
        result = await self.db.execute(
            select(func.count(Question.id)).where(
                Question.question_bank_id == qbank_id,
                Question.is_active == True
            )
        )
        return result.scalar() or 0


class QuestionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: QuestionCreate) -> Question:
        # Verify question bank exists
        qbank_result = await self.db.execute(
            select(QuestionBank).where(QuestionBank.id == data.question_bank_id)
        )
        if not qbank_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Question bank not found")
        
        question = Question(
            question_bank_id=data.question_bank_id,
            question_text=data.question_text,
            question_type=data.question_type,
            difficulty=data.difficulty,
            options=data.options,
            correct_answer=data.correct_answer,
            marks=data.marks,
            negative_marks=data.negative_marks,
            explanation=data.explanation,
            tags=data.tags
        )
        self.db.add(question)
        await self.db.flush()
        await self.db.refresh(question)
        return question

    async def create_bulk(self, questions: List[QuestionCreate]) -> List[Question]:
        created = []
        for q_data in questions:
            question = await self.create(q_data)
            created.append(question)
        return created

    async def get_by_id(self, question_id: int) -> Optional[Question]:
        result = await self.db.execute(
            select(Question).where(Question.id == question_id)
        )
        return result.scalar_one_or_none()

    async def get_by_bank(
        self, 
        qbank_id: int, 
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        active_only: bool = True
    ) -> List[Question]:
        query = select(Question).where(Question.question_bank_id == qbank_id)
        
        if active_only:
            query = query.where(Question.is_active == True)
        if difficulty:
            query = query.where(Question.difficulty == difficulty)
        if question_type:
            query = query.where(Question.question_type == question_type)
        
        result = await self.db.execute(query.order_by(Question.created_at.desc()))
        return list(result.scalars().all())

    async def update(self, question_id: int, data: QuestionUpdate) -> Question:
        question = await self.get_by_id(question_id)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(question, field, value)
        
        await self.db.flush()
        await self.db.refresh(question)
        return question

    async def delete(self, question_id: int) -> bool:
        question = await self.get_by_id(question_id)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        await self.db.delete(question)
        await self.db.flush()
        return True
