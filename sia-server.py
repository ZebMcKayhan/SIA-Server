#!/usr/bin/env python3
"""
Galaxy SIA Server
Receives, validates, and parses proprietary SIA protocol messages from
Honeywell Galaxy Flex alarm systems. It sends notifications via ntfy.sh.

This server is configured via 'sia-server.conf' and 'configuration.py'.
"""
# --- Application Version ---
__version__ = "2.0.0-beta"

import asyncio
import logging
import logging.handlers
import sys
import signal
import functools
from queue import Queue

# --- SCRIPT INITIALIZATION ---

# Import the new configuration loader FIRST.
from configuration import load_and_validate_config

# Load and validate all configuration from files.
# This single 'config' object now holds all settings for the application.
config = load_and_validate_config()

# Define the logging setup function.
def setup_logging():
    """Configure logging based on the loaded config object."""
    log = logging.getLogger()
    if log.handlers:
        for handler in log.handlers[:]:
            log.removeHandler(handler)
    
    log.setLevel(getattr(logging, config.LOG_LEVEL, 'INFO'))
    
    handler = None
    
    if config.LOG_TO_SYSLOG: 
        if sys.platform == "win32":
            try:
                import win32evtlogutil
                import win32evtlog 
                # Next, attempt to register the application as an event source.
                # This is the step that requires Administrator rights and can fail.
                # We do this explicitly to get a clear error instead of a hang.
                win32evtlogutil.AddSourceToRegistry("SIA-Server", sys.executable)
                # If the above succeeded, we can create the handler.
                handler = logging.handlers.NTEventLogHandler("SIA-Server")
            except ImportError:
                # The library is not installed at all.
                print("WARNING: The 'pywin32' package is required for Windows Event Log logging but is not installed.", file=sys.stderr)
                print("WARNING: Please run 'python -m pip install pywin32' to enable this feature.", file=sys.stderr)
                print("WARNING: Falling back to screen logging.", file=sys.stderr)
            except Exception as e:     
                # This will catch permission errors if not run as admin.
                print("WARNING: Failed to initialize Windows Event Log handler: %s" % e, file=sys.stderr)
                print("WARNING: This may require running the script as an Administrator once to register the source.", file=sys.stderr)
                print("WARNING: Falling back to screen logging.", file=sys.stderr)
                            
        else: # Linux/Unix Syslog
            try:
                handler = logging.handlers.SysLogHandler(
                    address=config.SYSLOG_SOCKET,
                    facility=config.SYSLOG_FACILITY
                )
            except Exception as e:
                print("WARNING: Could not connect to syslog at %s: %s." % (config.SYSLOG_SOCKET, e), file=sys.stderr)
                print("WARNING: Falling back to screen logging.", file=sys.stderr)

    elif config.LOG_TO_FILE:
        # --- File Logging ---
        log.info("Logging configured to write to file: %s", config.LOG_FILE)
        max_bytes = config.LOG_MAX_MB * 1024 * 1024
        handler = logging.handlers.RotatingFileHandler(
            config.LOG_FILE, 
            maxBytes=max_bytes, 
            backupCount=config.LOG_BACKUP_COUNT
        )

    # If all else fails, or if 'Screen' was chosen, use the screen handler.
    if handler is None:
        log.info("Logging configured to write to screen (console).")
        handler = logging.StreamHandler(sys.stderr)

    
    if isinstance(handler, (logging.handlers.SysLogHandler, logging.handlers.NTEventLogHandler)):
        # For Syslog, use the user-configurable SYSLOG_FORMAT:
        formatter = logging.Formatter(config.SYSLOG_FORMAT, datefmt=config.LOG_DATE_FORMAT)
    else:
        # For File and Screen, use the user-configurable full format.
        formatter = logging.Formatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT)
    
    handler.setFormatter(formatter)
    log.addHandler(handler)
    if isinstance(handler, logging.handlers.NTEventLogHandler):
        log.info("Logging configured to write to Windows Event Log.")
    elif isinstance(handler, logging.handlers.SysLogHandler):
        log.info("Logging configured to write to system log (Syslog).")
    elif isinstance(handler, logging.handlers.RotatingFileHandler):
        log.info("Logging configured to write to file: %s", config.LOG_FILE)
    else:
        log.info("Logging configured to write to screen (console).")
    
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

# --- Optional Encryption Support ---
ENCRYPTION_AVAILABLE = False
try:
    from galaxy.encryption import do_handshake, CryptoContext, START_ENC_HEADER
    # Also check for the heavy dependency to be safe
    from Cryptodome.PublicKey import RSA
    ENCRYPTION_AVAILABLE = True
    # We will initialize the logger later, so we use print for this early message.
    log.info("INFO: Encryption modules loaded. Encrypted SIA sessions are supported.")
except ImportError:
    # Define dummy placeholders so the server can run without the encryption feature.
    CryptoContext = None
    do_handshake = None
    START_ENC_HEADER = b'\x05\x01' # Hardcooded as galaxy.encryption wasnt loaded.
    log.info("WARNING: Encryption modules not found (e.g., pycryptodome). Encrypted sessions will be rejected.")
# ---

from galaxy.parser import parse_galaxy_event
from notification import NotificationDispatcher, enqueue_notification
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


async def build_and_send(writer, command: str, payload: bytes = b'', crypto: CryptoContext | None = None):
    """Builds and sends a valid Galaxy message block."""
    command_byte = COMMAND_BYTES[command]
    payload_length = len(payload)
    length_byte = payload_length + 0x40
    message_part = bytes([length_byte, command_byte]) + payload
    checksum = 0xFF
    for byte in message_part:
        checksum ^= byte
    final_message = message_part + bytes([checksum])
    
    if crypto:
        log.debug("Encrypting outgoing command: %s", command)
        final_message = crypto.encrypt(final_message)
    
    writer.write(final_message)
    await writer.drain()
    log.debug("Sent Command: %s, Raw: %r", command, final_message)


async def handle_connection(notification_queue: Queue, reader, writer):
    """Handle an incoming SIA connection."""
    addr = writer.get_extra_info('peername')
    log.info("Connection from %r", addr)

    crypto = None  # This will hold our CryptoContext object if the session is encrypted
    valid_blocks = []
    
    try:
        while True:
            data = await reader.read(1024)
            if not data:
                log.info("Connection closed by peer")
                break
            # --- encryption detection ---
            if data.startswith(START_ENC_HEADER):
                if ENCRYPTION_AVAILABLE:
                    log.info("Encrypted session detected from %r", addr)
                    crypto = await do_handshake(reader, writer, data, log)
                    if crypto is None:
                        log.warning("Handshake failed, closing connection")
                        return
                    # Handshake successful, now wait for the first real SIA message.
                    data = await reader.read(1024)
                    if not data:
                        log.info("Connection closed after handshake")
                        return
                else: 
                    # This block runs if encryption is detected but not supported.
                    log.error("="*60)
                    log.error("ENCRYPTION DETECTED - UNSUPPORTED")
                    log.error("The panel at IP address '%s' has encryption enabled.", addr[0])
                    log.error("Required modules are missing. Please install 'pycryptodome'.")
                    log.error("Closing connection to stop panel retries.")
                    log.error("="*60)
                    return            
          
            if crypto:
                data = crypto.decrypt(data)

            command_byte, payload = validate_and_strip(data)
            
            if command_byte is None:
                    if len(data) > 0:
                        log.error("Validation failed (length or checksum error). Raw: %r", data)
                    else:
                        log.error("Validation failed (received empty data block).")
                    await build_and_send(writer, 'REJECT', crypto=crypto)
                    continue
            
            command_name = COMMANDS.get(command_byte, f'UNKNOWN(0x{command_byte:02x})')
            log.debug("Received Command: %s, Payload: %r", command_name, payload)

            # --- ACCOUNT POLICY ENFORCEMENT ---
            # Validate account_id if according to policy
            if command_name == 'ACCOUNT_ID':
                account_number = payload.decode(errors='ignore')
                
                # Look up the policy. Fall back to 'default', then to 'yes'.
                policy = config.ACCOUNT_POLICIES.get(
                    account_number,
                    config.ACCOUNT_POLICIES.get('default', 'yes')
                )
                
                is_encrypted = crypto is not None
                log.debug("Account '%s' has policy '%s'. Session is encrypted: %s",
                          account_number, policy, is_encrypted)
                # Policy: 'no' - This account is completely disabled.
                if policy == 'no':
                    log.warning("POLICY: Account '%s' is DISABLED. Rejecting connection.", account_number)
                    await build_and_send(writer, 'REJECT', crypto=crypto)
                    return
                # Policy: 'secure' - This account requires an encrypted session.
                if policy == 'secure' and not is_encrypted:
                    log.warning("POLICY: Account '%s' requires ENCRYPTED connection but received PLAINTEXT. Rejecting.", account_number)
                    await build_and_send(writer, 'REJECT', crypto=crypto)
                    return
                # If we reach here, the policy is satisfied.
                log.debug("POLICY: Account '%s' policy satisfied.", account_number)
            
            if command_name != 'END_OF_DATA':
                valid_blocks.append({'command': command_name, 'payload': payload})
            await build_and_send(writer, 'ACKNOWLEDGE', crypto=crypto)
            
            if command_name == 'END_OF_DATA':
                log.debug("End of data received, processing sequence.")
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
            log.debug("--- Processing Event %d of %d ---", i, len(event_chunks))
            
            event = parse_galaxy_event(
                chunk,
                config.ACCOUNT_SITES,
                config.UNKNOWN_CHAR_MAP,
                EVENT_CODE_DESCRIPTIONS
            )
            
            log.info("Site: %s (Account: %s)", event.site_name, event.account)
            description = event.action_text or event.event_description
            log.info("Event: %s (%s)", event.event_code, description)
            
            # Send the notification to our que:
            enqueue_notification(event, notification_queue)
            
            log.debug("--- Event %d complete ---", i)
    except Exception as e:
        log.error("Error in connection handler: %s", e, exc_info=True)
    finally:
        log.debug("Closing connection from %r", addr)
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

async def start_servers(notification_queue: Queue):
    """Starts the main SIA server and launches the IP Check server as a subprocess."""
    
    try:
        handler_with_queue = functools.partial(handle_connection, notification_queue)
        # --- Start the main SIA Event Server ---
        sia_server = await asyncio.start_server(
            handler_with_queue, config.LISTEN_ADDR, config.LISTEN_PORT
        )
        sia_addrs = ', '.join(str(sock.getsockname()) for sock in sia_server.sockets)
        log.info('='*60)
        log.info('Galaxy SIA Event Server Started')
        log.info('Listening for events on: %s', sia_addrs)
    except OSError as e:
        if "Address already in use" in str(e):
            log.critical("STARTUP FAILED: The port %d is already in use.", config.LISTEN_PORT)
        elif "Cannot assign requested address" in str(e) or "could not bind" in str(e):
            log.critical("STARTUP FAILED: The IP address '%s' is not valid for this machine.", config.LISTEN_ADDR)
            log.critical("Please use '0.0.0.0' or a specific IP address that this server owns.")
        elif "getaddrinfo failed" in str(e):
            log.critical("STARTUP FAILED: The address '%s' is not a valid IP address or hostname.", config.LISTEN_ADDR)
            log.critical("Please check for typos in your sia-server.conf file.")
        else:
            log.critical("A critical OS error occurred starting the SIA server: %s", e)
        
        log.critical("="*60)
        # We must return here to stop the program from continuing.
        raise # this triggers the OSError in the main loop

    # --- Launch the optional IP Check Server as a Subprocess ---
    ip_check_process = None
    ip_check_monitor_task = None
    if config.IP_CHECK_ENABLED:
        try:
            command = [sys.executable, 'ip_check.py']
            log.info("Launching IP Check server as a subprocess: %s", " ".join(command))
            ip_check_process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            ip_check_monitor_task = asyncio.create_task(monitor_subprocess(ip_check_process, 'ip_check.py'))
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
            await ip_check_process.wait()
            log.info("IP Check subprocess terminated.")

def handle_shutdown(signum, frame):
    log.info("Received shutdown signal (%d), stopping server...", signum)
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    log.info("Starting Galaxy SIA Server version %s", __version__)

    notification_queue = Queue(maxsize=config.MAX_QUEUE_SIZE)
    dispatcher = NotificationDispatcher(
        notification_queue,
        config.NTFY_TOPICS,
        config.EVENT_PRIORITIES,
        config.DEFAULT_PRIORITY,
        config.MAX_RETRIES,
        config.MAX_RETRY_TIME
    )
    dispatcher.start()
    
    exit_code = 0 # Assume success
    try:
        asyncio.run(start_servers(notification_queue))
    except (KeyboardInterrupt, SystemExit):
        log.info("Server stopped")
    except OSError as e:
        # OSError raised by start_servers, no need for additional logging.
        exit_code = 1
    except Exception as e:
        # This will now only catch very unexpected errors.
        log.critical("A critical server error occurred: %s", e, exc_info=True)
        exit_code = 1
    finally:
        # This block ensures the dispatcher is stopped when the server exits for any reason.
        log.info("Shutting down notification dispatcher...")
        dispatcher.stop()   # Signals the thread's loop to exit
        dispatcher.join()   # Waits for the thread to finish cleanly
        log.info("Notification dispatcher stopped.")
    
    sys.exit(exit_code)
    
if __name__ == '__main__':
    main()
