"""
Network Connection - TCP connection handler
"""
import asyncio
import logging
import json
import struct
import zlib
from typing import Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# Magic bytes
MAGIC = b'\xE5\x50'
PROTOCOL_VERSION = 0x01


class NetworkConnection:
    """Handles TCP connection to server"""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False

        # Buffer for incomplete frames
        self._buffer = b""

        # Callbacks
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_message: Optional[Callable] = None

        # Background task
        self._receive_task: Optional[asyncio.Task] = None

    async def connect(self):
        """Connect to server"""
        try:
            self.reader, self.writer = await asyncio.open_connection(
                self.host, self.port
            )
            self.connected = True
            logger.info(f"Connected to {self.host}:{self.port}")

            # Start receiving
            self._receive_task = asyncio.create_task(self._receive_loop())

            if self.on_connected:
                self.on_connected()

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

    async def disconnect(self):
        """Disconnect from server"""
        self.connected = False

        if self._receive_task:
            self._receive_task.cancel()

        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

        logger.info("Disconnected")

    async def _receive_loop(self):
        """Receive loop"""
        while self.connected:
            try:
                data = await self.reader.read(8192)
                if not data:
                    break

                self._buffer += data

                # Process complete frames
                while len(self._buffer) >= 14:
                    frame, consumed = self._decode_frame(self._buffer)
                    if frame is None:
                        break

                    self._buffer = self._buffer[consumed:]
                    self._handle_frame(frame)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Receive error: {e}")
                break

        self.connected = False
        if self.on_disconnected:
            self.on_disconnected()

    def _decode_frame(self, data: bytes):
        """Decode a frame from buffer"""
        if len(data) < 14:
            return None, 0

        if data[:2] != MAGIC:
            return None, 0

        msg_type = struct.unpack('>H', data[3:5])[0]
        flags = data[5]
        length = struct.unpack('>I', data[6:10])[0]
        total_length = 10 + length + 4

        if len(data) < total_length:
            return None, 0

        # Verify CRC
        expected_crc = struct.unpack('>I', data[10 + length:10 + length + 4])[0]
        actual_crc = zlib.crc32(data[:10 + length]) & 0xFFFFFFFF

        if expected_crc != actual_crc:
            logger.error("CRC check failed")
            return None, total_length

        payload = data[10:10 + length]

        # Decompress if needed
        if flags & 0x02:
            payload = zlib.decompress(payload)

        # Parse JSON
        try:
            data_json = json.loads(payload.decode('utf-8'))
        except:
            data_json = {}

        return {"type": msg_type, "flags": flags, "data": data_json}, total_length

    def _handle_frame(self, frame: dict):
        """Handle received frame"""
        if self.on_message:
            self.on_message(frame["type"], frame["data"])

    async def _send_frame(self, msg_type: int, data: dict, is_response: bool = False):
        """Send a frame"""
        payload = json.dumps(data).encode('utf-8')

        flags = 0
        if is_response:
            flags |= 0x01

        header = struct.pack(
            '>2sBHBI',
            MAGIC,
            PROTOCOL_VERSION,
            msg_type,
            flags,
            len(payload)
        )

        frame_without_crc = header + payload
        crc = zlib.crc32(frame_without_crc) & 0xFFFFFFFF
        crc_bytes = struct.pack('>I', crc)

        self.writer.write(frame_without_crc + crc_bytes)
        await self.writer.drain()

    # ==================== Message Senders ====================

    async def send_auth(self, device_id: str, device_name: str, device_type: str,
                        os_version: str = "", mac_address: str = ""):
        """Send authentication request"""
        await self._send_frame(0x0002, {
            "device_id": device_id,
            "device_name": device_name,
            "device_type": device_type,
            "os_version": os_version,
            "mac_address": mac_address,
        })

    async def send_heartbeat(self):
        """Send heartbeat"""
        await self._send_frame(0x0001, {"time": ""})

    async def send_host_register(self, printers: list):
        """Send printer registration"""
        await self._send_frame(0x0010, {"printers": printers})

    async def send_user_list_request(self):
        """Send printer list request"""
        await self._send_frame(0x0020, {})

    async def send_job_create(self, printer_id: str, file_path: str, params: dict):
        """Send job creation request"""
        await self._send_frame(0x0030, {
            "printer_id": printer_id,
            "file_path": file_path,
            "params": params,
        })

    async def send_job_data(self, job_id: str, data: bytes, seq: int, total: int):
        """Send job data chunk"""
        import base64
        data_base64 = base64.b64encode(data).decode('utf-8')
        await self._send_frame(0x0032, {
            "job_id": job_id,
            "data": data_base64,
            "seq": seq,
            "total": total,
        })

    async def send_job_cancel(self, job_id: str):
        """Send job cancel request"""
        await self._send_frame(0x0035, {"job_id": job_id})

    async def send_job_status(self, job_id: str, status: str, message: str = ""):
        """Send job status update (host -> server)"""
        payload = {"job_id": job_id, "status": status}
        if message:
            payload["message"] = message
        await self._send_frame(0x0034, payload)