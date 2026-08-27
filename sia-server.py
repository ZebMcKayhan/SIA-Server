#!/usr/bin/env python3
from __future__ import annotations
"""
Galaxy SIA Server
Receives, validates, and parses proprietary SIA protocol messages from
Honeywell Galaxy Flex alarm systems. It sends notifications via ntfy.sh.

This server is configured via 'sia-server.conf' and 'configuration.py'.
"""
# --- Application Version ---
__version__ = "2.7.0-beta_5"  #

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

from configuration import load_logging_config, load_application_config, load_accounts, load_log_level

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
    enc_version = getattr(sys.modules.get('galaxy.encryption'), '__version__', None)
    log.info("Encryption modules loaded (version %s). Encrypted SIA sessions are supported.", enc_version)
except ModuleNotFoundError:
    log.info("Encryption modules not found. Encrypted sessions will be rejected.")
except ImportError:
    log.info("Encryption modules failed to import. Encrypted sessions will be rejected.")
except Exception as e:
    log.info("Encryption modules failed to load: %s. Encrypted sessions will be rejected.", e)
# ---

from galaxy.protocol import build_block, validate_and_strip, check_block, INCOMPLETE_BLOCK_TIMEOUT, INTER_COMMAND_TIMEOUT
from galaxy.parser import parse_sia_frame, FrameResult, GalaxyEvent
from notification import NotificationDispatcher, enqueue_notification
from galaxy.constants import COMMANDS, COMMAND_BYTES, EVENT_CODE_DESCRIPTIONS
import ip_check

VALID_COMMANDS = set(COMMANDS.keys())

_serve_task = None   # Current serve task, cancelled to trigger shutdown
_event_loop = None   # The running event loop; used by signal handlers to call_soon_threadsafe
_dispatcher = None   # Reference to NotificationDispatcher for SIGHUP reload

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
    buffer = bytearray()  # TCP reassembly buffer
    
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

            buffer.extend(data)
            # We need at least 2 bytes to detect anything meaningful
            if len(buffer) < 2:
                log.debug("Only 1 byte in buffer from %r, waiting for more.", addr)
                continue
            
            # --- encryption detection ---
            if crypto is None and buffer.startswith(START_ENC_HEADER):
                if len(buffer) < 5:
                    log.debug("Encrypted header incomplete from %r, waiting for more.", addr)
                    continue
                if ENCRYPTION_AVAILABLE:
                    log.debug("Encrypted header detected from %r", addr)
                    crypto = await do_handshake(reader, writer, bytes(buffer), log)
                    if crypto is None:
                        if config.REJECT_POLICY == 'respond':
                            log.warning("Handshake failed, closing connection")
                        return
                    log.info("Encrypted session established from %r", addr)
                    # Handshake successful, now wait for the first real SIA message.
                    buffer.clear()
                    continue
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
                data = crypto.decrypt(bytes(buffer))
                if not data:
                    log.debug("Incomplete encrypted block from %r, waiting for more.", addr)
                    continue
            else:
                data = bytes(buffer) # make a copy rather than reference

            command_ok, expected_len, received_len = check_block(data, VALID_COMMANDS)

            if not command_ok:
                if config.REJECT_POLICY == 'respond':
                    log.warning("Invalid frame header from %r - rejected. "
                                "Buffer: %r", addr, bytes(buffer))
                else:
                    log.debug("Invalid frame header from %r - rejected. "
                              "Buffer: %r", addr, bytes(buffer))
                await policy_reject(writer, crypto)
                return

            if received_len > expected_len:
                if config.REJECT_POLICY == 'respond':
                    log.warning("Protocol violation from %r: expected %d bytes, got %d. "
                                "Buffer: %r", addr, expected_len, received_len, bytes(buffer))
                else:
                    log.debug("Protocol violation from %r: expected %d bytes, got %d. "
                              "Buffer: %r", addr, expected_len, received_len, bytes(buffer))
                await policy_reject(writer, crypto)
                return

            if received_len < expected_len:
                log.debug("Incomplete block from %r: have %d/%d bytes",
                          addr, received_len, expected_len)
                continue

            buffer.clear()
            
            command_byte, payload = validate_and_strip(data)
            
            if command_byte is None:
                if config.REJECT_POLICY == 'respond':
                    log.warning("Bad checksum or malformed block from %r - rejected. "
                                "Raw: %r", addr, data)
                else:
                    log.debug("Bad checksum or malformed block from %r - rejected. "
                                "Raw: %r", addr, data)
                await policy_reject(writer, crypto)
                return
            
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
                else:
                     log.debug("Invalid or unexpected frame '%s' from %r - rejected.",
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

async def start_servers(notification_queue: Queue):
    """Starts the main SIA Event Server and the IP Check Service each if enabled."""

    # --- Exit early if nothing is enabled ---
    if not config.SIA_SERVER_ENABLED and not config.IP_CHECK_ENABLED:
        log.warning("Both SIA Event Server and IP Check Service are disabled. Nothing to do, exiting.")
        return
        
    sia_server = None
    
    # --- Start the optional SIA Event Server ---
    if config.SIA_SERVER_ENABLED:
        try:
            handler_with_queue = functools.partial(handle_connection, notification_queue)
            sia_server = await asyncio.start_server(
                handler_with_queue, config.LISTEN_ADDR, config.LISTEN_PORT
            )
            sia_addrs = ', '.join(str(sock.getsockname()) for sock in sia_server.sockets)
            log.info('='*60)
            log.info('Galaxy SIA Event Server Started')
            log.info('Listening for events on: %s', sia_addrs)
            log.info('='*60)
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
                log.critical("A critical OS error occurred starting the SIA Event Server: %s", e)
            log.critical("="*60)
            raise

    # --- Start the optional IP Check Service ---
    if config.IP_CHECK_ENABLED:
        try:
            ip_check.init(config, accounts)
            handler = functools.partial(ip_check.handle_ip_check,
                                        notification_queue=notification_queue)
            ip_check_server = await asyncio.start_server(
                handler, config.IP_CHECK_ADDR, config.IP_CHECK_PORT
            )
            ip_check_addrs = ', '.join(str(sock.getsockname()) for sock in ip_check_server.sockets)
            log.info('='*60)
            log.info('IP Check Service Started')
            log.info('Listening for heartbeats on: %s', ip_check_addrs)
            log.info('='*60)
            asyncio.create_task(ip_check.watchdog_task(notification_queue))
        except OSError as e:
            log.warning("IP Check Service failed to start: %s. Continuing without it.", e)

    global _serve_task, _event_loop
    loop = asyncio.get_running_loop()
    _event_loop = loop

    if sia_server:
        serve_task = asyncio.ensure_future(sia_server.serve_forever())
        _serve_task = serve_task
    else:
        # Only IP Check is running — keep alive with a never-completing future
        serve_task = loop.create_future()
        _serve_task = serve_task

    # Register asyncio-native signal handlers (Linux/macOS only).
    # On Windows loop.add_signal_handler raises NotImplementedError; we fall
    # back to the signal.signal handlers registered in main() instead.
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                functools.partial(_cancel_serve_task, sig)
            )
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await serve_task
    except asyncio.CancelledError:
        log.info("Server shutdown requested.")
        
def _cancel_serve_task(sig):
    """Cancel the serve task from any context (loop callback or signal handler)."""
    log.info("Received signal %s, shutting down...", sig)
    if _serve_task is not None:
        _serve_task.cancel()

def handle_shutdown(signum, frame):
    """Synchronous signal handler (fallback for Windows / pre-loop signals).

    signal.signal() handlers run in the main thread outside the asyncio event
    loop, so it is NOT safe to call asyncio objects directly from here.
    We use call_soon_threadsafe() to schedule the cancellation on the loop.
    If the loop is not yet running (very early signal), we exit immediately.
    """
    if _event_loop is not None and _event_loop.is_running():
        _event_loop.call_soon_threadsafe(
            functools.partial(_cancel_serve_task, signum)
        )
    else:
        sys.exit(0)  # Loop not started yet — nothing to cancel

def _apply_sighup_reload(new_level: str, new_accounts):
    """
    Apply a reloaded configuration. Must run on the event loop thread so that
    mutations to shared asyncio state (ip_check.accounts) are never interleaved
    with a running coroutine (e.g. watchdog_task).
    Scheduled via call_soon_threadsafe from handle_sighup.
    """
    global accounts

    # Apply log level
    logging.getLogger().setLevel(getattr(logging, new_level, logging.INFO))
    log.info("Log level set to %s.", new_level)

    # Apply accounts — safe here because we are between coroutine steps
    accounts = new_accounts
    ip_check.accounts = new_accounts
    if _dispatcher:
        _dispatcher.reload_accounts(new_accounts)
    log.info("SIGHUP reload complete.")

def handle_sighup(signum, frame):
    """Synchronous SIGHUP handler.

    File I/O (reading the config) is done here in the signal handler because
    it does not touch any asyncio or shared mutable state.
    The actual mutations are then scheduled on the event loop via
    call_soon_threadsafe so they run between coroutine steps, not inside one.
    """
    log.info("Received SIGHUP signal. Reloading configuration...")

    # Heavy I/O — safe to do here, no shared state touched yet
    new_level   = load_log_level(args.config)
    new_accounts = load_accounts(args.config)

    if _event_loop is not None and _event_loop.is_running():
        _event_loop.call_soon_threadsafe(
            functools.partial(_apply_sighup_reload, new_level, new_accounts)
        )
    else:
        # Loop not running yet — apply directly (startup edge case)
        _apply_sighup_reload(new_level, new_accounts)
def main():
    # Register synchronous signal handlers as a baseline.
    # On Linux/macOS these will be overridden by loop.add_signal_handler()
    # once the event loop starts (inside start_servers). On Windows,
    # loop.add_signal_handler is not supported so these remain active and use
    # call_soon_threadsafe to interact with the loop safely.
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, handle_sighup)
    log.info("Starting Galaxy SIA Server version %s", __version__)

    global _dispatcher
    notification_queue = Queue(maxsize=config.MAX_QUEUE_SIZE)
    dispatcher = NotificationDispatcher(
        notification_queue,
        accounts,
        config.EVENT_PRIORITIES,
        config.DEFAULT_PRIORITY,
        config.MAX_RETRIES,
        config.MAX_RETRY_TIME,
        config.NOTIFICATION_FORMAT_ASCII,
        config.NOTIFICATION_FORMAT_DATA,
    )
    _dispatcher = dispatcher
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
