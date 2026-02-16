#!/usr/bin/env python3
"""
Galaxy SIA Server

Receives, validates, and parses proprietary SIA protocol messages from
Honeywell Galaxy Flex alarm systems. It sends notifications via ntfy.sh.

Author: Built with assistance from Claude (Anthropic)
License: MIT
"""
# --- Application Version ---
__version__ = "1.4.0-beta"

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
from galaxy.constants import COMMANDS, COMMAND_BYTES, EVENT_CODE_DESCRIPTIONS

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
    for byte in message_to_check:
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
    for byte in message_part:
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
                is_encrypted_handshake = False
                if len(data) >= 2 and data[0:2] == b'\x05\x01':
                    is_encrypted_handshake = True

                if is_encrypted_handshake:
                    # --- SPECIAL HANDLING FOR ENCRYPTED HANDSHAKE ---
                    log.error("="*60)
                    log.error("ENCRYPTION DETECTED - UNSUPPORTED")
                    log.error("The panel at IP address '%s' has encryption enabled.", addr[0])
                    log.error("This server does not support the proprietary encryption.")
                    log.error("Please disable encryption in the panel's SIA settings.")
                    log.error("Closing connection to stop the panel from retrying.")
                    log.error("Raw block received: %r", data)
                    log.error("="*60)
                    
                    # Do not send anything back. Just break the loop.
                    # The 'finally' block will close the connection.
                    break 

                else:
                    # --- STANDARD HANDLING FOR CORRUPTED DATA ---
                    if len(data) > 0:
                        log.error("Validation failed (length or checksum error). Raw: %r", data)
                    else:
                        log.error("Validation failed (received empty data block).")

                    # Send a standard unencrypted REJECT.
                    await build_and_send(writer, 'REJECT')
                    continue # Continue to listen for more data on this connection if any.

            command_name = COMMANDS.get(command_byte, f'UNKNOWN(0x{command_byte:02x})')
            log.info("Received Command: %s, Payload: %r", command_name, payload)

            if command_name != 'END_OF_DATA':
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
                config.UNKNOWN_CHAR_MAP,
                EVENT_CODE_DESCRIPTIONS
            )
            
            log.info("Site: %s (Account: %s)", event.site_name, event.account)
            description = event.action_text or event.event_description
            log.info("Event: %s (%s)", event.event_code, description)
            
            send_notification(
                event,
                config.NTFY_TOPICS,
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


async def monitor_subprocess(process, name):
    """Monitors a subprocess, parses its log level, and logs its output."""
    log.info("Monitoring subprocess '%s' (PID: %d)", name, process.pid)
    
    # Map level names to logging constants
    LEVEL_MAP = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }

    async def log_stream(stream, default_level):
        while not stream.at_eof():
            line = await stream.readline()
            if line:
                line_str = line.decode().strip()
                
                # Check for our "LEVEL:message" format
                parts = line_str.split(':', 1)
                if len(parts) == 2 and parts[0] in LEVEL_MAP:
                    # We found a log level prefix
                    level_name = parts[0]
                    msg = parts[1].strip()
                    log_level = LEVEL_MAP[level_name]
                else:
                    # It's a plain message with no level, use the default
                    msg = line_str
                    log_level = default_level
                
                log.log(log_level, "[%s] %s", name, msg)

    await asyncio.gather(
        log_stream(process.stdout, logging.INFO),
        log_stream(process.stderr, logging.ERROR)
    )
    
    await process.wait()
    log.warning("Subprocess '%s' (PID: %d) has exited with code %d.", name, process.pid, process.returncode)


# In sia-server.py

async def start_servers():
    """Starts the main SIA server and launches the IP Check server as a subprocess."""
    
    # --- Start the main SIA Event Server ---
    sia_server = await asyncio.start_server(
        handle_connection, config.LISTEN_ADDR, config.LISTEN_PORT
    )
    sia_addrs = ', '.join(str(sock.getsockname()) for sock in sia_server.sockets)
    log.info('='*60)
    log.info('Galaxy SIA Event Server Started')
    log.info('Listening for events on: %s', sia_addrs)
    
    # --- Launch the optional IP Check Server as a Subprocess ---
    ip_check_process = None
    if config.IP_CHECK_ENABLED:
        try:
            command = [sys.executable, 'ip_check.py']
            log.info("Launching IP Check server as a subprocess: %s", " ".join(command))
            
            ip_check_process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Create a task to monitor the subprocess in the background
            asyncio.create_task(monitor_subprocess(ip_check_process, 'ip_check.py'))
            
        except Exception as e:
            log.error("Failed to launch IP Check server subprocess: %s", e)
    
    log.info('='*60)
    
    # Run the main SIA server forever
    try:
        await sia_server.serve_forever()
    finally:
        # When the main server is shut down, also terminate the subprocess
        if ip_check_process and ip_check_process.returncode is None:
            log.info("Terminating IP Check server subprocess...")
            ip_check_process.terminate()
            await ip_check_process.wait() # Wait for it to be truly gone
            log.info("IP Check subprocess terminated.")


def handle_shutdown(signum, frame):
    log.info("Received shutdown signal (%d), stopping server...", signum)
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    log.info("Starting Galaxy SIA Server version %s", __version__)
    
    try:
        asyncio.run(start_servers())
                
    except (KeyboardInterrupt, SystemExit):
        log.info("Server stopped")
    except Exception as e:
        log.error("Server error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
