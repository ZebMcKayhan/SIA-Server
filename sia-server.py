#!/usr/bin/env python3
from __future__ import annotations
"""
Galaxy SIA Server
Receives, validates, and parses proprietary SIA protocol messages from
Honeywell Galaxy Flex alarm systems. It sends notifications via ntfy.sh.

This server is configured via 'sia-server.conf' and 'configuration.py'.
"""
# --- Application Version ---
__version__ = "2.5.0-beta1"

import argparse
import asyncio
import logging
import logging.handlers
import sys
import signal
import functools
from queue import Queue

# --- SCRIPT INITIALIZATION ---
# Parse command line arguments FIRST, before anything else
parser = argparse.ArgumentParser(description='Galaxy SIA Notification Server')
parser.add_argument(
    '--config',
    default='sia-server.conf',
    help='Path to configuration file (default: sia-server.conf)'
)
args = parser.parse_args()

from configuration import load_logging_config, load_application_config, load_accounts

# Load and validate all configuration from files.
# This single 'config' object now holds all settings for the application.
logging_config = load_logging_config(args.config)

# Define the logging setup function.
def setup_logging(logging_config):
    """Configure logging based on the loaded logging config object."""
    log = logging.getLogger() 
    if log.handlers:
        for handler in log.handlers[:]:
            log.removeHandler(handler)

    log.setLevel(getattr(logging, logging_config.LOG_LEVEL, 'INFO'))

    handler = None

    if logging_config.LOG_TO_SYSLOG:
        if sys.platform == "win32":
            try:
                import win32evtlogutil
                import win32evtlog
                win32evtlogutil.AddSourceToRegistry("SIA-Server", sys.executable)
                handler = logging.handlers.NTEventLogHandler("SIA-Server")
            except ImportError:
                print("WARNING: 'pywin32' not installed. Falling back to screen logging.",
                      file=sys.stderr)
            except Exception as e:
                print("WARNING: Failed to initialize Windows Event Log: %s" % e,
                      file=sys.stderr)
        else:
            try:
                handler = logging.handlers.SysLogHandler(
                    address=logging_config.SYSLOG_SOCKET,
                    facility=logging_config.SYSLOG_FACILITY
                )
            except Exception as e:
                print("WARNING: Could not connect to syslog at %s: %s. Falling back to screen."
                      % (logging_config.SYSLOG_SOCKET, e), file=sys.stderr)

    elif logging_config.LOG_TO_FILE:
        max_bytes = logging_config.LOG_MAX_MB * 1024 * 1024
        handler = logging.handlers.RotatingFileHandler(
            logging_config.LOG_FILE,
            maxBytes=max_bytes,
            backupCount=logging_config.LOG_BACKUP_COUNT
        )

    if handler is None:
        handler = logging.StreamHandler(sys.stderr)

    if isinstance(handler, (logging.handlers.SysLogHandler,
                            logging.handlers.NTEventLogHandler)):
        formatter = logging.Formatter(logging_config.SYSLOG_FORMAT,
                                      datefmt=logging_config.LOG_DATE_FORMAT)
    else:
        formatter = logging.Formatter(logging_config.LOG_FORMAT,
                                      datefmt=logging_config.LOG_DATE_FORMAT)

    handler.setFormatter(formatter)
    log.addHandler(handler)

    if isinstance(handler, logging.handlers.NTEventLogHandler):
        log.info("Logging configured to write to Windows Event Log.")
    elif isinstance(handler, logging.handlers.SysLogHandler):
        log.info("Logging configured to write to system log (Syslog).")
    elif isinstance(handler, logging.handlers.RotatingFileHandler):
        log.info("Logging configured to write to file: %s", logging_config.LOG_FILE)
    else:
        log.info("Logging configured to write to screen (console).")

    return log

# Set up logging immediately after loading logging config.
log = setup_logging(logging_config)
log = logging.getLogger('sia_server')  # change name of local logs
log.info("Logging configured successfully.")
log.info("Using configuration file: %s", args.config)

# Now load the application and account configuration WITH logging available ---
config = load_application_config(args.config)
accounts = load_accounts(args.config)

# Now, import the rest of our modules.
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    log.info("Using uvloop for event loop.")
except ImportError:
    log.info("uvloop not found, using standard asyncio event loop.")
    pass

# --- Optional Encryption Support ---
ENCRYPTION_AVAILABLE = False
START_ENC_HEADER = b'\x05\x01'
CryptoContext = None
do_handshake = None
try:
    from galaxy.encryption import do_handshake, CryptoContext
    ENCRYPTION_AVAILABLE = True
    log.info("INFO: Encryption modules loaded. Encrypted SIA sessions are supported.")
except ModuleNotFoundError:
    log.info("Encryption modules not found. Encrypted sessions will be rejected.")
except ImportError:
    log.info("Encryption modules failed to import. Encrypted sessions will be rejected.")
# ---

from galaxy.protocol import build_block, validate_and_strip, check_block, INCOMPLETE_BLOCK_TIMEOUT, INTER_COMMAND_TIMEOUT
from galaxy.parser import parse_sia_frame, FrameResult, GalaxyEvent
from notification import NotificationDispatcher, enqueue_notification
from galaxy.constants import COMMANDS, COMMAND_BYTES, EVENT_CODE_DESCRIPTIONS

# --- END INITIALIZATION ---

async def build_and_send(writer, command: str, payload: bytes = b'', crypto: CryptoContext | None = None):
    """Builds and sends a valid Galaxy message block."""
    command_byte = COMMAND_BYTES[command]
    final_message = build_block(command_byte, payload)
    
    if crypto:
        log.debug("Encrypting outgoing command: %s", command)
        final_message = crypto.encrypt(final_message)
    
    writer.write(final_message)
    await writer.drain()
    log.debug("Sent Command: %s, Raw: %r", command, final_message)

async def policy_reject(writer, crypto=None):
    """
    Handles a connection rejection according to the configured REJECT_POLICY.
    'respond' - Sends a SIA REJECT frame to the client.
    'drop'    - Silently closes without sending anything.
    """
    if config.REJECT_POLICY == 'respond':
        await build_and_send(writer, 'REJECT', crypto=crypto)
    log.debug("Connection rejected (policy: %s)", config.REJECT_POLICY)
    

async def handle_connection(notification_queue: Queue, reader, writer):
    """Handle an incoming SIA connection."""
    addr = writer.get_extra_info('peername')
    log.debug("Connection from %r", addr)

    crypto = None  # This will hold our CryptoContext object if the session is encrypted
    account_validated = False
    events = []
    buffer          = bytearray()  # TCP reassembly buffer
    
    try:
        while True:
            timeout = INCOMPLETE_BLOCK_TIMEOUT if buffer else INTER_COMMAND_TIMEOUT
            try:
                data = await asyncio.wait_for(reader.read(1024), timeout=timeout)
            except asyncio.TimeoutError:
                if buffer:
                    log.debug("Timeout waiting for complete block from %r", addr)
                else:
                    log.debug("Timeout waiting for next command from %r", addr)
                await policy_reject(writer, crypto)
                return
                
            if not data:
                log.debug("Connection closed by peer")
                break
            # --- encryption detection ---
            if data.startswith(START_ENC_HEADER):
                if ENCRYPTION_AVAILABLE:
                    log.debug("Encrypted header detected from %r", addr)
                    crypto = await do_handshake(reader, writer, data, log)
                    if crypto is None:
                        if config.REJECT_POLICY == 'respond':
                            log.warning("Handshake failed, closing connection")
                        return
                    log.info("Encrypted session established from %r", addr)
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
                    log.error("Required modules for encryption are missing.")
                    log.error("Closing connection to stop panel retries.")
                    log.error("="*60)
                    return            
          
            if crypto:
                data = crypto.decrypt(data)

            command_byte, payload = validate_and_strip(data)
            
            if command_byte is None:
                if len(data) > 0:
                    if config.REJECT_POLICY == 'respond': #only print warning if we respond
                        log.warning("Invalid frame from %r - rejected.", addr)
                    log.debug("Raw: %r", data)
                else:
                    if config.REJECT_POLICY == 'respond': #only print warning if we respond
                        log.warning("Invalid frame, received empty data block, from %r - rejected.", addr)
                await policy_reject(writer, crypto=crypto)
                continue
            
            command_name = COMMANDS.get(command_byte, f'UNKNOWN(0x{command_byte:02x})')
            log.debug("Received Command: %s, Payload: %r", command_name, payload)

            # Parse the frame - parser enforces protocol state machine
            result = parse_sia_frame(
                command_name, payload, events,
                {k: v.site_name for k, v in accounts.accounts.items() if v.site_name is not None},
                EVENT_CODE_DESCRIPTIONS,
                config.UNKNOWN_CHAR_MAP
            )

            if result == FrameResult.FAIL:
                if config.REJECT_POLICY == 'respond':
                    log.warning("Invalid or unexpected frame '%s' from %r - rejected.",
                                command_name, addr)
                await policy_reject(writer, crypto=crypto)
                return

            # Policy check whenever a new account is parsed
            if events and events[-1].account and not account_validated:
                account_number = events[-1].account
                account = accounts.get(account_number)
                policy = account.policy if account else 'yes'
                is_encrypted = crypto is not None
                log.debug("Account '%s' has policy '%s'. Session is encrypted: %s",
                          account_number, policy, is_encrypted)
                if policy == 'no':
                    log.warning("POLICY: Account '%s' is DISABLED. Rejecting connection.", account_number)
                    await policy_reject(writer, crypto=crypto)
                    return
                if policy == 'secure' and not is_encrypted:
                    log.warning("POLICY: Account '%s' requires ENCRYPTED connection but received PLAINTEXT. Rejecting.", account_number)
                    await policy_reject(writer, crypto=crypto)
                    return
                account_validated = True
                log.debug("POLICY: Account '%s' policy satisfied.", account_number)
            
            await build_and_send(writer, 'ACKNOWLEDGE', crypto=crypto)

            if result == FrameResult.END:
                log.debug("End of data received, processing sequence.")
                break

        if not events:
            return
            
        log.info("Found %d event(s) in connection from %s", len(events), addr[0])
        for i, event in enumerate(events, 1):
            log.debug("--- Processing Event %d of %d ---", i, len(events))

            log.info("Site: %s (Account: %s)", event.site_name, event.account)
            description = event.action_text or event.event_description
            event_type_str = f"{event.event_type} " if event.event_type else ""
            log.info("%sEvent: %s (%s)", event_type_str, event.event_code, description)

            enqueue_notification(event, notification_queue)

            log.debug("--- Event %d complete ---", i)

    except (ConnectionResetError, BrokenPipeError):
        log.debug("Client disconnected abruptly (%r)", addr)
        return

    except asyncio.IncompleteReadError:
        log.debug("Client closed connection during read (%r)", addr)
        return

    except Exception as e:
        log.error("Error in connection handler: %s", e, exc_info=True)
    
    finally:
        log.debug("Closing connection from %r", addr)
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError, OSError):
            log.debug("The connection was closed ugly by the client (%r)", addr)
            pass  # Client already closed the connection
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
                line_str = line.decode(errors='replace').strip()
                try:
                    level_name, logger_name, msg = line_str.split(':', 2)
                    log_level = LEVEL_MAP.get(level_name, default_level)
                    subprocess_logger = logging.getLogger(logger_name)
                    subprocess_logger.log(log_level, msg)
                except ValueError:
                    # Fallback for malformed lines
                    log.log(default_level, "[%s] %s", name, line_str)
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
            command = [sys.executable, 'ip_check.py', '--config', args.config]
            log.info("Launching IP Check server as a subprocess: %s", " ".join(command))
            ip_check_process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            ip_check_monitor_task = asyncio.create_task(monitor_subprocess(ip_check_process, 'ip_check.py'))
        except Exception as e:
            log.error("Failed to launch IP Check server subprocess: %s", e)
    
    log.info('='*60)
    
    # Prefer loop-level signal handlers so the finally block (which
    # terminates the IP Check subprocess) always runs on SIGINT/SIGTERM.
    loop = asyncio.get_running_loop()
    serve_task = asyncio.ensure_future(sia_server.serve_forever())

    def _handle_signal(sig):
        log.info("Received signal %s, shutting down...", sig)
        serve_task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s))
        except (NotImplementedError, RuntimeError):
            pass  # Windows: falls back to signal.signal() handlers in main()

    # Run the main SIA server
    try:
        await serve_task
    except asyncio.CancelledError:
        log.info("Server shutdown requested.")
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
        accounts,
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
