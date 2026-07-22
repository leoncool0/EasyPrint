"""
Database Models and Initialization
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


def local_now():
    """Get current local time (UTC+8)"""
    return datetime.now(timezone(timedelta(hours=8)))


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


# Async engine and session
engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get database session"""
    async with async_session_maker() as session:
        yield session


class Device(Base):
    """Device model - represents a client device"""
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    device_name: Mapped[Optional[str]] = mapped_column(sa.String(128))
    device_type: Mapped[str] = mapped_column(sa.String(32))  # host, user, mixed
    os_version: Mapped[Optional[str]] = mapped_column(sa.String(64))
    ip_address: Mapped[Optional[str]] = mapped_column(sa.String(45))
    mac_address: Mapped[Optional[str]] = mapped_column(sa.String(17))
    token: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    is_online: Mapped[bool] = mapped_column(default=False)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(sa.DateTime)
    created_at: Mapped[datetime] = mapped_column(default=local_now)
    updated_at: Mapped[datetime] = mapped_column(default=local_now, onupdate=local_now)


class Printer(Base):
    """Printer model - represents a shared printer"""
    __tablename__ = "printers"

    id: Mapped[int] = mapped_column(primary_key=True)
    printer_id: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(sa.String(128))
    model: Mapped[Optional[str]] = mapped_column(sa.String(128))
    host_device_id: Mapped[int] = mapped_column(sa.ForeignKey("devices.id"))
    status: Mapped[str] = mapped_column(sa.String(32), default="offline")  # online, offline, busy, error
    capabilities: Mapped[Optional[str]] = mapped_column(sa.Text)  # JSON string
    is_shared: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=local_now)
    updated_at: Mapped[datetime] = mapped_column(default=local_now, onupdate=local_now)


class PrintJob(Base):
    """Print job model - represents a print task"""
    __tablename__ = "print_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    printer_id: Mapped[int] = mapped_column(sa.ForeignKey("printers.id"))
    user_device_id: Mapped[int] = mapped_column(sa.ForeignKey("devices.id"))
    job_name: Mapped[Optional[str]] = mapped_column(sa.String(256))
    file_size: Mapped[int] = mapped_column(default=0)
    pages: Mapped[Optional[int]] = mapped_column()
    copies: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(sa.String(32), default="created")  # created, transferring, queued, printing, completed, failed, cancelled
    error_message: Mapped[Optional[str]] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(default=local_now)
    updated_at: Mapped[datetime] = mapped_column(default=local_now, onupdate=local_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime)


class PrintLog(Base):
    """Print log model - audit log"""
    __tablename__ = "print_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(sa.String(64), index=True)
    printer_id: Mapped[int] = mapped_column(sa.ForeignKey("printers.id"))
    user_device_id: Mapped[int] = mapped_column(sa.ForeignKey("devices.id"))
    action: Mapped[str] = mapped_column(sa.String(32))  # create, transfer, print, complete, fail, cancel
    details: Mapped[Optional[str]] = mapped_column(sa.Text)  # JSON string
    created_at: Mapped[datetime] = mapped_column(default=local_now)