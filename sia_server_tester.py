#!/usr/bin/env python3
"""SIA Server Test Client

Builds and sends valid Galaxy SIA message blocks to the SIA server.
This script is useful for testing the server with variable input values.

--- Arguments ---

  --host HOST         Server hostname or IP address (default: 127.0.0.1)
  --port PORT         Server port (default: 10000)
  --timeout SECS      Max seconds to wait for a response per segment (default: 2.0)
  --quiet             Suppress all output except errors

Message modes (mutually exclusive, one is required):
  --send-sample                     Send the built-in sample message sequence.
  --segment HEX [--segment HEX]     Send one or more raw hex segments.
  --account-id ID --new-event EVT   Build and send new event message from payloads.
  --account-id ID --old-event EVT   Build and send old event message from payloads.
  --ascii TEXT                      ASCII block is optional (omit for SIA level 0/1/2).
  --account-id ID --ip-check        Send a simulated IP Check (heartbeat) ping.
  --interval HH:MM                  Heartbeat interval for --ip-check (default: 00:15)

--- SIA Event Structure Reference ---

Event types and their DATA block (N) formats by SIA level:

  Zone events (detector alarm, keyswitch etc.):
    Level 3/4:  #xxxxxx  Ntihh:mm/rigg/EVzzzz   + ASCII block
    Level 2:    #xxxxxx  Ntihh:mm/rigg/EVzzzz
    Level 1:    #xxxxxx  NEVzzzz
    Level 0:    #xxxx    NEVzzzz

  User events (arm/disarm, reset, duress etc.):
    Level 3/4:  #xxxxxx  Ntihh:mm/rigg/iduuu/pimmm/EV   + ASCII block
    Level 2:    #xxxxxx  Ntihh:mm/rigg/iduuu/pimmm/EV
    Level 1:    #xxxxxx  NEVmmm
    Level 0:    #xxxx    NEVmmm

  Module events (keypad added, RIO missing etc.):
    Level 3/4:  #xxxxxx  Ntihh:mm/rigg/pimmm/EV   + ASCII block
    Level 2:    #xxxxxx  Ntihh:mm/rigg/pimmm/EV
    Level 1:    #xxxxxx  NEVmmm
    Level 0:    #xxxx    NEVmmm

  System events (auto set, test, engineer mode etc.):
    Level 3/4:  #xxxxxx  Ntihh:mm/rigg/EV   + ASCII block
    Level 2:    #xxxxxx  Ntihh:mm/rigg/EV
    Level 1:    #xxxxxx  NEV
    Level 0:    #xxxx    NEV000

Note: SIA Level 0 uses a 4-digit account number (#xxxx).
      SIA Level 1 and above use a 6-digit account number (#xxxxxx).
      The parser does not track event type, so zone numbers (zzzz),
      module numbers (mmm) and the fixed '000' suffix in level 0
      system events are all parsed the same way.

DATA Block field key:
  ti = Time (hh:mm)
  ri = Group modifier
  g  = Group number (gg)
  id = User modifier
  u  = User number (uuu)
  pi = Peripheral modifier
  m  = Peripheral number (mmm)
  EV = Event Code (2 chars, see galaxy/constants.py for full list)
  z  = Zone number (zzzz)

ASCII Block field key:
  e  = Log event name (9 chars)
  s  = Event state ('+' ON, '-' OFF, ' ' NOT USED)
  l  = Site identifier (8 chars, can be blank)
  d  = Descriptor:
         Zone event:   16 char zone name
         User event:    6 char username
         Module event:  3 char module name (RIO, KEY, MAX, COM1-COM6)

--- Usage Examples ---

SIA Level 3 - Zone alarm (Burglary Alarm, zone 1011):
    python sia_server_tester.py --account-id 123456 \\
      --new-event 'ti23:42/ri01/BA1011' \\
      --ascii '+INBROTT      IR Hall          '

SIA Level 3 - User event (Area closed/armed by user 023, partition 013) Custom host and port:
    python sia_server_tester.py --host 192.168.1.100 --port 10000 \\
      --account-id 123456 \\
      --new-event 'ti23:42/id023/pi013/CG' \\
      --ascii ' PART SET USER'

SIA Level 3 - System event (Automatic test), Suppress output (quiet mode):
    python sia_server_tester.py --quiet \\
      --account-id 123456 \\
      --new-event 'ti08:00/ri01/RP' \\
      --ascii ' AUTO TEST...Modul'

SIA Level 2 - Zone alarm (no ASCII block), Custom response timeout (default is 2.0 seconds):
    python sia_server_tester.py --timeout 0.5 \\
      --account-id 123456 \\
      --new-event 'ti23:42/ri01/BA1011'

    python sia_server_tester.py --account-id 123456 \\
      --old-event 'ti23:42/ri01/BA1011'

SIA Level 1 - Zone alarm (minimal format, 6-digit account):
    python sia_server_tester.py --account-id 123456 \\
      --new-event 'BA1011'

SIA Level 1 - User event (module number instead of zone):
    python sia_server_tester.py --account-id 123456 \\
      --new-event 'CL001'

SIA Level 0 - Zone alarm (4-digit account):
    python sia_server_tester.py --account-id 1234 \\
      --new-event 'BA1011'

SIA Level 0 - System event (fixed 000 suffix):
    python sia_server_tester.py --account-id 1234 \\
      --new-event 'RP000'

IP Check (heartbeat) - default 15 minute interval, default port 10001:
    python sia_server_tester.py --account-id 123456 --ip-check

IP Check with custom interval and port:
    python sia_server_tester.py --account-id 123456 --ip-check \\
      --interval 00:30 --port 10001

Send built-in sample message:
    python sia_server_tester.py --send-sample

Send built-in sample to a remote host:
    python sia_server_tester.py --host 192.168.1.100 --send-sample

Example using raw hex segments:
    python sia_server_tester.py \\
      --segment 46233032333439399f \\
      --segment 564e746932333a34322f69643032332f70693031332f4347fb \\
      --segment 4e41205041525420534554205553455294 \\
      --segment 40308f
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
from typing import Iterable, List

from galaxy.protocol import build_block
from galaxy.constants import COMMAND_BYTES


DEFAULT_HOST       = '127.0.0.1'
DEFAULT_PORT       = 10000
DEFAULT_IP_CHECK_PORT = 10001
DEFAULT_TIMEOUT    = 2.0
DEFAULT_INTERVAL   = '00:15'
PANEL_EPOCH_OFFSET = 54000  # 15 hours - same as ip_check.py

SAMPLE_ACCOUNT  = '123456'
SAMPLE_NEW_EVENT = 'ti23:42/id023/pi013/CG'
SAMPLE_ASCII    = ' PART SET USER'

# Static block bytes 9-14 - observed constant across all captures
_IP_CHECK_STATIC = bytes([0x11, 0x0c, 0x00, 0xfd, 0x09, 0x00])


def parse_hex_segment(segment: str) -> bytes:
    """Convert a hex string to raw bytes."""
    normalized = segment.strip().replace(' ', '').replace('\\x', '')
    if len(normalized) % 2 != 0:
        raise ValueError('Hex segment length must be even.')
    return bytes.fromhex(normalized)


def parse_interval(interval_str: str) -> int:
    """Parse HH:MM interval string and return total seconds."""
    try:
        parts = interval_str.strip().split(':')
        if len(parts) != 2:
            raise ValueError
        hours   = int(parts[0])
        minutes = int(parts[1])
        if not (0 <= hours <= 99 and 0 <= minutes <= 59):
            raise ValueError
        return hours * 3600 + minutes * 60
    except ValueError:
        raise ValueError(f"Invalid interval format '{interval_str}'. Use HH:MM (e.g. 00:15 or 01:30).")


def build_ip_check_packet(account_id: str, interval_seconds: int) -> bytes:
    """
    Build a 26-byte IP Check (heartbeat) packet.

    Structure:
      Byte 0:     0x00 header
      Bytes 1-8:  account number, ASCII zero-padded to 8 chars
      Bytes 9-14: static ID block (observed constant across all captures)
      Bytes 15-18: timestamp, 32-bit little-endian (Unix time - PANEL_EPOCH_OFFSET)
      Byte 19:    0x3c (unknown, always observed as 60)
      Bytes 20-23: interval in seconds, 32-bit little-endian
      Bytes 24-25: checksum (algorithm unknown, set to 0x00 0x00)

    Note: The checksum algorithm is unknown so bytes 24-25 are set to 0x00.
          ip_check.py does not currently validate the checksum so this is
          sufficient for testing.
    """
    # Byte 0: header
    header = bytes([0x00])

    # Bytes 1-8: account number zero-padded to 8 chars
    account_padded = account_id.zfill(8).encode('ascii')[:8]

    # Bytes 15-18: timestamp (current unix time minus timezone and panel epoch offset)
    if time.localtime().tm_isdst and time.daylight:
        tz_offset = time.altzone
    else:
        tz_offset = time.timezone
    timestamp = int(time.time()) - tz_offset - PANEL_EPOCH_OFFSET
    ts_bytes = struct.pack('<I', timestamp & 0xFFFFFFFF)

    # Byte 19: unknown, always 0x3c
    unknown = bytes([0x3c])

    # Bytes 20-23: interval in seconds
    iv_bytes = struct.pack('<I', interval_seconds & 0xFFFFFFFF)

    # Bytes 24-25: checksum unknown, set to 0x00
    checksum = bytes([0x00, 0x00])

    packet = header + account_padded + _IP_CHECK_STATIC + ts_bytes + unknown + iv_bytes + checksum
    assert len(packet) == 26, f"IP Check packet must be 26 bytes, got {len(packet)}"
    return packet


def send_segments(host: str, port: int, segments: Iterable[bytes],
                  timeout: float, quiet: bool = False) -> None:
    """Send raw byte segments to the SIA server, reading and printing the response after each segment."""
    segments_list = list(segments)
    print(f'Connecting to {host}:{port}...')
    with socket.create_connection((host, port), timeout=5) as sock:
        for index, chunk in enumerate(segments_list, start=1):
            if not quiet:
                print(f'Sending segment {index}/{len(segments_list)} ({len(chunk)} bytes): {chunk.hex()}')
            sock.sendall(chunk)

            try:
                sock.settimeout(timeout)
                response = sock.recv(4096)
                if response:
                    if len(response) >= 2:
                        cmd_byte = response[1]
                        if cmd_byte == 0x38:
                            status = 'ACK'
                        elif cmd_byte == 0x39:
                            status = 'REJECT'
                        else:
                            status = f'UNKNOWN(0x{cmd_byte:02x})'
                    else:
                        status = 'UNKNOWN (response too short)'
                    if not quiet:
                        print(f'  → {status} ({response.hex()})')
                else:
                    if not quiet:
                        print(f'  → No response received.')
            except socket.timeout:
                if not quiet:
                    print(f'  → No response within {timeout}s, continuing.')


def send_ip_check(host: str, port: int, packet: bytes,
                  timeout: float, quiet: bool = False) -> None:
    """
    Send an IP Check packet and wait for the echo response.
    The server echoes the exact packet back - we verify it matches.
    """
    print(f'Connecting to {host}:{port} for IP Check...')
    with socket.create_connection((host, port), timeout=5) as sock:
        if not quiet:
            print(f'Sending IP Check packet ({len(packet)} bytes): {packet.hex()}')
        sock.sendall(packet)

        try:
            sock.settimeout(timeout)
            response = sock.recv(1024)
            if response:
                if response == packet:
                    if not quiet:
                        print(f'  → Echo received ({len(response)} bytes) ✓ matches sent packet')
                else:
                    if not quiet:
                        print(f'  → Response received ({len(response)} bytes): {response.hex()}')
                        print(f'  → WARNING: Response does not match sent packet!')
            else:
                if not quiet:
                    print(f'  → No response received.')
        except socket.timeout:
            if not quiet:
                print(f'  → No response within {timeout}s.')


def build_sample_message(account_id: str, event_payload: str,
                         event_command: str = 'NEW_EVENT',
                         ascii_text: str | None = None) -> List[bytes]:
    """Build a standard ACCOUNT_ID + NEW_EVENT/OLD_EVENT + (optional ASCII) + END_OF_DATA sequence."""
    segments = [
        build_block(COMMAND_BYTES['ACCOUNT_ID'], account_id.encode('ascii')),
        build_block(COMMAND_BYTES[event_command], event_payload.encode('ascii')),
    ]
    if ascii_text is not None:
        segments.append(build_block(COMMAND_BYTES['ASCII'], ascii_text.encode('ascii')))
    segments.append(build_block(COMMAND_BYTES['END_OF_DATA'], b''))
    return segments


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Send raw Galaxy SIA packets to a SIA server.')
    parser.add_argument('--host', default=DEFAULT_HOST,
                        help='Server host (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                        help='Server port (default: 10000, IP Check default: 10001)')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT,
                        help='Max time in seconds to wait for a response (default: 2.0)')
    parser.add_argument('--account-id',
                        help='Account ID payload for ACCOUNT_ID command.')
    parser.add_argument('--new-event',
                        help='Payload for NEW_EVENT command.')
    parser.add_argument('--old-event',
                        help='Payload for OLD_EVENT command (same format as --new-event).')
    parser.add_argument('--ascii', dest='ascii_text',
                        help='Payload for ASCII command.')
    parser.add_argument('--ip-check', action='store_true',
                        help='Send a simulated IP Check (heartbeat) ping.')
    parser.add_argument('--interval', default=DEFAULT_INTERVAL,
                        help='Heartbeat interval for --ip-check in HH:MM format (default: 00:15).')
    parser.add_argument('--send-sample', action='store_true',
                        help='Send the built-in sample message sequence.')
    parser.add_argument('--segment', action='append', default=[],
                        help='Raw hex segment to send. Can be repeated.')
    parser.add_argument('--quiet', action='store_true',
                        help='Suppress debug output.')

    args = parser.parse_args(argv)

    # --- IP Check mode ---
    if args.ip_check:
        if not args.account_id:
            parser.error('--ip-check requires --account-id.')

        # Default to IP Check port if user did not specify a port
        port = args.port if args.port != DEFAULT_PORT else DEFAULT_IP_CHECK_PORT

        try:
            interval_seconds = parse_interval(args.interval)
        except ValueError as e:
            parser.error(str(e))

        packet = build_ip_check_packet(args.account_id, interval_seconds)

        if not args.quiet:
            print('SIA Server Tester - IP Check mode')
            print('----------------------------------')
            print(f'Host:     {args.host}')
            print(f'Port:     {port}')
            print(f'Account:  {args.account_id}')
            print(f'Interval: {args.interval} ({interval_seconds}s)')
            print(f'Timeout:  {args.timeout}s')

        try:
            send_ip_check(args.host, port, packet, args.timeout, quiet=args.quiet)
            return 0
        except Exception as exc:
            print(f'ERROR: {exc}', file=sys.stderr)
            return 1

    # --- SIA Event modes ---
    if args.send_sample:
        segments = build_sample_message(SAMPLE_ACCOUNT, SAMPLE_NEW_EVENT, 'NEW_EVENT', SAMPLE_ASCII)
    elif args.segment:
        segments = [parse_hex_segment(segment) for segment in args.segment]
    elif args.account_id or args.new_event or args.old_event or args.ascii_text:
        if not args.account_id or not (args.new_event or args.old_event):
            parser.error('When building a message, --account-id and --new-event or --old-event are required.')
        if args.new_event and args.old_event:
            parser.error('Cannot use both --new-event and --old-event.')
        event_payload = args.new_event or args.old_event
        event_command = 'NEW_EVENT' if args.new_event else 'OLD_EVENT'
        segments = build_sample_message(args.account_id, event_payload, event_command, args.ascii_text)
    else:
        parser.error('Provide --send-sample, --segment, --ip-check, or the command payload arguments.')

    if not args.quiet:
        print('SIA Server Tester')
        print('------------------')
        print(f'Host:     {args.host}')
        print(f'Port:     {args.port}')
        print(f'Timeout:  {args.timeout}s')
        print(f'Segments: {len(segments)}')

    try:
        send_segments(args.host, args.port, segments, args.timeout, quiet=args.quiet)
        return 0
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
