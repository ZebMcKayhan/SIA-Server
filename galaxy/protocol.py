"""
Galaxy SIA Protocol framing helpers.

Single source of truth for the low-level block format:

    [length_byte][command_byte][payload...][checksum]

where length_byte = 0x40 + len(payload) and checksum is the XOR of 0xFF
with every preceding byte of the block.

Used by sia-server.py, ip_check.py and the test suite so the checksum
and framing logic is implemented exactly once.
"""
from __future__ import annotations

from typing import Optional, Tuple

# Framing constants
LENGTH_OFFSET  = 0x40
HEADER_SIZE    = 2          # length byte + command byte
CHECKSUM_SIZE  = 1
MIN_BLOCK_SIZE = HEADER_SIZE + CHECKSUM_SIZE   # 3 bytes minimum
MAX_PAYLOAD    = 0xFF - LENGTH_OFFSET          # 191 bytes maximum


def xor_checksum(data: bytes) -> int:
    """
    XOR checksum used by the Galaxy SIA protocol.
    Seed is 0xFF, XOR'd with every byte in data.
    """
    checksum = 0xFF
    for byte in data:
        checksum ^= byte
    return checksum


def build_block(command_byte: int, payload: bytes = b'') -> bytes:
    """
    Build a complete, checksummed SIA block.

    Args:
        command_byte: The command byte identifying the block type.
        payload:      The block payload (default empty).

    Returns:
        A complete block ready to send:
        [length_byte][command_byte][payload...][checksum]

    Raises:
        ValueError: If the payload exceeds the maximum allowed size.
    """
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(
            f"Payload too long ({len(payload)} bytes); "
            f"maximum is {MAX_PAYLOAD} bytes."
        )
    message = bytes([LENGTH_OFFSET + len(payload), command_byte]) + payload
    return message + bytes([xor_checksum(message)])


def validate_and_strip(block: bytes) -> Tuple[Optional[int], Optional[bytes]]:
    """
    Validates a complete raw SIA block and returns the command byte and payload.

    Args:
        block: The raw block bytes to validate.

    Returns:
        (command_byte, payload) if the block is valid.
        (None, None) if the block is malformed (wrong length or bad checksum).
    """
    if len(block) < MIN_BLOCK_SIZE:
        return None, None

    declared_payload_length = block[0] - LENGTH_OFFSET
    if declared_payload_length < 0 or declared_payload_length > MAX_PAYLOAD:
        return None, None

    expected_size = declared_payload_length + MIN_BLOCK_SIZE
    if expected_size != len(block):
        return None, None

    if xor_checksum(block[:-1]) != block[-1]:
        return None, None

    return block[1], block[2:-1]
