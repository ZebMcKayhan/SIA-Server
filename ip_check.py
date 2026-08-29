#!/usr/bin/env python3
"""
Galaxy IP Check (Heartbeat) Server

Handles the proprietary Honeywell "Path Viability Check" heartbeat protocol.
Intended to be imported and run as part of sia-server.py.
"""

import asyncio
import logging
import sys
import time
import datetime
from queue import Queue
from typing import Optional, Tuple

from galaxy.protocol import INCOMPLETE_BLOCK_TIMEOUT, INTER_COMMAND_TIMEOUT, IP_CHECK_CLOSE_TIMEOUT
from notification import enqueue_message_notification

log = logging.getLogger('ip_check')

# --- Optional Encryption Support ---
ENCRYPTION_AVAILABLE = False
START_ENC_HEADER = b'\x05\x01'
CryptoContext = None
do_handshake = None
try:
    from galaxy.encryption import do_handshake, CryptoContext
    ENCRYPTION_AVAILABLE = True
    enc_version = getattr(sys.modules.get('galaxy.encryption'), '__version__', None)
    log.debug("Encryption modules loaded (version %s).", enc_version)
except ModuleNotFoundError:
    log.debug("Encryption modules not found. Encrypted sessions will be rejected.")
except ImportError:
    log.debug("Encryption modules failed to import. Encrypted sessions will be rejected.")
except Exception as e:
    log.debug("Encryption modules failed to load: %s. Encrypted sessions will be rejected.", e)

import re

# --- Watchdog Configuration ---
PANEL_EPOCH_OFFSET = 54000  # 15 hours - converts panel timestamp to local time

# --- Module-level config and accounts, set by init() ---
config = None
accounts = None

def init(cfg, accts):
    """Initialise the IP Check module with shared config and accounts."""
    global config, accounts
    config = cfg
    accounts = accts

# Watchdog state per account
# { account: { 'state': 'UNKNOWN'|'CONNECTED'|'DISCONNECTED'|'DISABLED',
#              'last_seen': float,      # server time (time.time())
#              'last_panel_time': str,  # formatted panel local time
#              'last_panel_ts': float,  # panel epoch timestamp with offset
#              'interval': int } }      # seconds
watchdog_state = {}

def panel_timestamp_to_str(data: bytes) -> str:
    """Extract and format panel timestamp from IP Check packet bytes 15-18."""
    ts = data[15] + data[16]*256 + data[17]*65536 + data[18]*16777216
    unix_ts = ts + PANEL_EPOCH_OFFSET
    return datetime.datetime.fromtimestamp(
        unix_ts, datetime.timezone.utc
    ).strftime('%Y-%m-%d %H:%M')


# ===================================================================
# IP Check Notification Formatting
# ===================================================================

def format_duration(seconds: Union[int, float], fmt: str) -> str:
    """
    Format a duration in seconds according to duration format tokens (%DD, %hh, %mm, %ss).

    Rules:
      - Units are calculated from largest to smallest unit requested in the format string.
      - Omitted higher-order units fold into the next lower unit.
      - %DD: Days, leading zeroes stripped, 0 is '0'.
      - %hh: Hours, minimum 2 digits (does not wrap at 24).
      - %mm: Minutes, minimum 2 digits.
      - %ss: Seconds, minimum 2 digits.
      - The calculation is independent of the order tokens appear in the string.
    """
    total_seconds = max(0, int(round(seconds)))
    has_days = '%DD' in fmt
    has_hours = '%hh' in fmt
    has_minutes = '%mm' in fmt
    has_seconds = '%ss' in fmt

    rem = total_seconds
    if has_days:
        days = rem // 86400
        rem %= 86400
    else:
        days = 0

    if has_hours:
        hours = rem // 3600
        rem %= 3600
    else:
        hours = 0

    if has_minutes:
        minutes = rem // 60
        rem %= 60
    else:
        minutes = 0

    if has_seconds:
        secs = rem
    else:
        secs = 0

    result = fmt
    if has_days:
        result = result.replace('%DD', str(days))
    if has_hours:
        result = result.replace('%hh', f"{hours:02d}")
    if has_minutes:
        result = result.replace('%mm', f"{minutes:02d}")
    if has_seconds:
        result = result.replace('%ss', f"{secs:02d}")

    return result


def format_timestamp_dt(dt: datetime.datetime, fmt: str) -> str:
    """Format a datetime object using %YYYY, %YY, %MM, %DD, %hh, %mm, %ss tokens."""
    res = fmt
    res = res.replace('%YYYY', dt.strftime('%Y'))
    res = res.replace('%YY', dt.strftime('%y'))
    res = res.replace('%MM', dt.strftime('%m'))
    res = res.replace('%DD', dt.strftime('%d'))
    res = res.replace('%hh', dt.strftime('%H'))
    res = res.replace('%mm', dt.strftime('%M'))
    res = res.replace('%ss', dt.strftime('%S'))
    return res


def format_timestamp_struct(st: time.struct_time, fmt: str) -> str:
    """Format a time struct using %YYYY, %YY, %MM, %DD, %hh, %mm, %ss tokens."""
    res = fmt
    res = res.replace('%YYYY', time.strftime('%Y', st))
    res = res.replace('%YY', time.strftime('%y', st))
    res = res.replace('%MM', time.strftime('%m', st))
    res = res.replace('%DD', time.strftime('%d', st))
    res = res.replace('%hh', time.strftime('%H', st))
    res = res.replace('%mm', time.strftime('%M', st))
    res = res.replace('%ss', time.strftime('%S', st))
    return res


def _render_ip_check_field(field_name: str, fmt: Optional[str],
                           context: dict, server_time_st: time.struct_time) -> Optional[str]:
    """
    Render a single field token (%field or %field{format}) for an IP Check event.
    Returns None if the field is unavailable for the current event.
    """
    # Server time fields
    if field_name == 'time':
        return time.strftime('%H:%M', server_time_st)
    if field_name == 'YYYY':
        return time.strftime('%Y', server_time_st)
    if field_name == 'YY':
        return time.strftime('%y', server_time_st)
    if field_name == 'MM':
        return time.strftime('%m', server_time_st)
    if field_name == 'DD':
        return time.strftime('%d', server_time_st)
    if field_name == 'hh':
        return time.strftime('%H', server_time_st)
    if field_name == 'mm':
        return time.strftime('%M', server_time_st)
    if field_name == 'ss':
        return time.strftime('%S', server_time_st)

    # String fields (always available)
    if field_name in ('account', 'site_name', 'current_state', 'new_state'):
        val = context.get(field_name)
        return str(val) if val is not None else None

    # Duration fields
    if field_name in ('last_interval', 'new_interval', 'last_threshold',
                      'new_threshold', 'elapsed'):
        val = context.get(field_name)
        if val is None:
            return None
        if fmt:
            return format_duration(val, fmt)
        else:
            return format_duration(val, '%hh:%mm:%ss')

    # Timestamp fields
    if field_name == 'last_seen':
        ts = context.get('last_seen')
        if ts is None:
            return None
        st = time.localtime(ts)
        if fmt:
            return format_timestamp_struct(st, fmt)
        else:
            return time.strftime('%Y-%m-%d %H:%M:%S', st)

    if field_name in ('last_panel_time', 'new_panel_time'):
        ts_key = 'last_panel_ts' if field_name == 'last_panel_time' else 'new_panel_ts'
        ts = context.get(ts_key)
        str_val = context.get(field_name)
        if ts is None and str_val is None:
            return None
        if fmt:
            if ts is not None:
                dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
                return format_timestamp_dt(dt, fmt)
            elif str_val is not None:
                try:
                    dt = datetime.datetime.strptime(str_val, '%Y-%m-%d %H:%M').replace(tzinfo=datetime.timezone.utc)
                    return format_timestamp_dt(dt, fmt)
                except Exception:
                    return str_val
            return None
        else:
            if str_val is not None:
                return str_val
            elif ts is not None:
                return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
            return None

    return None


def format_ip_check_notification(template: str, context: dict) -> str:
    r"""
    Format an IP Check notification string according to context.

    Syntax:
      %field          Value of the field formatted with default representation.
      %field{format}  Value formatted using the specified timestamp/duration format.
      [ ... ]         Optional section; omitted if any referenced field is unavailable.
      \n, \r\n        Replaced with a newline character.
    """
    server_time_st = time.localtime()

    # Process optional sections [ ... ]
    def render_optional(match: re.Match) -> str:
        section = match.group(1)
        # Find all %field or %field{format}
        matches = re.findall(r'%([a-zA-Z_][a-zA-Z0-9_]*)(?:\{([^{}]*)\})?', section)
        if any(_render_ip_check_field(field_name, fmt if fmt else None, context, server_time_st) is None
               for field_name, fmt in matches):
            return ""

        def replace_in_section(m: re.Match) -> str:
            field_name = m.group(1)
            fmt = m.group(2) if m.group(2) is not None else None
            val = _render_ip_check_field(field_name, fmt, context, server_time_st)
            return val if val is not None else ""

        return re.sub(r'%([a-zA-Z_][a-zA-Z0-9_]*)(?:\{([^{}]*)\})?', replace_in_section, section)

    template = re.sub(r'\[([^\[\]]*)\]', render_optional, template)

    # Process remaining %field or %field{format} tokens
    def replace_main(m: re.Match) -> str:
        field_name = m.group(1)
        fmt = m.group(2) if m.group(2) is not None else None
        val = _render_ip_check_field(field_name, fmt, context, server_time_st)
        return val if val is not None else ""

    template = re.sub(r'%([a-zA-Z_][a-zA-Z0-9_]*)(?:\{([^{}]*)\})?', replace_main, template)

    # Replace newline escape sequences
    template = template.replace(r"\r\n", "\n").replace(r"\n", "\n")

    return template


def update_watchdog(account_number: str, site_name: str,
                    data: bytes, notification_queue: Queue):
    """
    Update watchdog state when a valid ping is received.
    Called from handle_ip_check() after successful validation.
    """
    ts = data[15] + data[16]*256 + data[17]*65536 + data[18]*16777216
    unix_ts = ts + PANEL_EPOCH_OFFSET
    dt = datetime.datetime.fromtimestamp(unix_ts, datetime.timezone.utc)
    panel_time = dt.strftime('%Y-%m-%d %H:%M')

    interval = data[20] + data[21]*256 + data[22]*65536 + data[23]*16777216
    hours = interval // 3600
    minutes = (interval % 3600) // 60
    seconds = interval % 60
    interval_str = f"{hours:02d}:{minutes:02d}:{seconds:02d} ({interval}s)"

    now = time.time()
    prev_entry = watchdog_state.get(account_number, {})
    current_state = prev_entry.get('state', 'UNKNOWN')
    previous_interval = prev_entry.get('interval')
    prev_panel_time = prev_entry.get('last_panel_time')
    prev_panel_ts = prev_entry.get('last_panel_ts')
    prev_last_seen = prev_entry.get('last_seen')
    current_threshold = (previous_interval * config.IP_CHECK_WATCHDOG) if previous_interval is not None else None
    new_threshold = interval * config.IP_CHECK_WATCHDOG

    new_state = 'DISABLED' if config.IP_CHECK_WATCHDOG <= 1.0 else 'CONNECTED'
    watchdog_state[account_number] = {
        'state': new_state,
        'last_seen': now,
        'last_panel_time': panel_time,
        'last_panel_ts': unix_ts,
        'interval': interval,
    }

    if current_state == 'DISCONNECTED':
        # Connection restored - only reachable if watchdog was previously enabled
        log.info("Watchdog: Site: %s (Account: %s) - connection restored, "
                 "interval %s.", site_name, account_number, interval_str)
        fmt = getattr(config, 'IP_CHECK_CONNECTION_RESTORED', None)
        if fmt:
            elapsed = (now - prev_last_seen) if prev_last_seen is not None else None
            ctx = {
                'account': account_number,
                'site_name': site_name,
                'current_state': current_state,
                'new_state': new_state,
                'last_panel_time': prev_panel_time,
                'last_panel_ts': prev_panel_ts,
                'last_interval': previous_interval,
                'last_threshold': current_threshold,
                'last_seen': prev_last_seen,
                'elapsed': elapsed,
                'new_panel_time': panel_time,
                'new_panel_ts': unix_ts,
                'new_interval': interval,
                'new_threshold': new_threshold,
            }
            msg = format_ip_check_notification(fmt, ctx)
            prio = getattr(config, 'IP_CHECK_CONNECTION_RESTORED_PRIO', 2)
            enqueue_message_notification(
                account_number,
                site_name,
                msg,
                priority=prio,
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

        fmt = getattr(config, 'IP_CHECK_MONITORING_STARTED', None)
        if fmt:
            ctx = {
                'account': account_number,
                'site_name': site_name,
                'current_state': current_state,
                'new_state': new_state,
                'last_panel_time': None,
                'last_panel_ts': None,
                'last_interval': None,
                'last_threshold': None,
                'last_seen': None,
                'elapsed': None,
                'new_panel_time': panel_time,
                'new_panel_ts': unix_ts,
                'new_interval': interval,
                'new_threshold': new_threshold,
            }
            msg = format_ip_check_notification(fmt, ctx)
            prio = getattr(config, 'IP_CHECK_MONITORING_STARTED_PRIO', 2)
            enqueue_message_notification(
                account_number,
                site_name,
                msg,
                priority=prio,
                queue=notification_queue
            )
    else:
        # CONNECTED/DISABLED -> CONNECTED/DISABLED: check if interval changed
        if previous_interval is not None and previous_interval != interval:
            log.info("Watchdog: Site: %s (Account: %s) - interval updated to %s.",
                     site_name, account_number, interval_str)
            fmt = getattr(config, 'IP_CHECK_INTERVAL_CHANGED', None)
            if fmt:
                elapsed = (now - prev_last_seen) if prev_last_seen is not None else None
                ctx = {
                    'account': account_number,
                    'site_name': site_name,
                    'current_state': current_state,
                    'new_state': new_state,
                    'last_panel_time': prev_panel_time,
                    'last_panel_ts': prev_panel_ts,
                    'last_interval': previous_interval,
                    'last_threshold': current_threshold,
                    'last_seen': prev_last_seen,
                    'elapsed': elapsed,
                    'new_panel_time': panel_time,
                    'new_panel_ts': unix_ts,
                    'new_interval': interval,
                    'new_threshold': new_threshold,
                }
                msg = format_ip_check_notification(fmt, ctx)
                prio = getattr(config, 'IP_CHECK_INTERVAL_CHANGED_PRIO', 3)
                enqueue_message_notification(
                    account_number,
                    site_name,
                    msg,
                    priority=prio,
                    queue=notification_queue
                )

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
                current_state = state['state']
                new_state = 'DISCONNECTED'
                watchdog_state[account_number]['state'] = new_state
                last_panel_time = state['last_panel_time']
                last_panel_ts = state.get('last_panel_ts')
                last_seen = state['last_seen']
                current_threshold = threshold

                account = accounts.get(account_number)
                site_name = account.site_name if account else account_number
                policy = account.policy if account else 'yes'
                
                # Check account policy before firing notification
                if policy == 'no':
                    log.debug("Watchdog: Site: %s (Account: %s) - heartbeat lost but account is disabled, skipping notification.",
                              site_name, account_number)
                    continue
                    
                # Format elapsed time as hh:mm:ss
                elapsed_int = int(elapsed)
                e_hours = elapsed_int // 3600
                e_minutes = (elapsed_int % 3600) // 60
                e_seconds = elapsed_int % 60

                log.warning("Watchdog: Site: %s (Account: %s) - heartbeat lost! "
                            "No ping received for %02d:%02d:%02d.",
                            site_name, account_number, e_hours, e_minutes, e_seconds)

                fmt = getattr(config, 'IP_CHECK_WATCHDOG_TIMEOUT', None)
                if fmt:
                    ctx = {
                        'account': account_number,
                        'site_name': site_name,
                        'current_state': current_state,
                        'new_state': new_state,
                        'last_panel_time': last_panel_time,
                        'last_panel_ts': last_panel_ts,
                        'last_interval': interval,
                        'last_threshold': current_threshold,
                        'last_seen': last_seen,
                        'elapsed': elapsed,
                        'new_panel_time': None,
                        'new_panel_ts': None,
                        'new_interval': None,
                        'new_threshold': None,
                    }
                    msg = format_ip_check_notification(fmt, ctx)
                    prio = getattr(config, 'IP_CHECK_WATCHDOG_TIMEOUT_PRIO', 4)
                    enqueue_message_notification(
                        account_number,
                        site_name,
                        msg,
                        priority=prio,
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

async def handle_ip_check(reader, writer, notification_queue: Queue):
    """Handles an incoming IP Check connection by echoing the received data."""
    addr = writer.get_extra_info('peername')
    log.debug("Connection from %r", addr)
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
            if crypto is None and buffer.startswith(START_ENC_HEADER):
                if len(buffer) < 5:
                    log.debug("Encrypted header incomplete from %r, waiting for more.", addr)
                    continue
                if ENCRYPTION_AVAILABLE:
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
            # The panel normally closes after ~15 s; we give it 30 s so a slow
            # network doesn't trigger the timeout under normal conditions.
            # If the timeout fires (network fault / panel hung), we log at debug
            # and fall through to the finally block which closes the writer.
            try:
                await asyncio.wait_for(reader.read(1024), timeout=IP_CHECK_CLOSE_TIMEOUT)
                log.debug("Panel at %r has closed the connection.", addr)
            except asyncio.TimeoutError:
                log.debug("Panel at %r did not close within %.0fs; closing from server side.",
                          addr, IP_CHECK_CLOSE_TIMEOUT)

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
