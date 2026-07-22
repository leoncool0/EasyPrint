"""
Statistics API Endpoints
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session, Device, Printer, PrintJob, PrintLog

router = APIRouter()


@router.get("/", summary="Get server statistics")
async def get_stats(session: AsyncSession = Depends(get_session)):
    """Get overall server statistics"""

    # Device stats
    total_devices_result = await session.execute(select(func.count(Device.id)))
    total_devices = total_devices_result.scalar()

    online_devices_result = await session.execute(
        select(func.count(Device.id)).where(Device.is_online == True)
    )
    online_devices = online_devices_result.scalar()

    # Printer stats
    total_printers_result = await session.execute(select(func.count(Printer.id)))
    total_printers = total_printers_result.scalar()

    online_printers_result = await session.execute(
        select(func.count(Printer.id)).where(Printer.status == "online")
    )
    online_printers = online_printers_result.scalar()

    # Job stats - today
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_jobs_result = await session.execute(
        select(func.count(PrintJob.id)).where(PrintJob.created_at >= today)
    )
    today_jobs = today_jobs_result.scalar()

    return {
        "total_devices": total_devices,
        "online_devices": online_devices,
        "offline_devices": total_devices - online_devices,
        "total_printers": total_printers,
        "online_printers": online_printers,
        "today_jobs": today_jobs,
    }