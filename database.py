import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DB_URL")
if not DATABASE_URL:
    raise RuntimeError("DB_URL environment variable is not set. Use a postgresql+asyncpg URL.")

DATABASE_URL = DATABASE_URL.strip().strip('"').strip("'")

if not DATABASE_URL.startswith("postgresql+asyncpg://"):
    raise RuntimeError("DB_URL must use the asyncpg driver: postgresql+asyncpg://...")

# use normal SQLAlchemy pooling (session pooler on Supabase is compatible with prepared statements)
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session
