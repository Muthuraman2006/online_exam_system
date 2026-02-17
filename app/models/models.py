import enum
from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Text, ForeignKey, 
    Enum, Float, Index, UniqueConstraint, CheckConstraint, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base


class RoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    INVIGILATOR = "INVIGILATOR"
    STUDENT = "STUDENT"


class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False, default=RoleEnum.STUDENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships - noload for performance (load explicitly when needed)
    exam_papers: Mapped[List["StudentExamPaper"]] = relationship(back_populates="student", lazy="noload")
    results: Mapped[List["Result"]] = relationship(back_populates="student", lazy="noload")
    created_question_banks: Mapped[List["QuestionBank"]] = relationship(back_populates="created_by_user", lazy="noload")
    
    __table_args__ = (
        Index("ix_users_email_role", "email", "role"),
        Index("ix_users_role_active", "role", "is_active"),
    )


class QuestionBank(Base):
    __tablename__ = "question_banks"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships - noload for performance
    created_by_user: Mapped["User"] = relationship(back_populates="created_question_banks", lazy="noload")
    questions: Mapped[List["Question"]] = relationship(back_populates="question_bank", lazy="noload", cascade="all, delete-orphan")
    exams: Mapped[List["Exam"]] = relationship(back_populates="question_bank", lazy="noload")
    
    __table_args__ = (
        Index("ix_qbank_subject_active", "subject", "is_active"),
    )


class QuestionTypeEnum(str, enum.Enum):
    MCQ = "MCQ"
    TRUE_FALSE = "TRUE_FALSE"
    FILL_BLANK = "FILL_BLANK"


class DifficultyEnum(str, enum.Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class Question(Base):
    __tablename__ = "questions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    question_bank_id: Mapped[int] = mapped_column(Integer, ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuestionTypeEnum] = mapped_column(Enum(QuestionTypeEnum), nullable=False)
    difficulty: Mapped[DifficultyEnum] = mapped_column(Enum(DifficultyEnum), nullable=False, default=DifficultyEnum.MEDIUM)
    options: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # For MCQ: {"A": "opt1", "B": "opt2", ...}
    correct_answer: Mapped[str] = mapped_column(String(500), nullable=False)  # Stored hashed/encrypted for security
    marks: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    negative_marks: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # ["algebra", "chapter1"]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships - noload for performance
    question_bank: Mapped["QuestionBank"] = relationship(back_populates="questions", lazy="noload")
    student_responses: Mapped[List["StudentResponse"]] = relationship(back_populates="question", lazy="noload")
    
    __table_args__ = (
        Index("ix_question_bank_type_diff", "question_bank_id", "question_type", "difficulty"),
        Index("ix_question_active_bank", "is_active", "question_bank_id"),
        CheckConstraint("marks >= 0", name="check_marks_positive"),
        CheckConstraint("negative_marks >= 0", name="check_negative_marks_positive"),
    )


class ExamStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Exam(Base):
    __tablename__ = "exams"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_bank_id: Mapped[int] = mapped_column(Integer, ForeignKey("question_banks.id"), nullable=False, index=True)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_marks: Mapped[float] = mapped_column(Float, nullable=False)
    passing_marks: Mapped[float] = mapped_column(Float, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ExamStatusEnum] = mapped_column(Enum(ExamStatusEnum), nullable=False, default=ExamStatusEnum.DRAFT)
    
    # Exam configuration
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=True)
    shuffle_options: Mapped[bool] = mapped_column(Boolean, default=True)
    show_result_immediately: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_review: Mapped[bool] = mapped_column(Boolean, default=True)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    
    # Question distribution (JSON: {"easy": 10, "medium": 20, "hard": 10})
    difficulty_distribution: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships - noload for performance, load explicitly when needed
    question_bank: Mapped["QuestionBank"] = relationship(back_populates="exams", lazy="noload")
    exam_papers: Mapped[List["StudentExamPaper"]] = relationship(back_populates="exam", lazy="noload", cascade="all, delete-orphan")
    exam_sessions: Mapped[List["ExamSession"]] = relationship(back_populates="exam", lazy="noload", cascade="all, delete-orphan")
    results: Mapped[List["Result"]] = relationship(back_populates="exam", lazy="noload", cascade="all, delete-orphan")
    assigned_students: Mapped[List["ExamAssignment"]] = relationship(back_populates="exam", lazy="noload", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_exam_status_time", "status", "start_time", "end_time"),
        Index("ix_exam_bank_status", "question_bank_id", "status"),
        CheckConstraint("total_questions > 0", name="check_total_questions_positive"),
        CheckConstraint("duration_minutes > 0", name="check_duration_positive"),
        CheckConstraint("passing_marks <= total_marks", name="check_passing_marks"),
        CheckConstraint("end_time > start_time", name="check_end_after_start"),
    )


class ExamAssignment(Base):
    """Assigns exams to specific students"""
    __tablename__ = "exam_assignments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    exam: Mapped["Exam"] = relationship(back_populates="assigned_students", lazy="noload")
    
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", name="uq_exam_student_assignment"),
        Index("ix_assignment_student", "student_id"),
    )


class PaperStatusEnum(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    AUTO_SUBMITTED = "AUTO_SUBMITTED"
    EVALUATED = "EVALUATED"


class StudentExamPaper(Base):
    """Unique question paper generated for each student"""
    __tablename__ = "student_exam_papers"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Stores ordered question IDs with shuffled options
    # {"questions": [{"id": 1, "options_order": ["B", "A", "D", "C"]}, ...]}
    paper_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    status: Mapped[PaperStatusEnum] = mapped_column(Enum(PaperStatusEnum), nullable=False, default=PaperStatusEnum.NOT_STARTED)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Server-side timer tracking
    time_remaining_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    student: Mapped["User"] = relationship(back_populates="exam_papers", lazy="noload")
    exam: Mapped["Exam"] = relationship(back_populates="exam_papers", lazy="noload")
    responses: Mapped[List["StudentResponse"]] = relationship(back_populates="paper", lazy="noload", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", "attempt_number", name="uq_student_exam_attempt"),
        Index("ix_paper_student_exam", "student_id", "exam_id"),
        Index("ix_paper_status", "status"),
    )


class StudentResponse(Base):
    """Individual question responses"""
    __tablename__ = "student_responses"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("student_exam_papers.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    
    selected_answer: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_marked_for_review: Mapped[bool] = mapped_column(Boolean, default=False)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)  # Set after evaluation
    marks_obtained: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    paper: Mapped["StudentExamPaper"] = relationship(back_populates="responses", lazy="noload")
    question: Mapped["Question"] = relationship(back_populates="student_responses", lazy="noload")
    
    __table_args__ = (
        UniqueConstraint("paper_id", "question_id", name="uq_paper_question_response"),
        Index("ix_response_paper", "paper_id"),
        Index("ix_response_question", "question_id"),
    )


class Result(Base):
    """Final exam results"""
    __tablename__ = "results"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("student_exam_papers.id", ondelete="CASCADE"), nullable=False)
    
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    total_marks: Mapped[float] = mapped_column(Float, nullable=False)
    marks_obtained: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    is_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Detailed breakdown
    category_wise_score: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    difficulty_wise_score: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    student: Mapped["User"] = relationship(back_populates="results", lazy="noload")
    exam: Mapped["Exam"] = relationship(back_populates="results", lazy="noload")
    
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", "paper_id", name="uq_exam_student_result"),
        Index("ix_result_exam_rank", "exam_id", "rank"),
        Index("ix_result_student", "student_id"),
    )


class ExamSession(Base):
    """Live exam session tracking for invigilators"""
    __tablename__ = "exam_sessions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    total_students: Mapped[int] = mapped_column(Integer, default=0)
    students_started: Mapped[int] = mapped_column(Integer, default=0)
    students_submitted: Mapped[int] = mapped_column(Integer, default=0)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    exam: Mapped["Exam"] = relationship(back_populates="exam_sessions", lazy="noload")
    flags: Mapped[List["SessionFlag"]] = relationship(back_populates="session", lazy="noload", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_session_exam_active", "exam_id", "is_active"),
    )


class SessionFlag(Base):
    """Flags raised by invigilators for suspicious activity"""
    __tablename__ = "session_flags"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    flagged_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    flag_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "tab_switch", "suspicious_behavior", etc.
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    session: Mapped["ExamSession"] = relationship(back_populates="flags", lazy="noload")
    
    __table_args__ = (
        Index("ix_flag_session_student", "session_id", "student_id"),
    )
