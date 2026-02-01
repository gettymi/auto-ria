import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, BigInteger, DateTime
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_HOST = os.getenv("DB_HOST_LOCAL", "localhost")   
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)



class Base(AsyncAttrs, DeclarativeBase):
    pass


class Car(Base):
    __tablename__ = 'cars'

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    url: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    price_usd: Mapped[int] = mapped_column(Integer)
    odometer: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String, default="Unknown")
    phone_number: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    images_count: Mapped[int] = mapped_column(Integer, default=0)
    car_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    car_vin: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    datetime_found: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)