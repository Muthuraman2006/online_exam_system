import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

from app.models.models import (
    Exam, Question, StudentExamPaper, StudentResponse, Result,
    ExamAssignment, ExamSession, User, RoleEnum,
    ExamStatusEnum, PaperStatusEnum, DifficultyEnum, QuestionTypeEnum
)
from app.schemas.schemas import (
    ExamPaperResponse, PaperQuestion, SingleAnswerSave, AnswerSubmit, ResultResponse
)
from app.core.config import settings


class ExamEngineService:
    """Core exam engine handling paper generation, timer, answers, and evaluation"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ PAPER GENERATION ============
    
    async def generate_paper(self, exam_id: int, student: User) -> StudentExamPaper:
        """
        Generate unique randomized paper for student.
        
        CRITICAL: ONE-PAPER-PER-STUDENT GUARANTEE
        -----------------------------------------
        Each student gets exactly ONE paper per exam (per attempt).
        If paper exists, return it (idempotent). Never regenerate.
        This ensures:
        - Same questions on refresh/resume
        - Randomization happens ONCE at first access
        - No way to "reset" and get different questions
        """
        
        # Get exam
        exam = await self._get_exam(exam_id)
        
        # Validate exam is available
        await self._validate_exam_available(exam, student)
        
        # CRITICAL: Return existing paper if already generated (idempotent)
        # This guarantees same questions on every access
        existing_paper = await self._get_existing_paper(exam_id, student.id)
        if existing_paper:
            if existing_paper.status in [PaperStatusEnum.SUBMITTED, PaperStatusEnum.AUTO_SUBMITTED, PaperStatusEnum.EVALUATED]:
                # Check if more attempts are allowed
                attempt_count = await self._get_attempt_count(exam_id, student.id)
                if attempt_count >= exam.max_attempts:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Maximum attempts ({exam.max_attempts}) reached"
                    )
                # Allow new attempt — fall through to create new paper
            else:
                return existing_paper
        
        # Check attempt count
        attempt_count = await self._get_attempt_count(exam_id, student.id)
        if attempt_count >= exam.max_attempts:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum attempts ({exam.max_attempts}) reached"
            )
        
        # RANDOMIZATION STEP 1: Select random subset from question bank
        # Uses random.sample() internally - each student gets different questions
        questions = await self._select_questions(exam)
        
        # RANDOMIZATION STEP 2: Shuffle question ORDER (if enabled)
        # Different students see questions in different sequence
        if exam.shuffle_questions:
            random.shuffle(questions)
        
        # RANDOMIZATION STEP 3: Shuffle OPTIONS within each question (if enabled)
        # Options A,B,C,D appear in random order per student
        paper_data = self._build_paper_data(questions, exam.shuffle_options)
        
        # Create paper
        paper = StudentExamPaper(
            exam_id=exam_id,
            student_id=student.id,
            paper_data=paper_data,
            status=PaperStatusEnum.NOT_STARTED,
            attempt_number=attempt_count + 1,
            time_remaining_seconds=exam.duration_minutes * 60
        )
        
        self.db.add(paper)
        await self.db.flush()
        
        # Create empty response records for all questions
        for q_data in paper_data["questions"]:
            response = StudentResponse(
                paper_id=paper.id,
                question_id=q_data["question_id"]
            )
            self.db.add(response)
        
        await self.db.flush()
        await self.db.refresh(paper)
        
        # Update session stats
        await self._update_session_stats(exam_id, "started")
        
        return paper

    async def _select_questions(self, exam: Exam) -> List[Question]:
        """Select questions based on difficulty distribution or random"""
        
        base_query = select(Question).where(
            Question.question_bank_id == exam.question_bank_id,
            Question.is_active == True
        )
        
        if exam.difficulty_distribution:
            questions = []
            for difficulty, count in exam.difficulty_distribution.items():
                if count > 0:
                    diff_query = base_query.where(Question.difficulty == difficulty)
                    result = await self.db.execute(diff_query)
                    diff_questions = list(result.scalars().all())
                    
                    if len(diff_questions) < count:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Not enough {difficulty} questions available"
                        )
                    
                    questions.extend(random.sample(diff_questions, count))
            return questions
        else:
            result = await self.db.execute(base_query)
            all_questions = list(result.scalars().all())
            
            if len(all_questions) < exam.total_questions:
                raise HTTPException(
                    status_code=400,
                    detail="Not enough questions available"
                )
            
            return random.sample(all_questions, exam.total_questions)

    def _build_paper_data(self, questions: List[Question], shuffle_options: bool) -> Dict:
        """Build paper data with question order and shuffled options"""
        paper_questions = []
        
        for idx, q in enumerate(questions):
            q_data = {
                "question_id": q.id,
                "sequence": idx + 1,
                "question_text": q.question_text,
                "question_type": q.question_type.value,
                "marks": q.marks,
                "negative_marks": q.negative_marks
            }
            
            if q.options:
                option_keys = list(q.options.keys())
                if shuffle_options:
                    random.shuffle(option_keys)
                q_data["options_order"] = option_keys
                q_data["options"] = {k: q.options[k] for k in option_keys}
            
            paper_questions.append(q_data)
        
        return {"questions": paper_questions}

    # ============ START EXAM ============
    
    async def start_exam(self, exam_id: int, student: User) -> ExamPaperResponse:
        """Start exam and return paper with server-side timer"""
        
        paper = await self.generate_paper(exam_id, student)
        exam = await self._get_exam(exam_id)
        
        # Start timer if not started
        if paper.status == PaperStatusEnum.NOT_STARTED:
            paper.status = PaperStatusEnum.IN_PROGRESS
            paper.started_at = datetime.now(timezone.utc)
            paper.time_remaining_seconds = exam.duration_minutes * 60
            paper.last_activity_at = datetime.now(timezone.utc)
            await self.db.flush()
            await self.db.refresh(paper)
        
        return await self._build_paper_response(paper, exam)

    # ============ GET PAPER (RESUME) ============
    
    async def get_paper(self, exam_id: int, student: User) -> ExamPaperResponse:
        """
        Get existing paper - enables RESUME on page refresh.
        
        RESUME LOGIC:
        - Returns the SAME paper generated earlier (same questions)
        - Recalculates time remaining based on server clock (tamper-proof)
        - Auto-submits if time has expired during absence
        """
        
        # Fetch existing paper - will be same questions as originally generated
        paper = await self._get_existing_paper(exam_id, student.id)
        if not paper:
            raise HTTPException(status_code=404, detail="No paper found. Start the exam first.")
        
        if paper.status in [PaperStatusEnum.SUBMITTED, PaperStatusEnum.AUTO_SUBMITTED, PaperStatusEnum.EVALUATED]:
            raise HTTPException(status_code=400, detail="Exam already submitted")
        
        exam = await self._get_exam(exam_id)
        
        # SERVER-SIDE TIMER: Recalculate from (now - started_at)
        # Prevents client-side time manipulation
        paper = await self._update_time_remaining(paper, exam=exam)
        
        # Check if time expired
        if paper.time_remaining_seconds <= 0:
            return await self.auto_submit(exam_id, student)
        
        return await self._build_paper_response(paper, exam)

    # ============ AUTO-SAVE ANSWER ============
    
    async def save_answer(self, exam_id: int, student: User, answer_data: SingleAnswerSave) -> Dict:
        """Auto-save single answer"""
        paper = await self._get_active_paper(exam_id, student.id)
        paper = await self._update_time_remaining(paper)  # exam loaded only if needed
        
        if paper.time_remaining_seconds <= 0:
            await self.auto_submit(exam_id, student)
            return {"status": "auto_submitted", "message": "Time expired"}
        
        # Find response record
        response = await self._get_response(paper.id, answer_data.question_id)
        if not response:
            raise HTTPException(status_code=404, detail="Question not in paper")
        
        # Update response
        response.selected_answer = answer_data.selected_answer
        response.is_marked_for_review = answer_data.is_marked_for_review
        response.answered_at = datetime.now(timezone.utc)
        
        paper.last_activity_at = datetime.now(timezone.utc)
        
        await self.db.flush()
        
        return {
            "status": "saved",
            "question_id": answer_data.question_id,
            "time_remaining_seconds": paper.time_remaining_seconds
        }

    async def save_all_answers(self, exam_id: int, student: User, answers: AnswerSubmit) -> Dict:
        """Bulk save answers"""
        
        paper = await self._get_active_paper(exam_id, student.id)
        paper = await self._update_time_remaining(paper)  # exam loaded only if needed
        
        if paper.time_remaining_seconds <= 0:
            await self.auto_submit(exam_id, student)
            return {"status": "auto_submitted", "message": "Time expired"}
        
        saved_count = 0
        for ans in answers.answers:
            response = await self._get_response(paper.id, ans.question_id)
            if response:
                response.selected_answer = ans.selected_answer
                response.is_marked_for_review = ans.is_marked_for_review
                response.answered_at = datetime.now(timezone.utc)
                saved_count += 1
        
        paper.last_activity_at = datetime.now(timezone.utc)
        await self.db.flush()
        
        return {
            "status": "saved",
            "saved_count": saved_count,
            "time_remaining_seconds": paper.time_remaining_seconds
        }

    # ============ MANUAL SUBMIT ============
    
    async def submit_exam(self, exam_id: int, student: User) -> ResultResponse:
        """Manual exam submission"""
        
        paper = await self._get_active_paper(exam_id, student.id)
        paper.status = PaperStatusEnum.SUBMITTED
        paper.submitted_at = datetime.now(timezone.utc)
        
        await self.db.flush()
        
        # Evaluate and generate result
        result = await self._evaluate_paper(paper)
        
        # Update session stats
        await self._update_session_stats(exam_id, "submitted")
        
        return result

    # ============ AUTO-SUBMIT ============
    
    async def auto_submit(self, exam_id: int, student: User) -> ResultResponse:
        """Auto-submit when time expires"""
        
        paper = await self._get_existing_paper(exam_id, student.id)
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        
        if paper.status in [PaperStatusEnum.SUBMITTED, PaperStatusEnum.AUTO_SUBMITTED, PaperStatusEnum.EVALUATED]:
            # Already submitted, return existing result
            result = await self._get_result(paper.id)
            if result:
                return await self._build_result_response(result)
            raise HTTPException(status_code=400, detail="Exam already submitted")
        
        paper.status = PaperStatusEnum.AUTO_SUBMITTED
        paper.submitted_at = datetime.now(timezone.utc)
        paper.time_remaining_seconds = 0
        
        await self.db.flush()
        
        result = await self._evaluate_paper(paper)
        await self._update_session_stats(exam_id, "submitted")
        
        return result

    # ============ EVALUATION ENGINE ============
    
    async def _evaluate_paper(self, paper: StudentExamPaper) -> ResultResponse:
        """Evaluate all answers and generate result — batch-loads questions (no N+1)."""
        
        exam = await self._get_exam(paper.exam_id)
        student = await self._get_user(paper.student_id)
        
        # Get all responses for this paper
        responses_result = await self.db.execute(
            select(StudentResponse).where(StudentResponse.paper_id == paper.id)
        )
        responses = list(responses_result.scalars().all())
        
        # BATCH LOAD all questions at once (eliminates N+1)
        question_ids = [r.question_id for r in responses]
        if question_ids:
            questions_result = await self.db.execute(
                select(Question).where(Question.id.in_(question_ids))
            )
            questions_map = {q.id: q for q in questions_result.scalars().all()}
        else:
            questions_map = {}
        
        total_marks = 0.0
        correct_count = 0
        wrong_count = 0
        attempted = 0
        
        difficulty_scores = {d.value: {"correct": 0, "total": 0, "marks": 0.0} for d in DifficultyEnum}
        
        for response in responses:
            question = questions_map.get(response.question_id)
            if not question:
                continue
            
            if response.selected_answer:
                attempted += 1
                is_correct = self._check_answer(question, response.selected_answer)
                response.is_correct = is_correct
                
                if is_correct:
                    response.marks_obtained = question.marks
                    total_marks += question.marks
                    correct_count += 1
                else:
                    response.marks_obtained = -question.negative_marks
                    total_marks -= question.negative_marks
                    wrong_count += 1
                
                # Track difficulty breakdown
                diff = question.difficulty.value
                difficulty_scores[diff]["total"] += 1
                if is_correct:
                    difficulty_scores[diff]["correct"] += 1
                    difficulty_scores[diff]["marks"] += question.marks
            else:
                response.is_correct = None
                response.marks_obtained = 0.0
        
        await self.db.flush()
        
        # Calculate percentage
        percentage = (total_marks / exam.total_marks * 100) if exam.total_marks > 0 else 0
        is_passed = total_marks >= exam.passing_marks
        
        # Create result
        result = Result(
            exam_id=paper.exam_id,
            student_id=paper.student_id,
            paper_id=paper.id,
            total_questions=exam.total_questions,
            attempted=attempted,
            correct=correct_count,
            wrong=wrong_count,
            total_marks=exam.total_marks,
            marks_obtained=max(0, total_marks),  # Don't go negative
            percentage=round(percentage, 2),
            is_passed=is_passed,
            difficulty_wise_score=difficulty_scores
        )
        
        self.db.add(result)
        
        # Update paper status
        paper.status = PaperStatusEnum.EVALUATED
        
        await self.db.flush()
        await self.db.refresh(result)
        
        # Calculate rank
        await self._calculate_ranks(paper.exam_id)
        await self.db.refresh(result)
        
        return await self._build_result_response(result)

    def _check_answer(self, question: Question, selected_answer: str) -> bool:
        """Check if answer is correct"""
        correct = question.correct_answer.strip().lower()
        selected = selected_answer.strip().lower()
        return correct == selected

    async def _calculate_ranks(self, exam_id: int):
        """Calculate ranks for all results in exam"""
        results_query = await self.db.execute(
            select(Result)
            .where(Result.exam_id == exam_id)
            .order_by(Result.marks_obtained.desc(), Result.evaluated_at.asc())
        )
        results = list(results_query.scalars().all())
        
        for rank, result in enumerate(results, 1):
            result.rank = rank
        
        await self.db.flush()

    # ============ HELPER METHODS ============
    
    async def _get_exam(self, exam_id: int) -> Exam:
        result = await self.db.execute(select(Exam).where(Exam.id == exam_id))
        exam = result.scalar_one_or_none()
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
        return exam

    async def _validate_exam_available(self, exam: Exam, student: User):
        """Validate exam is available for student - auto-updates status."""
        now = datetime.now(timezone.utc)
        
        # Auto-activate exam if within time window but status is stale
        start = exam.start_time
        end = exam.end_time
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        
        if exam.status in (ExamStatusEnum.DRAFT, ExamStatusEnum.SCHEDULED):
            if now >= start and now < end:
                exam.status = ExamStatusEnum.ACTIVE
                await self.db.flush()
            elif now >= end:
                exam.status = ExamStatusEnum.COMPLETED
                await self.db.flush()
        elif exam.status == ExamStatusEnum.ACTIVE:
            if now >= end:
                exam.status = ExamStatusEnum.COMPLETED
                await self.db.flush()
        
        if exam.status not in [ExamStatusEnum.SCHEDULED, ExamStatusEnum.ACTIVE]:
            raise HTTPException(status_code=400, detail="Exam is not active")
        
        if now < start:
            raise HTTPException(status_code=400, detail="Exam has not started yet")
        
        if now > end:
            raise HTTPException(status_code=400, detail="Exam has ended")
        
        # Auto-assign student if not already assigned (open enrollment)
        assignment_result = await self.db.execute(
            select(ExamAssignment).where(
                ExamAssignment.exam_id == exam.id,
                ExamAssignment.student_id == student.id
            )
        )
        if not assignment_result.scalar_one_or_none():
            new_assignment = ExamAssignment(
                exam_id=exam.id,
                student_id=student.id
            )
            self.db.add(new_assignment)
            await self.db.flush()

    async def _get_existing_paper(self, exam_id: int, student_id: int) -> Optional[StudentExamPaper]:
        result = await self.db.execute(
            select(StudentExamPaper).where(
                StudentExamPaper.exam_id == exam_id,
                StudentExamPaper.student_id == student_id
            ).order_by(StudentExamPaper.attempt_number.desc())
        )
        return result.scalars().first()

    async def _get_active_paper(self, exam_id: int, student_id: int) -> StudentExamPaper:
        paper = await self._get_existing_paper(exam_id, student_id)
        if not paper:
            raise HTTPException(status_code=404, detail="No active paper found")
        
        if paper.status in [PaperStatusEnum.SUBMITTED, PaperStatusEnum.AUTO_SUBMITTED, PaperStatusEnum.EVALUATED]:
            raise HTTPException(status_code=400, detail="Exam already submitted")
        
        return paper

    async def _get_attempt_count(self, exam_id: int, student_id: int) -> int:
        result = await self.db.execute(
            select(func.count(StudentExamPaper.id)).where(
                StudentExamPaper.exam_id == exam_id,
                StudentExamPaper.student_id == student_id
            )
        )
        return result.scalar() or 0

    async def _get_response(self, paper_id: int, question_id: int) -> Optional[StudentResponse]:
        result = await self.db.execute(
            select(StudentResponse).where(
                StudentResponse.paper_id == paper_id,
                StudentResponse.question_id == question_id
            )
        )
        return result.scalar_one_or_none()

    async def _get_question(self, question_id: int) -> Question:
        result = await self.db.execute(select(Question).where(Question.id == question_id))
        return result.scalar_one()

    async def _get_user(self, user_id: int) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one()

    async def _get_result(self, paper_id: int) -> Optional[Result]:
        result = await self.db.execute(select(Result).where(Result.paper_id == paper_id))
        return result.scalar_one_or_none()

    async def _update_time_remaining(self, paper: StudentExamPaper, exam: Exam = None) -> StudentExamPaper:
        """Calculate actual time remaining based on server time.
        Pass exam to avoid redundant DB query when caller already has it."""
        if paper.started_at and paper.status == PaperStatusEnum.IN_PROGRESS:
            if exam is None:
                exam = await self._get_exam(paper.exam_id)
            started = paper.started_at
            # Ensure timezone-aware comparison
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            elapsed = (now - started).total_seconds()
            total_seconds = exam.duration_minutes * 60
            remaining = max(0, int(total_seconds - elapsed))
            paper.time_remaining_seconds = remaining
            await self.db.flush()
        return paper

    async def _update_session_stats(self, exam_id: int, action: str):
        """Update exam session statistics"""
        session_result = await self.db.execute(
            select(ExamSession).where(
                ExamSession.exam_id == exam_id,
                ExamSession.is_active == True
            )
        )
        session = session_result.scalar_one_or_none()
        
        if session:
            if action == "started":
                session.students_started += 1
            elif action == "submitted":
                session.students_submitted += 1
            await self.db.flush()

    async def _build_paper_response(self, paper: StudentExamPaper, exam: Exam) -> ExamPaperResponse:
        """Build paper response for API — includes saved answers for resume support"""
        from app.schemas.schemas import SavedAnswer
        
        paper_questions = []
        
        for q_data in paper.paper_data["questions"]:
            pq = PaperQuestion(
                question_id=q_data["question_id"],
                question_text=q_data["question_text"],
                question_type=QuestionTypeEnum(q_data["question_type"]),
                options=q_data.get("options"),
                marks=q_data["marks"],
                negative_marks=q_data["negative_marks"]
            )
            paper_questions.append(pq)
        
        # Load saved answers for this paper (enables resume on refresh)
        saved_answers = None
        if paper.status == PaperStatusEnum.IN_PROGRESS:
            responses_result = await self.db.execute(
                select(StudentResponse).where(StudentResponse.paper_id == paper.id)
            )
            responses = responses_result.scalars().all()
            saved_answers = [
                SavedAnswer(
                    question_id=r.question_id,
                    selected_answer=r.selected_answer,
                    is_marked_for_review=r.is_marked_for_review or False
                )
                for r in responses
                if r.selected_answer is not None  # Only include answered questions
            ]
        
        return ExamPaperResponse(
            paper_id=paper.id,
            exam_id=exam.id,
            exam_title=exam.title,
            total_questions=exam.total_questions,
            duration_minutes=exam.duration_minutes,
            total_marks=exam.total_marks,
            status=paper.status,
            time_remaining_seconds=paper.time_remaining_seconds,
            questions=paper_questions,
            started_at=paper.started_at,
            answers=saved_answers
        )

    async def _build_result_response(self, result: Result) -> ResultResponse:
        """Build result response — single JOIN query instead of 2 separate queries."""
        row = await self.db.execute(
            select(Exam.title, User.full_name)
            .select_from(Result)
            .join(Exam, Result.exam_id == Exam.id)
            .join(User, Result.student_id == User.id)
            .where(Result.id == result.id)
        )
        exam_title, student_name = row.one()
        
        return ResultResponse(
            id=result.id,
            exam_id=result.exam_id,
            exam_title=exam_title,
            student_id=result.student_id,
            student_name=student_name,
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
