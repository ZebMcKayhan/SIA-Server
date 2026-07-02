#!/usr/bin/env python3
"""
Galaxy IP Check (Heartbeat) Server

Handles the proprietary Honeywell "Path Viability Check" heartbeat protocol.
Intended to be imported and run as part of sia-server.py.
"""

import asyncio
import logging
import time
import datetime
from queue import Queue
from typing import Optional, Tuple

from galaxy.protocol import INCOMPLETE_BLOCK_TIMEOUT, INTER_COMMAND_TIMEOUT
from notification import enqueue_message_notification

# --- Watchdog Configuration ---
PANEL_EPOCH_OFFSET = 54000  # 15 hours - converts panel timestamp to local time

# --- Module-level config and accounts, set by init() ---
config = None
accounts = None

log = logging.getLogger('ip_check')

def init(cfg, accts):
    """Initialise the IP Check module with shared config and accounts."""
    global config, accounts
    config = cfg
    accounts = accts

# Watchdog state per account
# { account: { 'state': 'UNKNOWN'|'CONNECTED'|'DISCONNECTED'|'DISABLED',
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

    new_state = 'DISABLED' if config.IP_CHECK_WATCHDOG <= 1.0 else 'CONNECTED'
    watchdog_state[account_number] = {
        'state': new_state,
        'last_seen': time.time(),
        'last_panel_time': panel_time,
        'interval': interval,
    }

    if current_state == 'DISCONNECTED':
        # Connection restored - only reachable if watchdog was previously enabled
        log.info("Watchdog: Site: %s (Account: %s) - connection restored, "
                 "interval %s.", site_name, account_number, interval_str)
        enqueue_message_notification(
            account_number,
            site_name,
            f"Heartbeat received at {panel_time}, connection restored",
            priority=config.IP_CHECK_RESTORE_PRIO,
            queue=notification_queue
        )
    elif current_state == 'UNKNOWN':
        # First ping ever - log monitoring started or disabled
        if config.IP_CHECK_WATCHDOG <= 1.0:
            log.info("Watchdog: Site: %s (Account: %s) - watchdog DISABLED, "
                     "interval %s.", site_name, account_number, interval_str)
        else:
            log.info("Watchdog: Site: %s (Account: %s) - monitoring started, "
                     "interval %s.", site_name, account_number, interval_str)
    else:
        # CONNECTED/DISABLED -> CONNECTED/DISABLED: check if interval changed
        if previous_interval != interval:
            log.info("Watchdog: Site: %s (Account: %s) - interval updated to %s.",
                     site_name, account_number, interval_str)

async def watchdog_task(notification_queue: Queue):
    """
    Async task that checks for missed heartbeats every minute.
    Started alongside the IP Check server.
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
            threshold = interval * config.IP_CHECK_WATCHDOG

            if elapsed > threshold:
                # Connection lost!
                watchdog_state[account_number]['state'] = 'DISCONNECTED'
                last_panel_time = state['last_panel_time']
                site_name = accounts.get(account_number).site_name if accounts.get(account_number) else account_number
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
                    priority=config.IP_CHECK_LOST_PRIO,
                    queue=notification_queue
                )

def validate_ip_check_packet(data: bytes) -> Tuple[bool, Optional[int], int]:
    """
    Inspect the buffer to determine if it looks like a valid IP Check packet.
    
    Returns:
        (valid_header, expected_len, received_len) where:
        - valid_header:  True if header byte looks valid
        - expected_len:  Always 26 (or None if header invalid)
        - received_len:  How many bytes are currently in the buffer

    Callers should:
        - If not valid_header → drop connection
        - If received_len < expected_len → wait for more data
        - If received_len > expected_len → protocol violation, drop
        - If received_len == expected_len → process the packet
    """
    received = len(data)

    if received < 1:
        return False, None, received

    if data[0] != 0x00:
        log.debug("IP Check: Invalid header byte 0x%02x (expected 0x00)", data[0])
        return False, None, received

    return True, 26, received

def extract_account(data: bytes) -> str:
    """Extract account number from IP Check packet bytes 1-8."""
    return data[1:9].decode('ascii', errors='ignore').lstrip('0') or '0'

async def handle_ip_check(reader, writer, notification_queue: Queue,
                          crypto_available: bool, start_enc_header: bytes,
                          do_handshake, crypto_context):
    """Handles an incoming IP Check connection by echoing the received data."""
    addr = writer.get_extra_info('peername')
    crypto = None
    buffer = bytearray()  # TCP reassembly buffer

    try:
        while True:
            timeout = INCOMPLETE_BLOCK_TIMEOUT if buffer else INTER_COMMAND_TIMEOUT
            try:
                data = await asyncio.wait_for(reader.read(1024), timeout=timeout)
            except asyncio.TimeoutError:
                if buffer:
                    log.debug("Timeout waiting for complete IP Check packet from %r", addr)
                else:
                    log.debug("Timeout waiting for IP Check packet from %r", addr)
                return

            if not data:
                log.debug("Connection closed by peer %r", addr)
                return

            buffer.extend(data)

            # We need at least 2 bytes to detect anything meaningful
            if len(buffer) < 2:
                log.debug("Only 1 byte in buffer from %r, waiting for more.", addr)
                continue

            # --- Encryption detection ---
            if crypto is None and buffer.startswith(start_enc_header):
                if len(buffer) < 5:
                    log.debug("Encrypted header incomplete from %r, waiting for more.", addr)
                    continue
                if crypto_available:
                    log.debug("Encrypted header detected from %s", addr[0])
                    crypto = await do_handshake(reader, writer, bytes(buffer), log)
                    if crypto is None:
                        log.debug("IP Check handshake failed from %s - ignored.", addr[0])
                        return
                    log.debug("Encrypted session established from %r", addr)
                    buffer.clear()
                    continue
                else:
                    log.warning("Encrypted session requested from %s but encryption not available - ignored.", addr[0])
                    return

            # Decrypt if encrypted session
            if crypto:
                data = crypto.decrypt(bytes(buffer))
                if not data:
                    log.debug("Incomplete encrypted packet from %r, waiting for more.", addr)
                    continue
            else:
                data = bytes(buffer)

            log.debug("Ping HEX: %s", data.hex())

            # Validate the packet before responding
            valid_header, expected_len, received_len = validate_ip_check_packet(data)
            if not valid_header:
                log.debug("Invalid IP Check packet from %r - ignored.", addr)
                return
            if received_len < expected_len:
                log.debug("Incomplete IP Check packet from %r: have %d/26 bytes",
                          addr, received_len)
                continue
            if received_len > expected_len:
                log.debug("Oversized IP Check packet from %r: got %d bytes, expected 26. "
                          "Ignoring.", addr, received_len)
                return

            buffer.clear()

            # --- ACCOUNT POLICY ENFORCEMENT ---
            account_number = extract_account(data)
            account = accounts.get(account_number)
            policy = account.policy if account else 'yes'
            is_encrypted = crypto is not None

            if policy == 'no':
                log.warning("IP Check from disabled account '%s' - ignored.", account_number)
                return

            if policy == 'secure' and not is_encrypted:
                log.warning("IP Check from '%s' requires encrypted connection - ignored.", account_number)
                return

            log.debug("IP Check account '%s' policy satisfied.", account_number)
            site_name = account.site_name if account else account_number
            update_watchdog(account_number, site_name, data, notification_queue)

            log.debug("Received ping from site: %s (Account: %s) from %s. Echoing response.",
                      site_name, account_number, addr[0])

            response = crypto.encrypt(data) if crypto else data
            writer.write(response)
            await writer.drain()

            # Wait for the panel to close the connection.
            # Note: The panel closes the connection after 15s:
            await reader.read(-1)
            log.debug("Panel at %r has closed the connection.", addr)
            break

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
            pass
        except Exception:
            pass
