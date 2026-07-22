"""
Print Log API Endpoints
"""
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session, PrintLog

router = APIRouter()


@router.get("/", summary="Get print logs")
async def get_logs(
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """Get recent print logs"""
    result = await session.execute(
        select(PrintLog).order_by(PrintLog.created_at.desc()).limit(limit)
    )
    logs = result.scalars().all()
    return {"logs": logs}