"""
TCP Gateway - Main TCP server handling client connections
"""
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

from app.config import settings
from app.models.database import local_now
from app.tcp.protocol import (
    MessageType, Frame, ProtocolError,
    decode_frame, encode_frame, create_response
)
from app.tcp.connection import Connection
from app.models.database import async_session_maker, Device, Printer

logger = logging.getLogger(__name__)


class TCPGateway:
    """TCP Gateway server"""

    def __init__(self):
        self.server: Optional[asyncio.Server] = None
        self.connections: Dict[str, Connection] = {}  # device_id -> Connection
        self._running = False
        self._heartbeat_check_task: Optional[asyncio.Task] = None

    async def start(self, host: str, port: int):
        """Start the TCP server"""
        self.server = await asyncio.start_server(
            self._handle_connection,
            host,
            port,
        )
        self._running = True

        addr = self.server.sockets[0].getsockname()
        logger.info(f"TCP Gateway listening on {addr[0]}:{addr[1]}")

        # Start heartbeat check task
        self._heartbeat_check_task = asyncio.create_task(self._heartbeat_check())

        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        """Stop the TCP server"""
        self._running = False
        
        if self._heartbeat_check_task:
            self._heartbeat_check_task.cancel()
        
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # Close all connections
        for conn in list(self.connections.values()):
            await conn.close()

        logger.info("TCP Gateway stopped")

    async def _heartbeat_check(self):
        """Periodically check for offline devices"""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                timeout = timedelta(seconds=settings.HEARTBEAT_TIMEOUT)
                now = local_now()

                for device_id, conn in list(self.connections.items()):
                    if now - conn._last_heartbeat > timeout:
                        logger.warning(f"Device timeout: {device_id}")
                        # Mark as offline in database
                        await self._mark_device_offline(device_id)
                        # Force close connection to release coroutine
                        await conn.close()
                        self.unregister_connection(device_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat check error: {e}")

    async def _mark_device_offline(self, device_id: str):
        """Mark device and its printers as offline in database"""
        async with async_session_maker() as session:
            # Mark device offline
            await session.execute(
                Device.__table__.update().where(Device.device_id == device_id)
                .values(is_online=False)
            )
            # Mark associated printers offline
            await session.execute(
                Printer.__table__.update().where(Printer.printer_id.like(f"{device_id}_%"))
                .values(status="offline")
            )
            await session.commit()

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a new client connection"""
        addr = writer.get_extra_info('peername')
        logger.info(f"New connection from {addr}")

        connection = Connection(reader, writer, self)
        connection.remote_addr = f"{addr[0]}:{addr[1]}"

        try:
            await connection.handle()
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            logger.info(f"Connection closed: {addr}")
            # Mark device as offline when connection closes
            if connection.device_id:
                await self._mark_device_offline(connection.device_id)
                self.unregister_connection(connection.device_id)

    def register_connection(self, device_id: str, connection: Connection):
        """Register a connection by device_id"""
        self.connections[device_id] = connection
        logger.info(f"Device registered: {device_id}")

    def unregister_connection(self, device_id: str):
        """Unregister a connection"""
        if device_id in self.connections:
            del self.connections[device_id]
            logger.info(f"Device unregistered: {device_id}")

    def get_connection(self, device_id: str) -> Optional[Connection]:
        """Get a connection by device_id"""
        return self.connections.get(device_id)

    async def broadcast_to_host(self, message: bytes):
        """Broadcast a message to all host connections"""
        for conn in self.connections.values():
            if conn.device_type in ("host", "mixed"):
                await conn.send(message)

    async def send_to_device(self, device_id: str, message: bytes):
        """Send a message to a specific device"""
        conn = self.connections.get(device_id)
        if conn:
            await conn.send(message)
        else:
            logger.warning(f"Device not found: {device_id}")