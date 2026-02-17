-- Performance indexes for Online Exam System
-- Run against Supabase PostgreSQL
-- All CREATE INDEX IF NOT EXISTS — safe to run multiple times

-- Users
CREATE INDEX IF NOT EXISTS ix_users_email_role ON users (email, role);
CREATE INDEX IF NOT EXISTS ix_users_role_active ON users (role, is_active);

-- Question Banks
CREATE INDEX IF NOT EXISTS ix_qbank_subject_active ON question_banks (subject, is_active);

-- Questions
CREATE INDEX IF NOT EXISTS ix_question_bank_type_diff ON questions (question_bank_id, question_type, difficulty);
CREATE INDEX IF NOT EXISTS ix_question_active_bank ON questions (is_active, question_bank_id);

-- Exams
CREATE INDEX IF NOT EXISTS ix_exam_status_time ON exams (status, start_time, end_time);
CREATE INDEX IF NOT EXISTS ix_exam_bank_status ON exams (question_bank_id, status);

-- Exam Assignments
CREATE INDEX IF NOT EXISTS ix_assignment_student ON exam_assignments (student_id);

-- Student Exam Papers
CREATE INDEX IF NOT EXISTS ix_paper_student_exam ON student_exam_papers (student_id, exam_id);
CREATE INDEX IF NOT EXISTS ix_paper_status ON student_exam_papers (status);

-- Student Responses
CREATE INDEX IF NOT EXISTS ix_response_paper ON student_responses (paper_id);
CREATE INDEX IF NOT EXISTS ix_response_question ON student_responses (question_id);

-- Results
CREATE INDEX IF NOT EXISTS ix_result_exam_rank ON results (exam_id, rank);
CREATE INDEX IF NOT EXISTS ix_result_student ON results (student_id);

-- Exam Sessions
CREATE INDEX IF NOT EXISTS ix_session_exam_active ON exam_sessions (exam_id, is_active);

-- Session Flags
CREATE INDEX IF NOT EXISTS ix_flag_session_student ON session_flags (session_id, student_id);
