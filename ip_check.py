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
from typing import Optional, Tuple, Union

from galaxy.protocol import INCOMPLETE_BLOCK_TIMEOUT, INTER_COMMAND_TIMEOUT, IP_CHECK_CLOSE_TIMEOUT
import watchdog

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

_ip_check_last_ping_ip = None  # Last PING source IP seen on IP-Check port (for log deduplication)

def panel_timestamp_to_str(data: bytes) -> str:
    """Extract and format panel timestamp from IP Check packet bytes 15-18."""
    ts = data[15] + data[16]*256 + data[17]*65536 + data[18]*16777216
    unix_ts = ts + PANEL_EPOCH_OFFSET
    return datetime.datetime.fromtimestamp(
        unix_ts, datetime.timezone.utc
    ).strftime('%Y-%m-%d %H:%M')




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


async def _handle_ip_check_ping(writer, addr):
    """
    Handle a PING healthcheck command received on the IP-Check port.

    Response policy:
      REJECT_POLICY = respond  -> send PONG to any source IP.
      REJECT_POLICY = drop     -> send PONG only to 127.0.0.1; ignore all others.

    Logging:
      First PING from a source IP   -> INFO (policy satisfied / rejected).
      Subsequent PINGs from same IP -> DEBUG only.
      If a new source IP is seen, the remembered IP is replaced and a new INFO
      entry is emitted.
    """
    global _ip_check_last_ping_ip
    source_ip = addr[0]

    if config.REJECT_POLICY == 'respond':
        allowed = True
    else:  # 'drop'
        allowed = (source_ip == '127.0.0.1')

    if source_ip != _ip_check_last_ping_ip:
        _ip_check_last_ping_ip = source_ip
        if allowed:
            log.info(
                "PING Received from IP %s, policy satisfied. "
                "Consecutive PINGs from this IP will not be logged.", source_ip
            )
        else:
            log.info(
                "PING Received from IP %s, policy rejected. "
                "Consecutive PINGs from this IP will not be logged.", source_ip
            )
    else:
        log.debug("PING from %s (duplicate suppressed).", source_ip)

    if allowed:
        writer.write(b"PONG")
        await writer.drain()
        log.debug("PONG sent to %s.", source_ip)


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

            # --- PING healthcheck detection ---
            # Must be an EXACT match of the 4 bytes b"PING" — no prefix, suffix, or framing.
            # Anything other than exactly b"PING" falls through to normal IP-Check processing.
            if crypto is None:
                _buf = bytes(buffer)
                if _buf == b"PING":
                    await _handle_ip_check_ping(writer, addr)
                    return
                # If we have 2-3 bytes that are a valid prefix of "PING", wait for the rest.
                # This handles TCP chunk delivery without prematurely dropping the connection.
                if len(_buf) <= 3 and _buf == b"PING"[:len(_buf)]:
                    log.debug("Partial PING prefix from %r, waiting for more data.", addr)
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

            # Parse timestamp and interval from raw bytes
            ts = data[15] + data[16]*256 + data[17]*65536 + data[18]*16777216
            unix_ts = ts + PANEL_EPOCH_OFFSET
            dt = datetime.datetime.fromtimestamp(unix_ts, datetime.timezone.utc)
            panel_time = dt.strftime('%Y-%m-%d %H:%M')
            interval = data[20] + data[21]*256 + data[22]*65536 + data[23]*16777216

            watchdog.update_watchdog(
                account_number=account_number,
                site_name=site_name,
                panel_time=panel_time,
                panel_ts=float(unix_ts),
                interval=interval,
                notification_queue=notification_queue,
            )

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
