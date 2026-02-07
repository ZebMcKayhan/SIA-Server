#!/usr/bin/env python3
"""
Galaxy SIA Server

Receives, validates, and parses proprietary SIA protocol messages from
Honeywell Galaxy Flex alarm systems. It sends notifications via ntfy.sh.

Author: Built with assistance from Claude (Anthropic)
License: MIT
"""

import asyncio
import logging
import logging.handlers
import sys
import signal

# Make uvloop optional for cross-platform compatibility (e.g., Windows)
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("Using uvloop for event loop.")
except ImportError:
    print("uvloop not found, using standard asyncio event loop.")
    pass

import config
from galaxy.parser import parse_galaxy_event
from notification import send_notification
from galaxy.constants import COMMANDS, COMMAND_BYTES

def setup_logging():
    """Configure logging based on config.py settings"""
    log = logging.getLogger()
    if log.handlers:
        return log
    log.setLevel(getattr(logging, config.LOG_LEVEL, 'INFO'))
    formatter = logging.Formatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT)
    if config.LOG_TO_FILE:
        handler = logging.handlers.RotatingFileHandler(
            config.LOG_FILE, maxBytes=config.LOG_MAX_BYTES, backupCount=config.LOG_BACKUP_COUNT
        )
        print(f"Logging to file: {config.LOG_FILE}")
    else:
        handler = logging.StreamHandler(sys.stderr)
        print("Logging to console")
    handler.setFormatter(formatter)
    log.addHandler(handler)
    return log

log = setup_logging()


def validate_and_strip(data: bytes) -> tuple[int, bytes] | tuple[None, None]:
    """
    Validates a raw message block for length and checksum, then strips them.
    Returns the command byte and payload if valid.
    """
    if len(data) < 3:
        log.warning("Invalid block: too short. Raw: %r", data)
        return None, None

    # 1. Validate length
    declared_payload_length = data[0] - 0x40
    actual_payload_length = len(data) - 3
    if declared_payload_length != actual_payload_length:
        log.warning("Block length mismatch! Declared: %d, Actual: %d. Raw: %r",
                    declared_payload_length, actual_payload_length, data)
        return None, None
        
    # 2. Validate checksum
    expected_checksum = data[-1]
    message_to_check = data[:-1]
    
    checksum = 0xFF
    checksum ^= (message_to_check[0] - 0x40) # Use true length
    for byte in message_to_check[1:]:
        checksum ^= byte
        
    if checksum != expected_checksum:
        log.warning("Checksum mismatch! Calculated: 0x%02x, Expected: 0x%02x. Raw: %r",
                    checksum, expected_checksum, data)
        return None, None

    # Block is valid. Strip and return.
    command_byte = data[1]
    payload = data[2:-1]
    
    return command_byte, payload


async def build_and_send(writer, command: str, payload: bytes = b''):
    """
    Builds a valid Galaxy message block and sends it.
    Calculates length and checksum automatically.
    """
    command_byte = COMMAND_BYTES[command]
    
    payload_length = len(payload)
    length_byte = payload_length + 0x40
    
    message_part = bytes([length_byte, command_byte]) + payload
    
    checksum = 0xFF
    checksum ^= (message_part[0] - 0x40) # True length
    for byte in message_part[1:]:
        checksum ^= byte
        
    final_message = message_part + bytes([checksum])
    
    writer.write(final_message)
    await writer.drain()
    log.debug("Sent Command: %s, Raw: %r", command, final_message)


async def handle_connection(reader, writer):
    """
    Handle incoming connection, validate blocks, and process events.
    """
    addr = writer.get_extra_info('peername')
    log.info("Connection from %r", addr)
    
    valid_blocks = []
    
    try:
        while True:
            data = await reader.read(1024)
            if not data:
                log.info("Connection closed by peer")
                break
            
            command_byte, payload = validate_and_strip(data)
            
            if command_byte is None:
                await build_and_send(writer, 'REJECT')
                log.error("Received invalid block, sent REJECT. Raw: %r", data)
                continue

            command_name = COMMANDS.get(command_byte, f'UNKNOWN(0x{command_byte:02x})')
            log.info("Received Command: %s, Payload: %r", command_name, payload)
            
            valid_blocks.append({'command': command_name, 'payload': payload})

            await build_and_send(writer, 'ACKNOWLEDGE')
            
            if command_name == 'END_OF_DATA':
                log.info("End of data received, processing sequence.")
                break
        
        # --- Chunk and process the collected valid blocks ---
        if not valid_blocks:
            return
            
        event_chunks = []
        current_chunk = []
        
        for block in valid_blocks:
            if block['command'] == 'ACCOUNT_ID' and current_chunk:
                event_chunks.append(current_chunk)
                current_chunk = [block]
            else:
                current_chunk.append(block)
        
        if current_chunk:
            event_chunks.append(current_chunk)
        
        log.info("Found %d distinct event(s) in this connection", len(event_chunks))

        for i, chunk in enumerate(event_chunks, 1):
            log.info("--- Processing Event %d of %d ---", i, len(event_chunks))
            
            event = parse_galaxy_event(
                chunk,
                config.ACCOUNT_SITES,
                config.DEFAULT_SITE,
                config.UNKNOWN_CHAR_MAP
            )
            
            log.info("Site: %s (Account: %s)", event.site_name, event.account)
            log.info("Event Code: %s, Action: %s", event.event_code, event.action_text)
            
            send_notification(
                event,
                config.NTFY_URL,
                config.EVENT_PRIORITIES,
                config.DEFAULT_PRIORITY,
                config.NTFY_ENABLED,
                config.NOTIFICATION_TITLE
            )
            
            log.info("--- Event %d complete ---", i)

    except Exception as e:
        log.error("Error in connection handler: %s", e, exc_info=True)
    finally:
        log.info("Closing connection from %r", addr)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            log.error("Error closing connection: %s", e)


async def start_server(address, port):
    server = await asyncio.start_server(handle_connection, address, port)
    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    log.info('='*60)
    log.info('Galaxy SIA Server Started')
    log.info('Listening on: %s', addrs)
    log.info('='*60)
    async with server:
        await server.serve_forever()


def handle_shutdown(signum, frame):
    log.info("Received shutdown signal (%d), stopping server...", signum)
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    log.info("Starting Galaxy SIA Server...")
    
    try:
        asyncio.run(start_server(config.LISTEN_ADDR, config.LISTEN_PORT))
    except (KeyboardInterrupt, SystemExit):
        log.info("Server stopped")
    except Exception as e:
        log.error("Server error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
