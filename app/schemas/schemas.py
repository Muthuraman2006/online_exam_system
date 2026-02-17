from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from app.models.models import RoleEnum, QuestionTypeEnum, DifficultyEnum, ExamStatusEnum, PaperStatusEnum


# ============ AUTH SCHEMAS ============

# Admin email - the ONLY admin allowed in the system
ADMIN_EMAIL = "muthuramanm.cse2024@citchennai.net"


class UserCreate(BaseModel):
    """Student registration - role is always STUDENT (enforced by backend)"""
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2, max_length=255)


class UserUpdate(BaseModel):
    """Update user profile (admin only)"""
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[str] = Field(None, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    is_active: Optional[bool] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: RoleEnum
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenWithUser(BaseModel):
    """Login response with token and user info for frontend"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    user_id: int
    email: str
    role: RoleEnum


# ============ QUESTION BANK SCHEMAS ============

class QuestionBankCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    subject: str = Field(..., min_length=2, max_length=100)


class QuestionBankUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None
    subject: Optional[str] = Field(None, min_length=2, max_length=100)
    is_active: Optional[bool] = None


class QuestionBankResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    subject: str
    created_by: int
    is_active: bool
    created_at: datetime
    question_count: int = 0

    class Config:
        from_attributes = True


# ============ QUESTION SCHEMAS ============

class QuestionCreate(BaseModel):
    question_bank_id: int
    question_text: str = Field(..., min_length=10)
    question_type: QuestionTypeEnum
    difficulty: DifficultyEnum = DifficultyEnum.MEDIUM
    options: Optional[Dict[str, str]] = None  # {"A": "opt1", "B": "opt2", ...}
    correct_answer: str
    marks: float = Field(1.0, ge=0)
    negative_marks: float = Field(0.0, ge=0)
    explanation: Optional[str] = None
    tags: Optional[List[str]] = None

    @field_validator("options")
    @classmethod
    def validate_options(cls, v, info):
        if info.data.get("question_type") == QuestionTypeEnum.MCQ:
            if not v or len(v) < 2:
                raise ValueError("MCQ must have at least 2 options")
        return v


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = Field(None, min_length=10)
    question_type: Optional[QuestionTypeEnum] = None
    difficulty: Optional[DifficultyEnum] = None
    options: Optional[Dict[str, str]] = None
    correct_answer: Optional[str] = None
    marks: Optional[float] = Field(None, ge=0)
    negative_marks: Optional[float] = Field(None, ge=0)
    explanation: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class QuestionResponse(BaseModel):
    id: int
    question_bank_id: int
    question_text: str
    question_type: QuestionTypeEnum
    difficulty: DifficultyEnum
    options: Optional[Dict[str, str]]
    marks: float
    negative_marks: float
    explanation: Optional[str]
    tags: Optional[List[str]]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class QuestionWithAnswer(QuestionResponse):
    correct_answer: str


# ============ EXAM SCHEMAS ============

class DifficultyDistribution(BaseModel):
    easy: int = Field(0, ge=0)
    medium: int = Field(0, ge=0)
    hard: int = Field(0, ge=0)


class ExamCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=255)
    description: Optional[str] = None
    question_bank_id: int
    total_questions: int = Field(..., gt=0)
    duration_minutes: int = Field(..., gt=0, le=360)
    total_marks: float = Field(..., gt=0)
    passing_marks: float = Field(..., ge=0)
    start_time: datetime
    end_time: datetime
    shuffle_questions: bool = True
    shuffle_options: bool = True
    show_result_immediately: bool = False
    allow_review: bool = True
    max_attempts: int = Field(1, ge=1)
    difficulty_distribution: Optional[DifficultyDistribution] = None

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v, info):
        if info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v

    @field_validator("passing_marks")
    @classmethod
    def validate_passing_marks(cls, v, info):
        if info.data.get("total_marks") and v > info.data["total_marks"]:
            raise ValueError("Passing marks cannot exceed total marks")
        return v


class ExamUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=255)
    description: Optional[str] = None
    question_bank_id: Optional[int] = None
    total_questions: Optional[int] = Field(None, gt=0)
    duration_minutes: Optional[int] = Field(None, gt=0, le=360)
    total_marks: Optional[float] = Field(None, gt=0)
    passing_marks: Optional[float] = Field(None, ge=0)
    max_attempts: Optional[int] = Field(None, ge=1)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[ExamStatusEnum] = None
    shuffle_questions: Optional[bool] = None
    shuffle_options: Optional[bool] = None
    show_result_immediately: Optional[bool] = None
    allow_review: Optional[bool] = None
    difficulty_distribution: Optional[DifficultyDistribution] = None


class ExamResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    question_bank_id: int
    total_questions: int
    duration_minutes: int
    total_marks: float
    passing_marks: float
    start_time: datetime
    end_time: datetime
    status: ExamStatusEnum
    shuffle_questions: bool
    shuffle_options: bool
    show_result_immediately: bool
    allow_review: bool
    max_attempts: int
    difficulty_distribution: Optional[Dict[str, int]]
    created_by: int
    created_at: datetime

    class Config:
        from_attributes = True


class ExamAssign(BaseModel):
    student_ids: List[int]


class StudentExamAssignment(BaseModel):
    """Exam assignment for a student with completion status."""
    id: int
    exam: ExamResponse
    is_completed: bool
    assigned_at: datetime

    class Config:
        from_attributes = True


# ============ EXAM PAPER SCHEMAS ============

class PaperQuestion(BaseModel):
    question_id: int
    question_text: str
    question_type: QuestionTypeEnum
    options: Optional[Dict[str, str]]  # Shuffled options
    marks: float
    negative_marks: float


class SavedAnswer(BaseModel):
    question_id: int
    selected_answer: Optional[str] = None
    is_marked_for_review: bool = False


class ExamPaperResponse(BaseModel):
    paper_id: int
    exam_id: int
    exam_title: str
    total_questions: int
    duration_minutes: int
    total_marks: float
    status: PaperStatusEnum
    time_remaining_seconds: Optional[int]
    questions: List[PaperQuestion]
    started_at: Optional[datetime]
    answers: Optional[List[SavedAnswer]] = None


class StudentAnswer(BaseModel):
    question_id: int
    selected_answer: Optional[str] = None
    is_marked_for_review: bool = False


class AnswerSubmit(BaseModel):
    answers: List[StudentAnswer]


class SingleAnswerSave(BaseModel):
    question_id: int
    selected_answer: Optional[str] = None
    is_marked_for_review: bool = False


# ============ RESULT SCHEMAS ============

class ResultResponse(BaseModel):
    id: int
    exam_id: int
    exam_title: str
    student_id: int
    student_name: str
    student_email: Optional[str] = None
    total_questions: int
    attempted: int
    correct: int
    wrong: int
    total_marks: float
    marks_obtained: float
    percentage: float
    is_passed: bool
    rank: Optional[int]
    category_wise_score: Optional[Dict[str, Any]]
    difficulty_wise_score: Optional[Dict[str, Any]]
    evaluated_at: datetime

    class Config:
        from_attributes = True


class ResultSummary(BaseModel):
    exam_id: int
    exam_title: str
    total_students: int
    students_appeared: int
    students_passed: int
    average_score: float
    highest_score: float
    lowest_score: float


# ============ SESSION SCHEMAS ============

class ExamSessionResponse(BaseModel):
    id: int
    exam_id: int
    exam_title: str
    started_at: datetime
    ended_at: Optional[datetime]
    total_students: int
    students_started: int
    students_submitted: int
    is_active: bool

    class Config:
        from_attributes = True


class StudentProgress(BaseModel):
    student_id: int
    student_name: str
    status: PaperStatusEnum
    questions_attempted: int
    time_remaining_seconds: Optional[int]
    last_activity_at: Optional[datetime]


class FlagCreate(BaseModel):
    student_id: int
    flag_type: str = Field(..., min_length=3, max_length=50)
    description: Optional[str] = None


class FlagResponse(BaseModel):
    id: int
    session_id: int
    student_id: int
    flagged_by: int
    flag_type: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
