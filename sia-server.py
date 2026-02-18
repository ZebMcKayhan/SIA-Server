#!/usr/bin/env python3
"""
Galaxy SIA Server
Receives, validates, and parses proprietary SIA protocol messages from
Honeywell Galaxy Flex alarm systems. It sends notifications via ntfy.sh.

This server is configured via 'sia-server.conf' and 'defaults.py'.
"""
# --- Application Version ---
__version__ = "1.6.0-beta"

import asyncio
import logging
import logging.handlers
import sys
import signal

# --- SCRIPT INITIALIZATION ---

# 1. Import the new configuration loader FIRST.
from configuration import load_and_validate_config

# 2. Load and validate all configuration from files.
# This single 'config' object now holds all settings for the application.
config = load_and_validate_config()

# 3. Define the logging setup function.
def setup_logging():
    """Configure logging based on the loaded config object."""
    log = logging.getLogger()
    if log.handlers:
        return log
    log.setLevel(getattr(logging, config.LOG_LEVEL, 'INFO'))
    formatter = logging.Formatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT)
    if config.LOG_TO_FILE:
        handler = logging.handlers.RotatingFileHandler(
            config.LOG_FILE, maxBytes=config.LOG_MAX_BYTES, backupCount=config.LOG_BACKUP_COUNT
        )
    else:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    log.addHandler(handler)
    return log

# 4. Set up the logger.
log = setup_logging()
log.info("Logging configured successfully.")

# 5. Now, import the rest of our modules.
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    log.info("Using uvloop for event loop.")
except ImportError:
    log.info("uvloop not found, using standard asyncio event loop.")
    pass

from galaxy.parser import parse_galaxy_event
from notification import send_notification
from galaxy.constants import COMMANDS, COMMAND_BYTES, EVENT_CODE_DESCRIPTIONS

# --- END INITIALIZATION ---


def validate_and_strip(data: bytes) -> tuple[int, bytes] | tuple[None, None]:
    """Validates a raw message block and returns the command byte and payload."""
    if len(data) < 3:
        log.warning("Invalid block: too short. Raw: %r", data)
        return None, None
    declared_payload_length = data[0] - 0x40
    actual_payload_length = len(data) - 3
    if declared_payload_length != actual_payload_length:
        log.warning("Block length mismatch! Declared: %d, Actual: %d. Raw: %r",
                    declared_payload_length, actual_payload_length, data)
        return None, None
    expected_checksum = data[-1]
    message_to_check = data[:-1]
    checksum = 0xFF
    for byte in message_to_check:
        checksum ^= byte
    if checksum != expected_checksum:
        log.warning("Checksum mismatch! Calculated: 0x%02x, Expected: 0x%02x. Raw: %r",
                    checksum, expected_checksum, data)
        return None, None
    command_byte = data[1]
    payload = data[2:-1]
    return command_byte, payload


async def build_and_send(writer, command: str, payload: bytes = b''):
    """Builds and sends a valid Galaxy message block."""
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
    """Handle an incoming SIA connection."""
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
                if len(data) >= 2 and data[0:2] == b'\x05\x01':
                    log.error("="*60)
                    log.error("ENCRYPTION DETECTED - UNSUPPORTED")
                    log.error("The panel at IP address '%s' has encryption enabled.", addr[0])
                    log.error("Closing connection to stop the panel from retrying.")
                    log.error("Raw block received: %r", data)
                    log.error("="*60)
                    break 
                else:
                    if len(data) > 0:
                        log.error("Validation failed (length or checksum error). Raw: %r", data)
                    else:
                        log.error("Validation failed (received empty data block).")
                    await build_and_send(writer, 'REJECT')
                    continue
            
            command_name = COMMANDS.get(command_byte, f'UNKNOWN(0x{command_byte:02x})')
            log.info("Received Command: %s, Payload: %r", command_name, payload)
            if command_name != 'END_OF_DATA':
                valid_blocks.append({'command': command_name, 'payload': payload})
            await build_and_send(writer, 'ACKNOWLEDGE')
            
            if command_name == 'END_OF_DATA':
                log.info("End of data received, processing sequence.")
                break
        
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
            
            # This call is now simpler
            send_notification(
                event,
                config.NTFY_TOPICS,
                config.EVENT_PRIORITIES,
                config.DEFAULT_PRIORITY
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
    LEVEL_MAP = {'DEBUG': logging.DEBUG, 'INFO': logging.INFO, 'WARNING': logging.WARNING, 'ERROR': logging.ERROR, 'CRITICAL': logging.CRITICAL}
    async def log_stream(stream, default_level):
        while not stream.at_eof():
            line = await stream.readline()
            if line:
                line_str = line.decode().strip()
                parts = line_str.split(':', 1)
                if len(parts) == 2 and parts[0] in LEVEL_MAP:
                    level_name, msg = parts[0], parts[1].strip()
                    log_level = LEVEL_MAP[level_name]
                else:
                    msg, log_level = line_str, default_level
                log.log(log_level, "[%s] %s", name, msg)
    await asyncio.gather(log_stream(process.stdout, logging.INFO), log_stream(process.stderr, logging.ERROR))
    await process.wait()
    log.warning("Subprocess '%s' (PID: %d) has exited with code %d.", name, process.pid, process.returncode)

async def start_servers():
    """Starts the main SIA server and launches the IP Check server as a subprocess."""
    sia_server = await asyncio.start_server(
        handle_connection, config.LISTEN_ADDR, config.LISTEN_PORT
    )
    sia_addrs = ', '.join(str(sock.getsockname()) for sock in sia_server.sockets)
    log.info('='*60)
    log.info('Galaxy SIA Event Server Started')
    log.info('Listening for events on: %s', sia_addrs)
    
    ip_check_process = None
    if config.IP_CHECK_ENABLED:
        try:
            command = [sys.executable, 'ip_check.py']
            log.info("Launching IP Check server as a subprocess: %s", " ".join(command))
            ip_check_process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            asyncio.create_task(monitor_subprocess(ip_check_process, 'ip_check.py'))
        except Exception as e:
            log.error("Failed to launch IP Check server subprocess: %s", e)
    
    log.info('='*60)
    
    try:
        await sia_server.serve_forever()
    finally:
        if ip_check_process and ip_check_process.returncode is None:
            log.info("Terminating IP Check server subprocess...")
            ip_check_process.terminate()
            await ip_check_process.wait()
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
