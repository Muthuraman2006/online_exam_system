import ssl
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Strict validation: only Supabase PostgreSQL allowed ──────────────────
if not settings.DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Provide a Supabase PostgreSQL connection string in .env  "
        "Example: DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>"
        "@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"
    )

if not settings.DATABASE_URL.startswith("postgresql+asyncpg://"):
    raise RuntimeError(
        f"Invalid DATABASE_URL driver. Expected 'postgresql+asyncpg://' but got: "
        f"'{settings.DATABASE_URL.split('://')[0]}://...'  "
        "SQLite and other databases are NOT supported."
    )

# ── SSL context for Supabase (requires TLS) ──────────────────────────────
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

_connect_args: dict = {"ssl": ssl_context}

# Supabase pooler (both session-mode 5432 and transaction-mode 6543)
# doesn't support server-side prepared statement caching
if "pooler.supabase.com" in settings.DATABASE_URL:
    _connect_args["prepared_statement_cache_size"] = 0

# ── Async engine (Supabase Pooler – Session mode) ────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    pool_pre_ping=True,
    pool_timeout=30,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency – yields a transactional async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def verify_supabase_connection(retries: int = 3, delay: float = 2.0) -> None:
    """Run SELECT 1 against Supabase to confirm connectivity.
    Retries on transient failures. Raises RuntimeError so the app
    refuses to start if Supabase is unreachable."""
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("✅ Supabase connected successfully")
            return
        except Exception as exc:
            last_exc = exc
            exc_str = str(exc).lower()

            # ── Actionable diagnostics ──────────────────────────
            if "password authentication failed" in exc_str:
                raise RuntimeError(
                    "❌ Supabase password is WRONG. "
                    "Go to Supabase Dashboard → Project Settings → Database "
                    "→ copy the correct password and update .env DATABASE_URL."
                ) from exc

            if "could not translate host name" in exc_str or "name or service not known" in exc_str:
                raise RuntimeError(
                    "❌ Cannot resolve Supabase host. Check your internet "
                    "connection and the host in DATABASE_URL."
                ) from exc

            # Transient / connection-closed — retry
            logger.warning(
                f"⚠️  Supabase connection attempt {attempt}/{retries} failed: {exc}"
            )
            if attempt < retries:
                await asyncio.sleep(delay)

    raise RuntimeError(
        f"❌ Failed to connect to Supabase after {retries} attempts. "
        f"Last error: {last_exc}\n"
        "Possible causes:\n"
        "  1. Supabase project is PAUSED → go to dashboard and click 'Restore'\n"
        "  2. Wrong password in .env → update DATABASE_URL\n"
        "  3. Network / firewall blocking port 5432\n"
    ) from last_exc


async def check_db_health() -> dict:
    """Lightweight health probe — returns connection status dict."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"database": "connected", "provider": "supabase"}
    except Exception as exc:
        return {"database": "disconnected", "error": str(exc)}


async def init_db() -> None:
    """Verify Supabase connectivity then create tables if they don't exist.
    Safe to call on every startup — CREATE TABLE IF NOT EXISTS is idempotent."""
    # 1. Connection check (with retries)
    await verify_supabase_connection()

    # 2. Ensure all model tables exist
    import app.models.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables verified / created successfully")
