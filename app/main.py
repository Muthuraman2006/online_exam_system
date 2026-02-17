from contextlib import asynccontextmanager
from pathlib import Path
import time
import logging
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db
from app.api.router import api_router

# Configure logging — WARNING level to avoid noisy INFO on every request
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # app logger stays INFO for our middleware

# Get the project root directory
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown


app = FastAPI(
    title="Online Examination System",
    description="A comprehensive online examination platform with admin, student, and invigilator workflows",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Response time logging middleware
@app.middleware("http")
async def log_request_time(request: Request, call_next):
    """Log request processing time for performance monitoring"""
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000  # Convert to milliseconds
    
    # Only log API requests (skip static files)
    if request.url.path.startswith("/api/"):
        logger.info(
            f"[{request.method}] {request.url.path} - "
            f"{response.status_code} - {process_time:.2f}ms"
        )
        # Warn for slow requests (>500ms)
        if process_time > 500:
            logger.warning(f"SLOW REQUEST: {request.url.path} took {process_time:.2f}ms")
    
    # Add timing header for debugging
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
    return response


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return clear, field-level validation errors for frontend display"""
    errors = []
    for error in exc.errors():
        # Extract field name (skip 'body' prefix)
        loc = error.get("loc", [])
        field = loc[-1] if loc else "unknown"
        if field == "body" and len(loc) > 1:
            field = loc[1]
        
        # Create human-readable messages
        msg = error.get("msg", "Invalid value")
        err_type = error.get("type", "")
        
        # Improve common error messages
        if "string_too_short" in err_type:
            ctx = error.get("ctx", {})
            min_len = ctx.get("min_length", 0)
            msg = f"Must be at least {min_len} characters"
        elif "string_too_long" in err_type:
            ctx = error.get("ctx", {})
            max_len = ctx.get("max_length", 0)
            msg = f"Must be at most {max_len} characters"
        elif "missing" in err_type:
            msg = "This field is required"
        elif "string_pattern_mismatch" in err_type:
            if "email" in str(field).lower():
                msg = "Please enter a valid email address"
            else:
                msg = "Invalid format"
        elif "greater_than_equal" in err_type:
            ctx = error.get("ctx", {})
            msg = f"Must be at least {ctx.get('ge', 0)}"
        elif "less_than_equal" in err_type:
            ctx = error.get("ctx", {})
            msg = f"Must be at most {ctx.get('le', 0)}"
        elif "enum" in err_type:
            msg = "Please select a valid option"
        
        errors.append({
            "field": str(field),
            "message": msg
        })
    
    # Create summary message
    if len(errors) == 1:
        summary = f"{errors[0]['field']}: {errors[0]['message']}"
    else:
        summary = f"{len(errors)} validation errors"
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": summary,
            "errors": errors
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    # Let HTTPException pass through with its proper status code
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
    if settings.DEBUG:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc)}
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


# Include API router
app.include_router(api_router, prefix="/api/v1")

# Mount static files (CSS, JS, images)
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")


# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve HTML pages
@app.get("/", response_class=HTMLResponse)
async def serve_root():
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/{page_name}.html", response_class=HTMLResponse)
async def serve_html_page(page_name: str):
    file_path = FRONTEND_DIR / f"{page_name}.html"
    if file_path.exists():
        return FileResponse(file_path)
    return HTMLResponse(content="<h1>404 - Page Not Found</h1>", status_code=404)
