"""
API Router
"""
from fastapi import APIRouter

from app.api import printers, jobs, devices, stats, logs

router = APIRouter()

# Include sub-routers
router.include_router(printers.router, prefix="/printers", tags=["printers"])
router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
router.include_router(devices.router, prefix="/devices", tags=["devices"])
router.include_router(stats.router, prefix="/stats", tags=["statistics"])
router.include_router(logs.router, prefix="/logs", tags=["logs"])