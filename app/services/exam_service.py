from datetime import datetime, timedelta, timezone
from typing import Optional, List
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from fastapi import HTTPException, status

from app.models.models import (
    Exam, ExamAssignment, QuestionBank, User, RoleEnum,
    ExamStatusEnum, ExamSession, Result
)
from app.schemas.schemas import ExamCreate, ExamUpdate, ExamAssign

# Timezone constants
IST = ZoneInfo("Asia/Kolkata")


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is in UTC. Naive datetimes are assumed IST."""
    if dt is None:
        return dt
    if dt.tzinfo is None:
        # Naive datetime — assume IST input from frontend
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc)


class ExamService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: ExamCreate, user: User) -> Exam:
        # Verify question bank exists and has enough questions
        qbank_result = await self.db.execute(
            select(QuestionBank).where(QuestionBank.id == data.question_bank_id)
        )
        qbank = qbank_result.scalar_one_or_none()
        if not qbank:
            raise HTTPException(status_code=404, detail="Question bank not found")
        
        # Count available questions
        from app.models.models import Question
        count_result = await self.db.execute(
            select(func.count(Question.id)).where(
                Question.question_bank_id == data.question_bank_id,
                Question.is_active == True
            )
        )
        available_count = count_result.scalar() or 0
        
        if available_count < data.total_questions:
            raise HTTPException(
                status_code=400,
                detail=f"Question bank has only {available_count} questions, but {data.total_questions} required"
            )
        
        difficulty_dist = None
        if data.difficulty_distribution:
            difficulty_dist = data.difficulty_distribution.model_dump()
            total_in_dist = sum(difficulty_dist.values())
            if total_in_dist != data.total_questions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Difficulty distribution sum ({total_in_dist}) must equal total questions ({data.total_questions})"
                )
        
        # Convert times to UTC (naive inputs assumed IST)
        start_utc = ensure_utc(data.start_time)
        end_utc = ensure_utc(data.end_time)
        
        # Auto-determine initial status based on current time
        now = datetime.now(timezone.utc)
        if now >= end_utc:
            initial_status = ExamStatusEnum.COMPLETED
        elif now >= start_utc:
            initial_status = ExamStatusEnum.ACTIVE
        else:
            initial_status = ExamStatusEnum.SCHEDULED
        
        exam = Exam(
            title=data.title,
            description=data.description,
            question_bank_id=data.question_bank_id,
            total_questions=data.total_questions,
            duration_minutes=data.duration_minutes,
            total_marks=data.total_marks,
            passing_marks=data.passing_marks,
            start_time=start_utc,
            end_time=end_utc,
            shuffle_questions=data.shuffle_questions,
            shuffle_options=data.shuffle_options,
            show_result_immediately=data.show_result_immediately,
            allow_review=data.allow_review,
            max_attempts=data.max_attempts,
            difficulty_distribution=difficulty_dist,
            created_by=user.id,
            status=initial_status
        )
        
        self.db.add(exam)
        await self.db.flush()
        await self.db.refresh(exam)
        return exam

    async def get_by_id(self, exam_id: int) -> Optional[Exam]:
        result = await self.db.execute(select(Exam).where(Exam.id == exam_id))
        return result.scalar_one_or_none()

    async def _auto_update_exam_status(self, exam: Exam) -> Exam:
        """Auto-update exam status based on current UTC time."""
        now = datetime.now(timezone.utc)
        start = exam.start_time
        end = exam.end_time
        
        # Ensure timezone-aware comparison
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        
        changed = False
        if exam.status in (ExamStatusEnum.DRAFT, ExamStatusEnum.SCHEDULED):
            if now >= end:
                exam.status = ExamStatusEnum.COMPLETED
                changed = True
            elif now >= start:
                exam.status = ExamStatusEnum.ACTIVE
                changed = True
        elif exam.status == ExamStatusEnum.ACTIVE:
            if now >= end:
                exam.status = ExamStatusEnum.COMPLETED
                changed = True
        
        if changed:
            await self.db.flush()
        return exam

    async def get_all(
        self, 
        status_filter: Optional[ExamStatusEnum] = None,
        created_by: Optional[int] = None
    ) -> List[Exam]:
        query = select(Exam)
        if status_filter:
            query = query.where(Exam.status == status_filter)
        if created_by:
            query = query.where(Exam.created_by == created_by)
        result = await self.db.execute(query.order_by(Exam.created_at.desc()))
        exams = list(result.scalars().all())
        
        # Batch auto-update statuses — single flush at end
        now = datetime.now(timezone.utc)
        any_changed = False
        for exam in exams:
            start = exam.start_time
            end = exam.end_time
            if start and start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end and end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            
            if exam.status in (ExamStatusEnum.DRAFT, ExamStatusEnum.SCHEDULED):
                if now >= end:
                    exam.status = ExamStatusEnum.COMPLETED
                    any_changed = True
                elif now >= start:
                    exam.status = ExamStatusEnum.ACTIVE
                    any_changed = True
            elif exam.status == ExamStatusEnum.ACTIVE:
                if now >= end:
                    exam.status = ExamStatusEnum.COMPLETED
                    any_changed = True
        
        if any_changed:
            await self.db.flush()
        
        return exams

    async def update(self, exam_id: int, data: ExamUpdate) -> Exam:
        exam = await self.get_by_id(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
        
        # Don't allow updates on active/completed exams (except status changes)
        if exam.status in [ExamStatusEnum.ACTIVE, ExamStatusEnum.COMPLETED]:
            if data.model_dump(exclude_unset=True, exclude={'status'}):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot modify exam details while active or completed"
                )
        
        update_data = data.model_dump(exclude_unset=True)
        if 'difficulty_distribution' in update_data and update_data['difficulty_distribution']:
            update_data['difficulty_distribution'] = update_data['difficulty_distribution'].model_dump() if hasattr(update_data['difficulty_distribution'], 'model_dump') else update_data['difficulty_distribution']
        
        # Ensure start_time and end_time are converted to UTC
        if 'start_time' in update_data and update_data['start_time']:
            update_data['start_time'] = ensure_utc(update_data['start_time'])
        if 'end_time' in update_data and update_data['end_time']:
            update_data['end_time'] = ensure_utc(update_data['end_time'])
        
        for field, value in update_data.items():
            setattr(exam, field, value)
        
        await self.db.flush()
        await self.db.refresh(exam)
        return exam

    async def delete(self, exam_id: int) -> bool:
        exam = await self.get_by_id(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
        
        # Admin can delete any exam; cascade removes related sessions/results/assignments
        await self.db.delete(exam)
        await self.db.flush()
        return True

    async def assign_students(self, exam_id: int, data: ExamAssign) -> int:
        exam = await self.get_by_id(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
        
        # BATCH verify all students exist and are students (single query)
        users_result = await self.db.execute(
            select(User.id).where(
                User.id.in_(data.student_ids),
                User.role == RoleEnum.STUDENT
            )
        )
        valid_student_ids = set(users_result.scalars().all())
        
        invalid = set(data.student_ids) - valid_student_ids
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Users {list(invalid)} not found or not students"
            )
        
        # BATCH check existing assignments (single query)
        existing_result = await self.db.execute(
            select(ExamAssignment.student_id).where(
                ExamAssignment.exam_id == exam_id,
                ExamAssignment.student_id.in_(data.student_ids)
            )
        )
        already_assigned = set(existing_result.scalars().all())
        
        # Create only new assignments
        assigned_count = 0
        for student_id in data.student_ids:
            if student_id not in already_assigned:
                self.db.add(ExamAssignment(exam_id=exam_id, student_id=student_id))
                assigned_count += 1
        
        if assigned_count > 0:
            await self.db.flush()
        return assigned_count

    async def get_assigned_students(self, exam_id: int) -> List[User]:
        result = await self.db.execute(
            select(User).join(ExamAssignment).where(ExamAssignment.exam_id == exam_id)
        )
        return list(result.scalars().all())

    async def get_exams_for_student(self, student_id: int) -> List[Exam]:
        """Get exams assigned to student - auto-updates statuses."""
        result = await self.db.execute(
            select(Exam)
            .join(ExamAssignment)
            .where(
                ExamAssignment.student_id == student_id,
                Exam.status.notin_([ExamStatusEnum.CANCELLED]),
            )
            .order_by(Exam.start_time)
        )
        exams = list(result.scalars().all())
        
        # Auto-update statuses
        for exam in exams:
            await self._auto_update_exam_status(exam)
        
        return exams

    async def get_student_exam_assignments(self, student_id: int):
        """Get exam assignments for a student + ALL active exams within time range.
        Combines explicitly assigned exams with any public active exams so students
        always see available exams without requiring manual assignment.
        
        Debug: logs current UTC/IST time and exam time windows for verification.
        """
        import logging
        log = logging.getLogger("exam_visibility")
        
        now = datetime.now(timezone.utc)
        now_ist = now.astimezone(IST)
        log.warning(
            f"[EXAM VISIBILITY DEBUG] current_utc={now.isoformat()} | "
            f"current_ist={now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        
        # ---- Query 1: Explicitly assigned exams (any status) ----
        assign_result = await self.db.execute(
            select(ExamAssignment.exam_id)
            .where(ExamAssignment.student_id == student_id)
        )
        assigned_exam_ids = set(assign_result.scalars().all())
        
        # ---- Query 2: ALL exams that are ACTIVE/SCHEDULED and within time range ----
        # This ensures students see exams even without explicit assignment
        active_result = await self.db.execute(
            select(Exam)
            .where(
                Exam.status.in_([ExamStatusEnum.ACTIVE, ExamStatusEnum.SCHEDULED]),
            )
            .order_by(Exam.start_time.desc())
        )
        all_exams = list(active_result.scalars().all())
        
        # Also fetch assigned exams that may be completed/draft (student's history)
        if assigned_exam_ids:
            assigned_result = await self.db.execute(
                select(Exam)
                .where(
                    Exam.id.in_(assigned_exam_ids),
                    ~Exam.id.in_([e.id for e in all_exams])  # avoid duplicates
                )
            )
            extra_assigned = list(assigned_result.scalars().all())
            all_exams.extend(extra_assigned)
        
        # Auto-update statuses
        any_changed = False
        for exam in all_exams:
            start = exam.start_time
            end = exam.end_time
            if start and start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end and end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            
            old_status = exam.status
            if exam.status in (ExamStatusEnum.DRAFT, ExamStatusEnum.SCHEDULED):
                if now >= end:
                    exam.status = ExamStatusEnum.COMPLETED
                    any_changed = True
                elif now >= start:
                    exam.status = ExamStatusEnum.ACTIVE
                    any_changed = True
            elif exam.status == ExamStatusEnum.ACTIVE:
                if now >= end:
                    exam.status = ExamStatusEnum.COMPLETED
                    any_changed = True
            
            # Debug log each exam
            log.warning(
                f"[EXAM] id={exam.id} title='{exam.title}' "
                f"status={old_status.value}->{exam.status.value} "
                f"start={start.isoformat() if start else 'None'} "
                f"end={end.isoformat() if end else 'None'} "
                f"visible={exam.status == ExamStatusEnum.ACTIVE and now >= start and now <= end}"
            )
        
        if any_changed:
            await self.db.flush()
        
        # ---- Query 3: Get completed exam IDs for this student ----
        completed_result = await self.db.execute(
            select(Result.exam_id)
            .where(Result.student_id == student_id)
        )
        completed_exam_ids = set(completed_result.scalars().all())
        
        # ---- Build response ----
        seen_ids = set()
        result_list = []
        for exam in all_exams:
            if exam.id in seen_ids:
                continue
            seen_ids.add(exam.id)
            
            result_list.append({
                "id": exam.id,
                "exam": {
                    "id": exam.id,
                    "title": exam.title,
                    "description": exam.description,
                    "question_bank_id": exam.question_bank_id,
                    "total_questions": exam.total_questions,
                    "duration_minutes": exam.duration_minutes,
                    "total_marks": exam.total_marks,
                    "passing_marks": exam.passing_marks,
                    "start_time": exam.start_time.isoformat() if exam.start_time else None,
                    "end_time": exam.end_time.isoformat() if exam.end_time else None,
                    "status": exam.status.value if exam.status else "SCHEDULED",
                    "shuffle_questions": exam.shuffle_questions,
                    "shuffle_options": exam.shuffle_options,
                    "show_result_immediately": exam.show_result_immediately,
                    "allow_review": exam.allow_review,
                    "max_attempts": exam.max_attempts,
                    "difficulty_distribution": exam.difficulty_distribution,
                    "created_by": exam.created_by,
                    "created_at": exam.created_at.isoformat() if exam.created_at else None
                },
                "is_completed": exam.id in completed_exam_ids,
                "is_assigned": exam.id in assigned_exam_ids,
                "assigned_at": None
            })
        
        log.warning(
            f"[EXAM VISIBILITY] student_id={student_id} | "
            f"total_found={len(result_list)} | "
            f"active={sum(1 for r in result_list if r['exam']['status'] == 'ACTIVE')} | "
            f"completed_by_student={len(completed_exam_ids)}"
        )
        
        return result_list

    async def get_available_exams_for_student(self) -> List[Exam]:
        """Get all ACTIVE exams within the current time window.
        No assignment required — any student can see these.
        Uses: status == ACTIVE AND start_time <= now AND end_time >= now
        """
        import logging
        log = logging.getLogger("exam_visibility")

        now = datetime.now(timezone.utc)
        now_ist = now.astimezone(IST)
        log.warning(
            f"[STUDENT AVAILABLE] current_utc={now.isoformat()} | "
            f"current_ist={now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

        result = await self.db.execute(
            select(Exam).where(
                Exam.status == ExamStatusEnum.ACTIVE,
                Exam.start_time <= now,
                Exam.end_time >= now
            ).order_by(Exam.start_time)
        )
        exams = list(result.scalars().all())

        # Also auto-update any SCHEDULED exams that should now be ACTIVE
        scheduled_result = await self.db.execute(
            select(Exam).where(
                Exam.status == ExamStatusEnum.SCHEDULED,
                Exam.start_time <= now,
                Exam.end_time >= now
            )
        )
        scheduled_exams = list(scheduled_result.scalars().all())
        for exam in scheduled_exams:
            exam.status = ExamStatusEnum.ACTIVE
            exams.append(exam)

        if scheduled_exams:
            await self.db.flush()

        log.warning(
            f"[STUDENT AVAILABLE] found={len(exams)} active exams within time window"
        )
        for e in exams:
            log.warning(
                f"  exam_id={e.id} title='{e.title}' "
                f"start={e.start_time.isoformat()} end={e.end_time.isoformat()}"
            )

        return exams

    async def activate_exam(self, exam_id: int) -> Exam:
        exam = await self.get_by_id(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
        
        if exam.status != ExamStatusEnum.SCHEDULED:
            raise HTTPException(
                status_code=400,
                detail="Only scheduled exams can be activated"
            )
        
        exam.status = ExamStatusEnum.ACTIVE
        
        # Count assigned students (don't rely on noload relationship)
        count_result = await self.db.execute(
            select(func.count(ExamAssignment.id)).where(ExamAssignment.exam_id == exam_id)
        )
        total_students = count_result.scalar() or 0
        
        # Create exam session for monitoring
        session = ExamSession(
            exam_id=exam_id,
            total_students=total_students
        )
        self.db.add(session)
        
        await self.db.flush()
        await self.db.refresh(exam)
        return exam

    async def schedule_exam(self, exam_id: int) -> Exam:
        exam = await self.get_by_id(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
        
        if exam.status != ExamStatusEnum.DRAFT:
            raise HTTPException(
                status_code=400,
                detail="Only draft exams can be scheduled"
            )
        
        # Check if there are assigned students
        assigned = await self.get_assigned_students(exam_id)
        if not assigned:
            raise HTTPException(
                status_code=400,
                detail="Cannot schedule exam without assigned students"
            )
        
        exam.status = ExamStatusEnum.SCHEDULED
        await self.db.flush()
        await self.db.refresh(exam)
        return exam
