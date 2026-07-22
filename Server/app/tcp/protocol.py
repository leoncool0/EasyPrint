"""
TCP Protocol - Frame Format and Message Types
"""
import struct
import zlib
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional, Tuple
import json


# Magic bytes: 0xE5 0x50 (EasyPrint)
MAGIC = b'\xE5\x50'

# Protocol version
PROTOCOL_VERSION = 0x01


class MessageType(IntEnum):
    """Message type definitions"""
    # Connection
    HEARTBEAT = 0x0001
    AUTH_REQ = 0x0002
    AUTH_RSP = 0x0003

    # Host operations
    HOST_REGISTER = 0x0010
    HOST_UNREGISTER = 0x0011
    HOST_STATUS = 0x0012

    # User operations
    USER_LIST_REQ = 0x0020
    USER_LIST_RSP = 0x0021

    # Job operations
    JOB_CREATE = 0x0030
    JOB_CREATE_RSP = 0x0031
    JOB_DATA = 0x0032
    JOB_DATA_ACK = 0x0033
    JOB_STATUS = 0x0034
    JOB_CANCEL = 0x0035

    # Discovery
    DISCOVER_REQ = 0x0040
    DISCOVER_RSP = 0x0041


class MessageFlag:
    """Message flag bits"""
    IS_RESPONSE = 0x01
    IS_COMPRESSED = 0x02
    IS_BINARY = 0x04


@dataclass
class Frame:
    """Protocol frame structure"""
    version: int
    msg_type: int
    flags: int
    payload: bytes

    @property
    def is_response(self) -> bool:
        return bool(self.flags & MessageFlag.IS_RESPONSE)

    @property
    def is_compressed(self) -> bool:
        return bool(self.flags & MessageFlag.IS_COMPRESSED)

    @property
    def is_binary(self) -> bool:
        return bool(self.flags & MessageFlag.IS_BINARY)

    def get_payload_json(self) -> dict:
        """Get payload as JSON dict"""
        payload = self.payload
        if self.is_compressed:
            payload = zlib.decompress(payload)
        return json.loads(payload.decode('utf-8'))


class ProtocolError(Exception):
    """Protocol error"""
    pass


def encode_frame(
    msg_type: int,
    payload: bytes,
    is_response: bool = False,
    compress: bool = False,
) -> bytes:
    """
    Encode a frame to bytes

    Frame format:
    - Magic: 2 bytes
    - Version: 1 byte
    - Type: 2 bytes
    - Flags: 1 byte
    - Length: 4 bytes
    - Payload: N bytes
    - CRC32: 4 bytes
    """
    flags = 0
    if is_response:
        flags |= MessageFlag.IS_RESPONSE
    if compress:
        payload = zlib.compress(payload)
        flags |= MessageFlag.IS_COMPRESSED

    # Build frame without CRC
    header = struct.pack(
        '>2sBHBI',
        MAGIC,
        PROTOCOL_VERSION,
        msg_type,
        flags,
        len(payload)
    )

    frame_without_crc = header + payload

    # Calculate CRC32
    crc = zlib.crc32(frame_without_crc) & 0xFFFFFFFF
    crc_bytes = struct.pack('>I', crc)

    return frame_without_crc + crc_bytes


def decode_frame(data: bytes) -> Tuple[Frame, int]:
    """
    Decode a frame from bytes

    Returns: (Frame, total_bytes_consumed)
    """
    if len(data) < 14:  # Minimum frame size
        raise ProtocolError("Data too short")

    # Check magic
    if data[:2] != MAGIC:
        raise ProtocolError("Invalid magic bytes")

    # Parse header
    version = data[2]
    msg_type = struct.unpack('>H', data[3:5])[0]
    flags = data[5]
    length = struct.unpack('>I', data[6:10])[0]

    # Check total length
    total_length = 10 + length + 4  # header + payload + crc
    if len(data) < total_length:
        raise ProtocolError("Incomplete frame")

    # Extract payload
    payload = data[10:10 + length]

    # Verify CRC
    expected_crc = struct.unpack('>I', data[10 + length:10 + length + 4])[0]
    actual_crc = zlib.crc32(data[:10 + length]) & 0xFFFFFFFF
    if expected_crc != actual_crc:
        raise ProtocolError("CRC check failed")

    frame = Frame(
        version=version,
        msg_type=msg_type,
        flags=flags,
        payload=payload
    )

    return frame, total_length


def create_response(msg_type: int, data: dict, compress: bool = False) -> bytes:
    """Create a response frame with JSON payload"""
    payload = json.dumps(data).encode('utf-8')
    return encode_frame(msg_type, payload, is_response=True, compress=compress)


def create_request(msg_type: int, data: dict, compress: bool = False) -> bytes:
    """Create a request frame with JSON payload"""
    payload = json.dumps(data).encode('utf-8')
    return encode_frame(msg_type, payload, is_response=False, compress=compress)