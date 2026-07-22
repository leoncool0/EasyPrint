"""
Connection Handler - Handles individual client connection
"""
import asyncio
import logging
from typing import TYPE_CHECKING, Optional
from datetime import datetime
import uuid
import json

from app.models.database import local_now

from app.config import settings
from app.tcp.protocol import (
    MessageType, Frame, ProtocolError,
    decode_frame, encode_frame, create_response, create_request
)
from app.models.database import (
    async_session_maker, Device, Printer, PrintJob
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.tcp.gateway import TCPGateway

logger = logging.getLogger(__name__)


class Connection:
    """Handles a single client connection"""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, gateway: "TCPGateway"):
        self.reader = reader
        self.writer = writer
        self.gateway = gateway

        # Connection info
        self.remote_addr: str = ""
        self.device_id: Optional[str] = None
        self.device_type: Optional[str] = None  # host, user, mixed
        self.token: Optional[str] = None
        self.authenticated: bool = False

        # Buffer for incomplete frames
        self._buffer = b""

        # Heartbeat task
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._last_heartbeat: datetime = local_now()

    async def handle(self):
        """Main connection handler loop"""
        while True:
            try:
                data = await self.reader.read(8192)
                if not data:
                    break

                self._buffer += data

                # Process all complete frames
                while True:
                    try:
                        frame, consumed = decode_frame(self._buffer)
                        self._buffer = self._buffer[consumed:]
                        await self._process_frame(frame)
                    except ProtocolError as e:
                        if "too short" in str(e) or "Incomplete" in str(e):
                            break  # Need more data
                        logger.error(f"Protocol error: {e}")
                        return

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Connection error: {e}")
                break

        # Cleanup
        if self.device_id:
            await self.gateway._mark_device_offline(self.device_id)
            self.gateway.unregister_connection(self.device_id)

    async def _process_frame(self, frame: Frame):
        """Process a received frame"""
        # Update heartbeat time
        self._last_heartbeat = local_now()

        # Route to handler based on message type
        handler = {
            MessageType.HEARTBEAT: self._handle_heartbeat,
            MessageType.AUTH_REQ: self._handle_auth,
            MessageType.HOST_REGISTER: self._handle_host_register,
            MessageType.HOST_UNREGISTER: self._handle_host_unregister,
            MessageType.HOST_STATUS: self._handle_host_status,
            MessageType.USER_LIST_REQ: self._handle_user_list,
            MessageType.JOB_CREATE: self._handle_job_create,
            MessageType.JOB_DATA: self._handle_job_data,
            MessageType.JOB_STATUS: self._handle_job_status,
            MessageType.JOB_CANCEL: self._handle_job_cancel,
        }.get(frame.msg_type)

        if handler:
            try:
                await handler(frame)
            except Exception as e:
                logger.error(f"Handler error for {frame.msg_type}: {e}")
        else:
            logger.warning(f"Unknown message type: {frame.msg_type}")

    async def send(self, data: bytes):
        """Send data to client"""
        self.writer.write(data)
        await self.writer.drain()

    async def close(self):
        """Close the connection"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass

    # ==================== Message Handlers ====================

    async def _handle_heartbeat(self, frame: Frame):
        """Handle heartbeat"""
        response = create_response(MessageType.HEARTBEAT, {"time": local_now().isoformat()})
        await self.send(response)

    async def _handle_auth(self, frame: Frame):
        """Handle authentication request"""
        data = frame.get_payload_json()
        device_id = data.get("device_id")
        device_name = data.get("device_name", "")
        device_type = data.get("device_type", "user")
        os_version = data.get("os_version", "")
        mac_address = data.get("mac_address", "")

        async with async_session_maker() as session:
            # First try to find by device_id
            result = await session.execute(
                select(Device).where(Device.device_id == device_id)
            )
            device = result.scalar_one_or_none()

            # If not found by device_id, try by MAC address (for device_id regeneration)
            if not device and mac_address:
                result = await session.execute(
                    select(Device).where(Device.mac_address == mac_address)
                )
                device = result.scalar_one_or_none()
                # Update device_id if found by MAC
                if device:
                    device.device_id = device_id

            if device:
                # Update existing device
                device.device_name = device_name
                device.device_type = device_type
                device.os_version = os_version
                device.mac_address = mac_address
                device.ip_address = self.remote_addr.split(":")[0]
                device.is_online = True
                device.last_heartbeat = local_now()
                token = device.token
            else:
                # Create new device
                token = str(uuid.uuid4())
                device = Device(
                    device_id=device_id,
                    device_name=device_name,
                    device_type=device_type,
                    os_version=os_version,
                    mac_address=mac_address,
                    ip_address=self.remote_addr.split(":")[0],
                    token=token,
                    is_online=True,
                    last_heartbeat=local_now(),
                )
                session.add(device)

            await session.commit()

        # Store connection info
        self.device_id = device_id
        self.device_type = device_type
        self.token = token
        self.authenticated = True

        # Register with gateway
        self.gateway.register_connection(device_id, self)

        # Send response
        response = create_response(MessageType.AUTH_RSP, {
            "success": True,
            "token": token,
        })
        await self.send(response)
        logger.info(f"Device authenticated: {device_id} ({device_type})")

    async def _handle_host_register(self, frame: Frame):
        """Handle printer registration from host"""
        if not self.authenticated:
            return

        data = frame.get_payload_json()
        printers = data.get("printers", [])

        async with async_session_maker() as session:
            for p in printers:
                printer_id = f"{self.device_id}_{p.get('name', 'printer')}"
                result = await session.execute(
                    select(Printer).where(Printer.printer_id == printer_id)
                )
                printer = result.scalar_one_or_none()

                if printer:
                    printer.name = p.get("name", "")
                    printer.model = p.get("model", "")
                    printer.status = "online"
                    printer.capabilities = json.dumps(p.get("capabilities", {}))
                else:
                    # Get device id
                    result = await session.execute(
                        select(Device.id).where(Device.device_id == self.device_id)
                    )
                    device_db_id = result.scalar_one_or_none()

                    if device_db_id is None:
                        logger.error(f"Device not found when registering printer: {self.device_id}")
                        continue

                    printer = Printer(
                        printer_id=printer_id,
                        name=p.get("name", ""),
                        model=p.get("model", ""),
                        host_device_id=device_db_id,
                        status="online",
                        capabilities=json.dumps(p.get("capabilities", {})),
                    )
                    session.add(printer)

            await session.commit()

        response = create_response(MessageType.HOST_REGISTER, {
            "success": True,
            "printer_count": len(printers),
        })
        await self.send(response)
        logger.info(f"Host registered {len(printers)} printers: {self.device_id}")

    async def _handle_host_unregister(self, frame: Frame):
        """Handle printer unregistration"""
        # TODO: Implement printer unregistration
        pass

    async def _handle_host_status(self, frame: Frame):
        """Handle printer status update"""
        # TODO: Implement status update
        pass

    async def _handle_user_list(self, frame: Frame):
        """Handle printer list request from user"""
        if not self.authenticated:
            return

        async with async_session_maker() as session:
            result = await session.execute(
                select(Printer).where(Printer.status == "online", Printer.is_shared == True)
            )
            printers = result.scalars().all()

            printer_list = []
            for p in printers:
                printer_list.append({
                    "printer_id": p.printer_id,
                    "name": p.name,
                    "model": p.model,
                    "status": p.status,
                })

        response = create_response(MessageType.USER_LIST_RSP, {
            "printers": printer_list,
        })
        await self.send(response)

    async def _handle_job_create(self, frame: Frame):
        """Handle print job creation"""
        if not self.authenticated:
            return

        data = frame.get_payload_json()
        printer_id = data.get("printer_id", "")
        job_name = data.get("job_name", "Print Job")
        file_size = data.get("file_size", 0)

        if not printer_id:
            response = create_response(MessageType.JOB_CREATE, {
                "success": False,
                "error": "printer_id is required",
            })
            await self.send(response)
            return

        async with async_session_maker() as session:
            # 查找目标打印机
            result = await session.execute(
                select(Printer).where(Printer.printer_id == printer_id)
            )
            printer = result.scalar_one_or_none()

            if not printer:
                response = create_response(MessageType.JOB_CREATE, {
                    "success": False,
                    "error": f"Printer not found: {printer_id}",
                })
                await self.send(response)
                return

            # 查找打印机所属的主机端设备
            result = await session.execute(
                select(Device).where(Device.id == printer.host_device_id)
            )
            host_device = result.scalar_one_or_none()

            if not host_device or not host_device.is_online:
                response = create_response(MessageType.JOB_CREATE, {
                    "success": False,
                    "error": f"Host device is offline: {host_device.device_name if host_device else 'Unknown'}",
                })
                await self.send(response)
                return

            # 创建打印任务
            job_uuid = str(uuid.uuid4())
            result = await session.execute(
                select(Device.id).where(Device.device_id == self.device_id)
            )
            user_device_db_id = result.scalar_one()

            print_job = PrintJob(
                job_id=job_uuid,
                printer_id=printer.id,
                user_device_id=user_device_db_id,
                job_name=job_name,
                file_size=file_size,
                status="transferring",
            )
            session.add(print_job)
            await session.commit()

        # 通知主机端有新打印任务
        host_conn = self.gateway.get_connection(host_device.device_id)
        if host_conn:
            job_info = {
                "job_id": job_uuid,
                "printer_id": printer_id,
                "job_name": job_name,
                "file_size": file_size,
            }
            host_message = create_request(MessageType.JOB_CREATE, job_info)
            await host_conn.send(host_message)
            logger.info(f"Forwarded job create to host: {host_device.device_id}")

        # 响应客户端
        response = create_response(MessageType.JOB_CREATE_RSP, {
            "success": True,
            "job_id": job_uuid,
            "printer_name": printer.name,
        })
        await self.send(response)
        logger.info(f"Print job created: {job_uuid} -> {printer_id}")

    async def _handle_job_data(self, frame: Frame):
        """Handle print job data (forward to host)"""
        if not self.authenticated:
            return

        data = frame.get_payload_json()
        job_id = data.get("job_id", "")
        chunk_data = data.get("data", "")
        seq = data.get("seq", 0)
        total = data.get("total", 1)

        if not job_id:
            return

        # 通过 job_id 反查 printer 和 host
        async with async_session_maker() as session:
            result = await session.execute(
                select(PrintJob).where(PrintJob.job_id == job_id)
            )
            print_job = result.scalar_one_or_none()

            if not print_job:
                logger.warning(f"Job not found: {job_id}")
                return

            result = await session.execute(
                select(Printer).where(Printer.id == print_job.printer_id)
            )
            printer = result.scalar_one_or_none()

            if not printer:
                return

            result = await session.execute(
                select(Device).where(Device.id == printer.host_device_id)
            )
            host_device = result.scalar_one_or_none()

            if not host_device:
                return

            # 更新任务状态
            if seq == total - 1:
                print_job.status = "queued"
                await session.commit()

        # 转发数据到主机端
        host_conn = self.gateway.get_connection(host_device.device_id)
        if host_conn:
            forward_data = {
                "job_id": job_id,
                "printer_id": printer.printer_id,
                "data": chunk_data,
                "seq": seq,
                "total": total,
            }
            host_message = create_request(MessageType.JOB_DATA, forward_data)
            await host_conn.send(host_message)
            logger.debug(f"Forwarded job data: {job_id} seq {seq}/{total}")

    async def _handle_job_cancel(self, frame: Frame):
        """Handle job cancellation"""
        if not self.authenticated:
            return

        data = frame.get_payload_json()
        job_id = data.get("job_id", "")

        async with async_session_maker() as session:
            result = await session.execute(
                select(PrintJob).where(PrintJob.job_id == job_id)
            )
            print_job = result.scalar_one_or_none()

            if print_job:
                print_job.status = "cancelled"
                await session.commit()

                # 通知主机端取消任务
                result = await session.execute(
                    select(Printer).where(Printer.id == print_job.printer_id)
                )
                printer = result.scalar_one_or_none()

                if printer:
                    result = await session.execute(
                        select(Device).where(Device.id == printer.host_device_id)
                    )
                    host_device = result.scalar_one_or_none()

                    if host_device:
                        host_conn = self.gateway.get_connection(host_device.device_id)
                        if host_conn:
                            cancel_msg = create_request(MessageType.JOB_CANCEL, {
                                "job_id": job_id,
                            })
                            await host_conn.send(cancel_msg)

        response = create_response(MessageType.JOB_CANCEL, {
            "success": True,
            "job_id": job_id,
        })
        await self.send(response)

    async def _handle_job_status(self, frame: Frame):
        """Handle job status update from host"""
        if not self.authenticated:
            return

        data = frame.get_payload_json()
        job_id = data.get("job_id", "")
        status = data.get("status", "")
        message = data.get("message", "")

        logger.info(f"Job status update: {job_id} -> {status}")

        async with async_session_maker() as session:
            result = await session.execute(
                select(PrintJob).where(PrintJob.job_id == job_id)
            )
            print_job = result.scalar_one_or_none()

            if print_job:
                print_job.status = status
                if message:
                    print_job.error_message = message
                await session.commit()

                # Notify user client of status change
                result = await session.execute(
                    select(Device).where(Device.id == print_job.user_device_id)
                )
                user_device = result.scalar_one_or_none()

                if user_device:
                    user_conn = self.gateway.get_connection(user_device.device_id)
                    if user_conn:
                        status_msg = create_request(MessageType.JOB_STATUS, {
                            "job_id": job_id,
                            "status": status,
                            "message": message,
                        })
                        await user_conn.send(status_msg)