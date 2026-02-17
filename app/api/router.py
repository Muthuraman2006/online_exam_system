from fastapi import APIRouter
from app.api.routes import auth, questions, exams, exam_session, results, sessions, dashboard

api_router = APIRouter()

# Include all routers
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(questions.router)
api_router.include_router(questions.questions_router)
api_router.include_router(exams.router)
api_router.include_router(exam_session.router)
api_router.include_router(results.router)
api_router.include_router(sessions.router)
