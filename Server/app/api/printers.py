"""
Printer API Endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session, Printer, Device

router = APIRouter()


@router.get("/", summary="Get all printers")
async def get_printers(
    online_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """Get list of all registered printers (with host device info)"""
    query = select(Printer, Device).join(Device, Printer.host_device_id == Device.id, isouter=True)
    if online_only:
        query = query.where(Printer.status == "online")
    result = await session.execute(query)
    rows = result.all()
    printers = []
    for printer, device in rows:
        item = {
            "id": printer.id,
            "printer_id": printer.printer_id,
            "name": printer.name,
            "model": printer.model,
            "status": printer.status,
            "host_device_id": printer.host_device_id,
            "is_shared": printer.is_shared,
            "created_at": printer.created_at,
            "host_device_name": device.device_name if device else "",
            "host_device_id_str": device.device_id if device else "",
        }
        printers.append(item)
    return {"printers": printers}


@router.get("/{printer_id}", summary="Get printer by ID")
async def get_printer(
    printer_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get printer details by printer_id"""
    result = await session.execute(
        select(Printer).where(Printer.printer_id == printer_id)
    )
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    return printer


@router.get("/{printer_id}/status", summary="Get printer status")
async def get_printer_status(
    printer_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get printer current status"""
    result = await session.execute(
        select(Printer.status, Printer.name).where(Printer.printer_id == printer_id)
    )
    printer = result.one_or_none()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    return {"printer_id": printer_id, "name": printer.name, "status": printer.status}


@router.delete("/{printer_id}", summary="Delete a printer")
async def delete_printer(
    printer_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a printer"""
    result = await session.execute(
        select(Printer).where(Printer.printer_id == printer_id)
    )
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    await session.delete(printer)
    await session.commit()

    return {"printer_id": printer_id, "status": "deleted"}