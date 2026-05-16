#!/usr/bin/env python3
"""
Galaxy IP Check (Heartbeat) Server

Listens on a dedicated port for the proprietary Honeywell "Path Viability Check"
ping. It echoes the received data back to the panel and closes the connection.
This script is intended to be run as a subprocess by sia-server.py.
"""

import argparse
import asyncio
import logging
import sys
import time
import datetime
from queue import Queue

# --- Watchdog Configuration ---
PANEL_EPOCH_OFFSET = 54000  # 15 hours - converts panel timestamp to local time
WATCHDOG_THRESHOLD = 2.1    # Allow 1 missed ping + buffer

# --- SCRIPT INITIALIZATION ---
# 1. Parse arguments
parser = argparse.ArgumentParser(description='Galaxy IP Check Server')
parser.add_argument(
    '--config',
    default='sia-server.conf',
    help='Path to configuration file (default: sia-server.conf)'
)
args = parser.parse_args()

# 2. Import configuration loader
from configuration import load_logging_config, load_full_config

# 3. Load ONLY logging config first 
logging_config = load_logging_config(args.config)

# --- Logging Setup for Subprocess ---
# 4. Configure the ROOT logger so all modules (including notification.py)
# automatically inherit the same handler and format.
# Format transports level, logger name and message to sia-server.py for formatting.
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, logging_config.LOG_LEVEL, 'INFO'))
root_logger.handlers.clear()
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
root_logger.addHandler(handler)

log = logging.getLogger('ip_check')

# 5. NOW load full config - logging is ready so all warnings/errors are captured
config = load_full_config(args.config)

# 6. Now, import the rest of our modules.
from notification import NotificationDispatcher, enqueue_message_notification
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass # uvloop is optional

# --- Optional Encryption Support ---
ENCRYPTION_AVAILABLE = False
START_ENC_HEADER = b'\x05\x01'
CryptoContext = None
do_handshake = None
try:
    from galaxy.encryption import do_handshake, CryptoContext, START_ENC_HEADER
    ENCRYPTION_AVAILABLE = True
    log.debug("Encryption modules loaded.")
except (ImportError, ModuleNotFoundError):
    pass
    
# --- END INITIALIZATION ---

# Watchdog state per account
# { account: { 'state': 'UNKNOWN'|'CONNECTED'|'DISCONNECTED',
#              'last_seen': float,      # server time (time.time())
#              'last_panel_time': str,  # formatted panel local time
#              'interval': int } }      # seconds
watchdog_state = {}

def panel_timestamp_to_str(data: bytes) -> str:
    """Extract and format panel timestamp from IP Check packet bytes 15-18."""
    ts = data[15] + data[16]*256 + data[17]*65536 + data[18]*16777216
    unix_ts = ts + PANEL_EPOCH_OFFSET
    return datetime.datetime.fromtimestamp(
        unix_ts, datetime.timezone.utc
    ).strftime('%Y-%m-%d %H:%M')

def update_watchdog(account_number: str, site_name: str,
                    data: bytes, notification_queue: Queue):
    """
    Update watchdog state when a valid ping is received.
    Called from handle_ip_check() after successful validation.
    """
    panel_time = panel_timestamp_to_str(data)
    interval = data[20] + data[21]*256 + data[22]*65536 + data[23]*16777216
    hours = interval // 3600
    minutes = (interval % 3600) // 60
    seconds = interval % 60
    interval_str = f"{hours:02d}:{minutes:02d}:{seconds:02d} ({interval}s)"

    current_state = watchdog_state.get(account_number, {}).get('state', 'UNKNOWN')
    previous_interval = watchdog_state.get(account_number, {}).get('interval', interval)

    # Always update state to CONNECTED with latest values
    watchdog_state[account_number] = {
        'state': 'CONNECTED',
        'last_seen': time.time(),
        'last_panel_time': panel_time,
        'interval': interval,
    }

    if current_state == 'DISCONNECTED':
        # Connection restored!
        log.info("Watchdog: Site: %s (Account: %s) - connection restored, "
                 "interval %s.", site_name, account_number, interval_str)
        enqueue_message_notification(
            account_number,
            site_name,
            f"Heartbeat received at {panel_time}, connection restored",
            priority=2,
            queue=notification_queue
        )
    elif current_state == 'UNKNOWN':
        # First ping ever - silent transition, just log
        log.info("Watchdog: Site: %s (Account: %s) - monitoring started, "
                 "interval %s.", site_name, account_number, interval_str)
    else:
        # CONNECTED → CONNECTED: check if interval changed
        if previous_interval != interval:
            log.info("Watchdog: Site: %s (Account: %s) - interval updated to %s.",
                     site_name, account_number, interval_str)

async def watchdog_task(notification_queue: Queue):
    """
    Async task that checks for missed heartbeats every minute.
    Started alongside the ip_check server.
    """
    log.debug("Watchdog task started.")
    while True:
        await asyncio.sleep(60)

        now = time.time()
        for account_number, state in list(watchdog_state.items()):
            if state['state'] != 'CONNECTED':
                continue

            interval = state['interval']
            if not interval:
                continue

            elapsed = now - state['last_seen']
            threshold = interval * WATCHDOG_THRESHOLD

            if elapsed > threshold:
                # Connection lost!
                watchdog_state[account_number]['state'] = 'DISCONNECTED'
                last_panel_time = state['last_panel_time']
                site_name = config.ACCOUNT_SITES.get(account_number, account_number)
                # Format elapsed time as hh:mm:ss
                elapsed_int = int(elapsed)
                e_hours = elapsed_int // 3600
                e_minutes = (elapsed_int % 3600) // 60
                e_seconds = elapsed_int % 60
                
                log.warning("Watchdog: Site: %s (Account: %s) - heartbeat lost! "
                           "No ping received for %02d:%02d:%02d.",
                           site_name, account_number, e_hours, e_minutes, e_seconds)

                enqueue_message_notification(
                    account_number,
                    site_name,
                    f"Heartbeat lost, last heartbeat received was {last_panel_time}",
                    priority=4,
                    queue=notification_queue
                )

def validate_ip_check_packet(data: bytes) -> bool:
    """
    Validates an incoming IP Check packet.
    Returns True if the packet is valid, False otherwise.
    
    Validation checks:
    1. Length must be exactly 26 bytes
    2. First byte (header) must be 0x00
    3. Checksum - algorithm unknown, not validated
    """
    # Check 1: Length
    if len(data) != 26:
        log.debug("IP Check: Invalid length %d (expected 26)", len(data))
        return False
    
    # Check 2: Header byte
    if data[0] != 0x00:
        log.debug("IP Check: Invalid header byte 0x%02x (expected 0x00)", data[0])
        return False
    
    # Check 3: checksum

    # Algo unknown...
    
    return True

def extract_account(data: bytes) -> str:
    """Extract account number from IP Check packet bytes 1-8."""
    return data[1:9].decode('ascii', errors='ignore').lstrip('0')
    
async def handle_ip_check(reader, writer, notification_queue: Queue):
    """Handles an incoming IP Check connection by echoing the received data."""
    addr = writer.get_extra_info('peername')
    crypto = None
    
    try:
        data = await reader.read(1024)
        if not data:
            return

        # --- Encryption detection ---
        if data.startswith(START_ENC_HEADER):
            if ENCRYPTION_AVAILABLE:
                log.debug("Encrypted header detected from %s", addr[0])
                crypto = await do_handshake(reader, writer, data, log)
                if crypto is None:
                    log.debug("IP Check handshake failed from %s - ignored.", addr[0])
                    return
                # Read the actual ping after handshake
                log.info("Encrypted session established from %r", addr)
                data = await reader.read(1024)
                if not data:
                    return
            else:
                log.warning("Encrypted session requested from %s but encryption not available - ignored.", addr[0])
                return

        # Decrypt if encrypted session
        if crypto:
            data = crypto.decrypt(data)
            
        log.debug("Ping HEX: %s", data.hex())
        # Validate the packet before responding
        if not validate_ip_check_packet(data):
            log.debug("Invalid IP Check packet from %s - ignored.", addr[0])
            return  # Silent drop

        # --- ACCOUNT POLICY ENFORCEMENT ---
        account_number = extract_account(data)
        policy = config.ACCOUNT_POLICIES.get(
            account_number,
            config.ACCOUNT_POLICIES.get('default', 'yes')
        )
        is_encrypted = crypto is not None

        if policy == 'no':
            log.warning("IP Check from disabled account '%s' - ignored.", account_number)
            return

        if policy == 'secure' and not is_encrypted:
            log.warning("IP Check from '%s' requires encrypted connection - ignored.", account_number)
            return

        log.debug("IP Check account '%s' policy satisfied.", account_number)
        site_name = config.ACCOUNT_SITES.get(account_number, account_number)
        update_watchdog(account_number, site_name, data, notification_queue)
        
        log.info("Received ping from site: %s (Account: %s) from %s. Echoing response.",
                 site_name, account_number, addr[0])

        response = crypto.encrypt(data) if crypto else data
        # Echo the exact same data back to the panel.
        writer.write(response)
        await writer.drain()

        # Wait for the panel to close the connection.
        # Note: The panel closes the connection after 15s:
        await reader.read(-1)
        log.debug("Panel at %r has closed the connection.", addr)

    except asyncio.IncompleteReadError:
        log.debug("Panel at %r has closed the connection (IncompleteReadError).", addr)
    except (ConnectionResetError, BrokenPipeError):
        log.debug("Client disconnected abruptly (%r)", addr)    
    except Exception as e:
        log.error("Error in IP Check handler for %s: %s", addr[0], e)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass  # Client already closed the connection
        except Exception:
            pass

async def start_ip_check_server(): # Renamed from 'main' to be an async function
    """The main async function to start the server."""
    
    if not config.IP_CHECK_ENABLED:
        if sys.stdout.isatty():
            # This print is for when a user tries to run it directly while disabled
            print("IP Check server is disabled in sia-server.conf. Exiting.")
        return

    # --- Start notification dispatcher ---
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
    
    log.info("="*50)
    log.info("Starting Galaxy IP Check (Heartbeat) Server")
    
    # We move the try...except block here, inside the async function
    try:
        server = await asyncio.start_server(
            lambda r, w: handle_ip_check(r, w, notification_queue),
            config.IP_CHECK_ADDR,
            config.IP_CHECK_PORT
        )
    except OSError as e:
        # This is the same robust error handling from the main server
        if "Address already in use" in str(e):
            log.critical("STARTUP FAILED: The port %d is already in use.", config.IP_CHECK_PORT)
        elif "Cannot assign requested address" in str(e) or "could not bind" in str(e):
            log.critical("STARTUP FAILED: The IP address '%s' is not valid for this machine.", config.IP_CHECK_ADDR)
        elif "getaddrinfo failed" in str(e):
            log.critical("STARTUP FAILED: The address '%s' is not a valid IP address or hostname.", config.IP_CHECK_ADDR)
        else:
            log.critical("A critical OS error occurred starting the IP Check server: %s", e)
        log.critical("="*50)
        dispatcher.stop()
        dispatcher.join()        
        return # Gracefully exit the async function

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    log.info('Listening for heartbeats on: %s', addrs)
    log.info("="*50)

    async with server:
        asyncio.create_task(watchdog_task(notification_queue))
        await server.serve_forever()


if __name__ == '__main__':
    # The main execution block is now just a simple try...except wrapper
    try:
        asyncio.run(start_ip_check_server())
    except (KeyboardInterrupt, SystemExit):
        log.info("IP Check server stopped.")
