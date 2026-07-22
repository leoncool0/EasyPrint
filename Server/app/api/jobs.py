"""
Print Job API Endpoints
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session, PrintJob, Printer, Device

router = APIRouter()


@router.get("/", summary="Get all jobs")
async def get_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """Get list of print jobs"""
    query = select(PrintJob).order_by(PrintJob.created_at.desc()).limit(limit)
    if status:
        query = query.where(PrintJob.status == status)
    result = await session.execute(query)
    jobs = result.scalars().all()
    return {"jobs": jobs}


@router.get("/{job_id}", summary="Get job by ID")
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get print job details"""
    result = await session.execute(
        select(PrintJob).where(PrintJob.job_id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", summary="Cancel a job")
async def cancel_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Cancel a print job"""
    result = await session.execute(
        select(PrintJob).where(PrintJob.job_id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ["completed", "cancelled", "failed"]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel job in {job.status} status")

    job.status = "cancelled"
    job.updated_at = datetime.utcnow()
    await session.commit()

    return {"job_id": job_id, "status": "cancelled"}