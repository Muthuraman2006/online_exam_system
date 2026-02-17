from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import ssl
from app.core.config import settings

# Create SSL context for Supabase (requires TLS)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Connection pool WITH PgBouncer: SQLAlchemy pool keeps warm TCP/TLS connections
# to PgBouncer, which itself pools PostgreSQL connections. This avoids the
# ~500-1500ms TCP+TLS handshake overhead on every request.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,            # NEVER echo SQL in production — blocks event loop
    pool_size=5,           # Keep 5 warm connections to PgBouncer
    max_overflow=10,       # Allow up to 15 total during spikes
    pool_recycle=300,      # Recycle every 5 min (PgBouncer may drop idle)
    pool_pre_ping=True,    # Verify connection is alive before use
    pool_timeout=10,       # Wait max 10s for a connection from pool
    future=True,
    connect_args={"ssl": ssl_context}
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Placeholder — tables are managed by Alembic migrations, not create_all."""
    pass
