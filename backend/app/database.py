from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    # Make sure the folder for the .db file exists before SQLite tries to open it.
    settings.data_path.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

if _is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        # Background jobs and API requests write concurrently: WAL + a busy timeout avoids "database is locked".
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=15000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session
