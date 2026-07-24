"""
Device API Endpoints
"""
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session, Device, Printer

router = APIRouter()


class DeviceUpdateRequest(BaseModel):
    device_name: Optional[str] = None


@router.get("/", summary="Get all devices")
async def get_devices(
    online_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """Get list of all registered devices"""
    query = select(Device).order_by(Device.created_at.desc())
    if online_only:
        query = query.where(Device.is_online == True)
    result = await session.execute(query)
    devices = result.scalars().all()
    return {"devices": devices}


@router.get("/{device_id}", summary="Get device by ID")
async def get_device(
    device_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get device details, including shared printers"""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # 获取该设备共享的打印机
    printer_result = await session.execute(
        select(Printer).where(Printer.host_device_id == device.id)
    )
    printers = printer_result.scalars().all()

    return {
        "device_id": device.device_id,
        "device_name": device.device_name,
        "device_type": device.device_type,
        "is_online": device.is_online,
        "shared_printers": [
            {"name": p.name, "model": p.model or ""}
            for p in printers
        ],
    }


@router.put("/{device_id}", summary="Update device")
async def update_device(
    device_id: str,
    request: DeviceUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Update device name"""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if request.device_name is not None:
        device.device_name = request.device_name.strip()

    await session.commit()
    await session.refresh(device)
    return device


@router.delete("/{device_id}", summary="Delete a device")
async def delete_device(
    device_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a device and its associated printers"""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Delete associated printers first
    printer_result = await session.execute(
        select(Printer).where(Printer.host_device_id == device.id)
    )
    printers = printer_result.scalars().all()
    deleted_printer_count = len(printers)
    for p in printers:
        await session.delete(p)

    # Delete device
    await session.delete(device)
    await session.commit()

    return {
        "device_id": device_id,
        "status": "deleted",
        "printers_deleted": deleted_printer_count,
    }