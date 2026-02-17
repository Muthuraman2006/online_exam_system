# ExamPro System Architecture & Workflow

## 1. System Workflows

### 1.1 Website User Journey
```
┌─────────────────────────────────────────────────────────────┐
│                    ExamPro System Flow                       │
└─────────────────────────────────────────────────────────────┘

STUDENT:
  auth.html (Login/Signup)
       ↓
  student-dashboard-main.html (View exams)
       ↓
  take-exam.html (Answer questions)
       ↓
  Submit exam
       ↓
  student-results.html (View results)

ADMIN:
  auth.html (Login)
       ↓
  admin-dashboard.html (System overview)
       ↓
  exams.html (Manage exams)
       ↓
  question-banks.html (Manage questions)
       ↓
  students.html (Manage users)
       ↓
  results.html (View analytics)
```

### 1.2 Authentication Workflow
```
┌─────────────────────────────────────────────────────────────┐
│              Authentication & Authorization                   │
└─────────────────────────────────────────────────────────────┘

Frontend (auth.html):
  1. User enters email & password
  2. Sends POST /api/v1/auth/login
  3. Receives token + user data
  4. Stores in localStorage
  5. Reads role from token
  6. Redirects to dashboard

Backend (app/services/auth_service.py):
  1. Receives email & password
  2. Queries users table
  3. Verifies bcrypt password hash
  4. Creates JWT token
  5. Returns token + user object
  6. (Role already in database)

JWT Token Contents:
  {
    "sub": "1",           // User ID
    "email": "user@..",
    "role": "student",    // From database
    "exp": 1770271887
  }
```

### 1.3 Authorization Workflow
```
┌─────────────────────────────────────────────────────────────┐
│           Protected Route Authorization                       │
└─────────────────────────────────────────────────────────────┘

Protected Endpoint (e.g., /api/v1/exams/create):
  1. Frontend sends JWT token in Authorization header
  2. Backend extracts token from header
  3. Decodes JWT (HS256)
  4. Verifies signature & expiration
  5. Checks role claim
  6. If role != "admin" → 403 Forbidden
  7. If valid → Process request

Error Cases:
  - No token → 401 Unauthorized
  - Invalid token → 401 Unauthorized
  - Expired token → 401 Unauthorized
  - Wrong role → 403 Forbidden
  - User deactivated → 403 Forbidden
```

---

## 2. Backend Architecture

### 2.1 Database Schema (PostgreSQL via Supabase)
```
┌──────────────────────────────────────────────────────────────┐
│                     Database Tables                           │
└──────────────────────────────────────────────────────────────┘

TABLE: users
  ├─ id: INT (PK)
  ├─ email: VARCHAR UNIQUE
  ├─ hashed_password: VARCHAR (bcrypt)
  ├─ full_name: VARCHAR
  ├─ role: ENUM(admin, invigilator, student)
  ├─ is_active: BOOLEAN
  └─ created_at: TIMESTAMP

TABLE: question_banks
  ├─ id: INT (PK)
  ├─ name: VARCHAR
  ├─ subject: VARCHAR
  ├─ created_by: INT (FK → users.id)
  └─ created_at: TIMESTAMP

TABLE: questions
  ├─ id: INT (PK)
  ├─ question_bank_id: INT (FK)
  ├─ question_text: TEXT
  ├─ question_type: ENUM(mcq, true_false, fill_blank)
  ├─ options: JSON ({"A":"opt1", "B":"opt2"})
  ├─ correct_answer: VARCHAR (hashed)
  ├─ marks: FLOAT
  └─ created_at: TIMESTAMP

TABLE: exams
  ├─ id: INT (PK)
  ├─ title: VARCHAR
  ├─ question_bank_id: INT (FK)
  ├─ total_questions: INT
  ├─ duration_minutes: INT
  ├─ total_marks: FLOAT
  ├─ passing_marks: FLOAT
  ├─ start_time: TIMESTAMP
  ├─ end_time: TIMESTAMP
  ├─ status: ENUM(draft, scheduled, active, completed)
  ├─ created_by: INT (FK → users.id)
  └─ created_at: TIMESTAMP

TABLE: student_exam_papers
  ├─ id: INT (PK)
  ├─ student_id: INT (FK → users.id)
  ├─ exam_id: INT (FK → exams.id)
  ├─ paper_data: JSON (student responses)
  ├─ status: ENUM(in_progress, submitted, evaluated)
  ├─ started_at: TIMESTAMP
  ├─ submitted_at: TIMESTAMP
  └─ created_at: TIMESTAMP

TABLE: results
  ├─ id: INT (PK)
  ├─ student_id: INT (FK)
  ├─ exam_id: INT (FK)
  ├─ total_questions: INT
  ├─ attempted: INT
  ├─ correct: INT
  ├─ marks_obtained: FLOAT
  ├─ percentage: FLOAT
  ├─ is_passed: BOOLEAN
  ├─ rank: INT
  └─ evaluated_at: TIMESTAMP
```

### 2.2 Backend Project Structure
```
app/
├── main.py
│   └─ FastAPI app, CORS, routes, exception handlers
│
├── core/
│   ├── config.py (Settings, CORS origins)
│   ├── database.py (SQLAlchemy async setup)
│   └── security.py (Password hashing, JWT tokens)
│
├── models/
│   └── models.py (SQLAlchemy ORM models)
│
├── schemas/
│   └── schemas.py (Pydantic schemas for validation)
│
├── services/
│   ├── auth_service.py (Register, Login logic)
│   ├── exam_service.py (Exam CRUD)
│   ├── question_service.py (Question CRUD)
│   └── result_service.py (Result calculations)
│
└── api/
    ├── router.py (Main API router)
    ├── routes/
    │   ├── auth.py (Login, Register endpoints)
    │   ├── exams.py (Exam endpoints)
    │   ├── questions.py (Question endpoints)
    │   └── results.py (Result endpoints)
    │
    └── deps/
        └── auth.py (JWT dependency, role checking)
```

### 2.3 API Endpoints (Key Routes)
```
┌──────────────────────────────────────────────────────────────┐
│                   REST API Endpoints                          │
└──────────────────────────────────────────────────────────────┘

Authentication:
  POST   /api/v1/auth/login
         → Login, get JWT token
  
  POST   /api/v1/auth/register
         → Student signup (role always "student")
  
  GET    /api/v1/auth/me
         → Get current user info (requires token)

Exams (Admin):
  GET    /api/v1/exams
         → List all exams (admin only)
  
  POST   /api/v1/exams
         → Create exam (admin only)
  
  PUT    /api/v1/exams/{id}
         → Update exam (admin only)
  
  DELETE /api/v1/exams/{id}
         → Delete exam (admin only)

Exams (Student):
  GET    /api/v1/exams/available
         → List exams student can take
  
  GET    /api/v1/exams/{id}
         → Get exam details

Questions (Admin):
  POST   /api/v1/questions
         → Create question (admin only)
  
  PUT    /api/v1/questions/{id}
         → Update question (admin only)

Student Sessions:
  POST   /api/v1/exam-session
         → Start exam session
  
  POST   /api/v1/exam-session/{id}/response
         → Save answer (auto-save)
  
  POST   /api/v1/exam-session/{id}/submit
         → Submit exam

Results:
  GET    /api/v1/results/my
         → Get student's results
  
  GET    /api/v1/results
         → Get all results (admin only)
```

### 2.4 Service Layer Pattern
```
Example: Exam Service
──────────────────────

class ExamService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_available_exams(self, student_id: int) -> List[Exam]:
        # 1. Query database
        # 2. Filter by status and date
        # 3. Check student assignments
        # 4. Return list
        pass
    
    async def create_exam(self, exam_data: ExamCreate, admin_user: User) -> Exam:
        # 1. Validate input
        # 2. Check admin role
        # 3. Create exam record
        # 4. Return created exam
        pass
    
    async def evaluate_exam(self, session_id: int) -> Result:
        # 1. Get student responses
        # 2. Compare with correct answers
        # 3. Calculate marks
        # 4. Store result
        # 5. Return result object
        pass
```

---

## 3. Frontend Architecture

### 3.1 Frontend Project Structure
```
frontend/
├── auth.html
│   └─ Login/Signup page
│
├── admin-dashboard.html
│   └─ Admin overview dashboard
│
├── exams.html
│   └─ Admin exam management
│
├── question-banks.html
│   └─ Admin question management
│
├── student-dashboard-main.html
│   └─ Student home, available exams
│
├── take-exam.html
│   └─ Exam interface, question display, timer
│
├── student-results.html
│   └─ Student view their results
│
├── results.html
│   └─ Admin view all results
│
├── css/
│   ├── core.css (Centralized design system)
│   ├── layout.css (Layouts, grids)
│   └── design-system.css (Colors, typography)
│
└── js/
    ├── api.js (HTTP client with token auth)
    ├── auth.js (Authentication utilities)
    ├── exam.js (Exam logic)
    ├── dashboard.js (Dashboard interactions)
    └── utils.js (Helper functions)
```

### 3.2 Frontend Token Management
```
┌──────────────────────────────────────────────────────────────┐
│            LocalStorage Token Architecture                     │
└──────────────────────────────────────────────────────────────┘

LocalStorage Keys:
  exampro-access-token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  exampro-user: {
    "id": 1,
    "email": "user@example.com",
    "full_name": "John Doe",
    "role": "student",
    "is_active": true,
    "created_at": "2026-02-05T..."
  }

Token Flow:
  1. Login API returns token
  2. JavaScript stores in localStorage
  3. Before API calls, read token
  4. Add to Authorization header
  5. Backend validates token
  6. If invalid → Clear localStorage, redirect to login
```

### 3.3 JavaScript API Client
```javascript
// api.js - HTTP client with token injection

const http = {
  async get(url) {
    const token = localStorage.getItem('exampro-access-token');
    return fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });
  },
  
  async post(url, data) {
    const token = localStorage.getItem('exampro-access-token');
    return fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(data)
    });
  }
};

// Usage:
const exams = await (await http.get('/api/v1/exams/available')).json();
```

---

## 4. Security Architecture

### 4.1 Authentication Flow
```
Step 1: User provides credentials
  Email: user@example.com
  Password: MyPassword@123

Step 2: Backend verification
  ├─ Query: SELECT * FROM users WHERE email = ?
  ├─ Check: user exists?
  ├─ Check: bcrypt_verify(password, hashed_password)?
  ├─ Check: is_active = true?
  └─ Result: User object + role from database

Step 3: Token generation
  ├─ Data: {sub: user.id, email: user.email, role: user.role}
  ├─ Sign: HS256(data, SECRET_KEY)
  └─ Result: JWT token (3 parts: header.payload.signature)

Step 4: Frontend storage
  ├─ Save: localStorage['exampro-access-token'] = token
  ├─ Save: localStorage['exampro-user'] = user object
  └─ Result: Token ready for future requests

Step 5: Protected API calls
  ├─ Header: Authorization: Bearer {token}
  ├─ Backend: Verify signature
  ├─ Backend: Check expiration
  ├─ Backend: Extract role claim
  ├─ Backend: Check role for endpoint permission
  └─ Result: Request allowed or 403 Forbidden
```

### 4.2 Role-Based Access Control (RBAC)
```
┌─────────────────────────────────────────────────────────────┐
│             Role Authorization Matrix                        │
└─────────────────────────────────────────────────────────────┘

Endpoint                    Admin   Student   Invigilator
─────────────────────────────────────────────────────────────
GET    /auth/me             ✅       ✅         ✅
POST   /auth/login          ✅       ✅         ✅
POST   /auth/register       ❌       ✅         ❌

GET    /exams               ✅       ❌         ❌
POST   /exams               ✅       ❌         ❌
PUT    /exams/{id}          ✅       ❌         ❌
DELETE /exams/{id}          ✅       ❌         ❌

GET    /exams/available     ✅       ✅         ✅
POST   /exam-session        ❌       ✅         ❌
POST   /exam-session/submit ❌       ✅         ❌

GET    /results             ✅       ❌         ❌
GET    /results/my          ✅       ✅         ❌
```

### 4.3 Password Security
```
Registration:
  1. User enters: "MyPassword@123"
  2. Backend: password_hash = bcrypt.hash(password)
  3. Database: Store hashed_password (NOT plain text)

Login:
  1. User enters: "MyPassword@123"
  2. Backend: stored_hash = SELECT hashed_password FROM users
  3. Backend: verify = bcrypt.verify(entered_password, stored_hash)
  4. Result: True → Proceed, False → Reject

Bcrypt Properties:
  - One-way function (cannot reverse)
  - Salted automatically
  - Slowed down (expensive computation)
  - 72-byte limit (truncate if longer)
```

---

## 5. Data Flow Examples

### 5.1 Student Taking Exam
```
1. Student opens: /take-exam.html?exam_id=5

2. Frontend:
   a. Read query parameter exam_id=5
   b. GET /api/v1/exams/5 (with token)
   c. Display exam title, time limit
   d. Start timer (countdown)
   e. POST /api/v1/exam-session (create session)
   f. Display first question

3. For each answer:
   a. Student selects/types answer
   b. POST /api/v1/exam-session/response (auto-save every 30s)
   c. Backend stores in StudentResponse table
   d. Display confirmation "Saved"

4. Student submits:
   a. POST /api/v1/exam-session/submit
   b. Backend:
      - Lock exam session
      - Evaluate answers
      - Calculate marks
      - Determine pass/fail
      - Store in results table
   c. Frontend redirects to results page

5. View results:
   - GET /api/v1/results/my
   - Display score, rank, detailed breakdown
```

### 5.2 Admin Creating Exam
```
1. Admin opens: /exams.html

2. Frontend:
   a. GET /api/v1/question-banks (fetch available banks)
   b. Display form: title, questions, marks, time, etc.

3. Admin fills form:
   - Title: "Semester Final Exam"
   - Question Bank: "Physics Ch1-5"
   - Total Questions: 50
   - Duration: 120 minutes
   - Passing Marks: 40%
   - Start Time: 2026-02-10 09:00
   - End Time: 2026-02-10 11:00

4. Submit:
   a. POST /api/v1/exams (with admin token)
   b. Backend validates (admin role required)
   c. Create exam record
   d. Set status = "SCHEDULED"
   e. Return exam object

5. Assign to students:
   a. POST /api/v1/exam-assignments
   b. Select student list
   c. Backend creates exam_assignment records
   d. Students see in /exams/available
```

---

## 6. Error Handling

### 6.1 Backend Error Response Format
```json
{
  "detail": "User already exists",
  "errors": [
    {
      "field": "email",
      "message": "Email already registered",
      "type": "validation_error"
    }
  ]
}
```

### 6.2 HTTP Status Codes
```
200 OK                    - Request successful
201 Created               - Resource created
400 Bad Request          - Invalid input
401 Unauthorized         - Missing/invalid token
403 Forbidden            - Valid token, insufficient permission
404 Not Found            - Resource not found
422 Unprocessable Entity - Validation error
500 Internal Server Error - Unexpected error
```

---

## 7. Performance Considerations

### 7.1 Database Indexing
```
Indexes on:
  - users.email (UNIQUE for fast login)
  - users.role (for filtering students)
  - exam_sessions.student_id (student's exams)
  - exam_sessions.exam_id (exam's participants)
  - results.student_id (student's results)
  - exams.status (filter by status)
```

### 7.2 Frontend Optimization
```
- Lazy load exam questions
- Cache user info in localStorage
- Debounce auto-save (not on every keystroke)
- Minimize JavaScript bundle
- Use CSS grid for responsive layouts
```

---

## 8. Deployment Architecture

### 8.1 Development
```
Frontend: http://127.0.0.1:8000 (served by FastAPI)
Backend:  http://127.0.0.1:8000 (FastAPI + Uvicorn)
Database: PostgreSQL (Supabase)
```

### 8.2 Production (Recommended)
```
Frontend: Served from S3 or CDN
          OR FastAPI static files
          Origin: https://exampr

Backend:  FastAPI on Cloud Run / Heroku / EC2
          Origin: https://api.exampr...

Database: Supabase PostgreSQL (managed)
          Automatic backups, SSL

CORS:     Frontend origin → Backend API
          (Specific, not wildcard)

SSL:      HTTPS everywhere
          Valid certificates
```

---

## Summary

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | HTML/CSS/JS | User interface |
| Backend | FastAPI | REST API, business logic |
| Database | PostgreSQL | Persistent data storage |
| Auth | JWT (HS256) | Stateless authentication |
| Password | Bcrypt | Secure hashing |
| Role Check | JWT payload | Authorization |
| CORS | Middleware | Cross-origin requests |

**System is production-ready for academic/examination use.**
