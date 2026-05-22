#!/usr/bin/env python3
"""SIA Server Test Client

Builds and sends valid Galaxy SIA message blocks to the SIA server.
This script is useful for testing the server with variable input values.

--- SIA Event Structure Reference ---

Event types and their DATA block (N) formats by SIA level:

  Zone events (detector alarm, keyswitch etc.):
    Level 3/4:  #xxxxxx  N ti:xx/ri:xx/EV zzzz   + ASCII block
    Level 2:    #xxxxxx  N ti:xx/ri:xx/EV zzzz
    Level 1:    #xxxxxx  N EV zzzz
    Level 0:    #xxxx    N EV zzzz

  User events (arm/disarm, reset, duress etc.):
    Level 3/4:  #xxxxxx  N ti:xx/ri:xx/id:uuu/pi:xxx/EV   + ASCII block
    Level 2:    #xxxxxx  N ti:xx/ri:xx/id:uuu/pi:xxx/EV
    Level 1:    #xxxxxx  N EV mmm
    Level 0:    #xxxx    N EV mmm

  Module events (keypad added, RIO missing etc.):
    Level 3/4:  #xxxxxx  N ti:xx/ri:xx/pi:mmm/EV   + ASCII block
    Level 2:    #xxxxxx  N ti:xx/ri:xx/pi:mmm/EV
    Level 1:    #xxxxxx  N EV mmm
    Level 0:    #xxxx    N EV mmm

  System events (auto set, test, engineer mode etc.):
    Level 3/4:  #xxxxxx  N ti:xx/ri:xx/EV   + ASCII block
    Level 2:    #xxxxxx  N ti:xx/ri:xx/EV
    Level 1:    #xxxxxx  N EV
    Level 0:    #xxxx    N EV000

Note: SIA Level 0 uses a 4-digit account number (#xxxx).
      SIA Level 1 and above use a 6-digit account number (#xxxxxx).
      The parser does not track event type, so zone numbers (zzzz),
      module numbers (mmm) and the fixed '000' suffix in level 0
      system events are all parsed the same way.

DATA Block field key:
  ti = Time (hh:mm)
  ri = Group/partition number
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

SIA Level 3 - User event (Area closed/armed by user 023, partition 013):
    python sia_server_tester.py --account-id 123456 \\
      --new-event 'ti23:42/id023/pi013/CG' \\
      --ascii ' PART SET USER'

SIA Level 3 - System event (Automatic test):
    python sia_server_tester.py --account-id 123456 \\
      --new-event 'ti08:00/ri01/RP' \\
      --ascii ' AUTO TEST...Modul'

SIA Level 2 - Zone alarm (no ASCII block):
    python sia_server_tester.py --account-id 123456 \\
      --new-event 'ti23:42/ri01/BA1011'

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
import sys
import time
from typing import Iterable, List

from galaxy.constants import COMMAND_BYTES


DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 10000
DEFAULT_DELAY = 0.05
SAMPLE_ACCOUNT = '123456'
SAMPLE_NEW_EVENT = 'ti23:42/id023/pi013/CG'
SAMPLE_ASCII = ' PART SET USER'


def build_sia_block(command: str | int, payload: bytes = b'') -> bytes:
    """Build a valid Galaxy SIA block with checksum."""
    if isinstance(command, str):
        command = command.upper()
        if command not in COMMAND_BYTES:
            raise ValueError(f'Unknown SIA command: {command}')
        command_byte = COMMAND_BYTES[command]
    else:
        command_byte = command

    length_byte = 0x40 + len(payload)
    message = bytes([length_byte, command_byte]) + payload
    checksum = 0xFF
    for byte in message:
        checksum ^= byte
    return message + bytes([checksum])


def parse_hex_segment(segment: str) -> bytes:
    """Convert a hex string to raw bytes."""
    normalized = segment.strip().replace(' ', '').replace('\\x', '')
    if len(normalized) % 2 != 0:
        raise ValueError('Hex segment length must be even.')
    return bytes.fromhex(normalized)


def send_segments(host: str, port: int, segments: Iterable[bytes], delay: float, quiet: bool = False) -> None:
    """Send raw byte segments to the SIA server."""
    segments_list = list(segments)
    print(f'Connecting to {host}:{port}...')
    with socket.create_connection((host, port), timeout=5) as sock:
        for index, chunk in enumerate(segments_list, start=1):
            if not quiet:
                print(f'Sending segment {index}/{len(segments_list)} ({len(chunk)} bytes)')
            sock.sendall(chunk)
            if delay > 0 and index != len(segments_list):
                time.sleep(delay)

        try:
            sock.settimeout(2.0)
            response = sock.recv(4096)
            if response:
                print('Server response:', response.hex())
            else:
                print('No response received; connection closed by server.')
        except socket.timeout:
            print('No response received within timeout.')


def build_sample_message(account_id: str, new_event: str, ascii_text: str | None = None) -> List[bytes]:
    """Build a standard ACCOUNT_ID + NEW_EVENT + (optional ASCII) + END_OF_DATA sequence."""
    segments = [
        build_sia_block('ACCOUNT_ID', account_id.encode('ascii')),
        build_sia_block('NEW_EVENT', new_event.encode('ascii')),
    ]
    if ascii_text is not None:
        segments.append(build_sia_block('ASCII', ascii_text.encode('ascii')))
    segments.append(build_sia_block('END_OF_DATA', b''))
    return segments


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Send raw Galaxy SIA packets to a SIA server.')
    parser.add_argument('--host', default=DEFAULT_HOST, help='Server host (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Server port (default: 10000)')
    parser.add_argument('--delay', type=float, default=DEFAULT_DELAY, help='Delay between segments in seconds.')
    parser.add_argument('--account-id', help='Account ID payload for ACCOUNT_ID command.')
    parser.add_argument('--new-event', help='Payload for NEW_EVENT command.')
    parser.add_argument('--ascii', dest='ascii_text', help='Payload for ASCII command.')
    parser.add_argument('--send-sample', action='store_true', help='Send the built-in sample message sequence.')
    parser.add_argument('--segment', action='append', default=[], help='Raw hex segment to send. Can be repeated.')
    parser.add_argument('--quiet', action='store_true', help='Suppress debug output.')

    args = parser.parse_args(argv)

    if args.send_sample:
        segments = build_sample_message(SAMPLE_ACCOUNT, SAMPLE_NEW_EVENT, SAMPLE_ASCII)
    elif args.segment:
        segments = [parse_hex_segment(segment) for segment in args.segment]
    elif args.account_id or args.new_event or args.ascii_text:
        if not args.account_id or not args.new_event:
            parser.error('When building a message, --account-id and --new-event are required.')
        segments = build_sample_message(args.account_id, args.new_event, args.ascii_text)
    else:
        parser.error('Provide --send-sample, --segment, or the command payload arguments.')

    if not args.quiet:
        print('SIA Server Tester')
        print('------------------')
        print(f'Host: {args.host}')
        print(f'Port: {args.port}')
        print(f'Delay: {args.delay}s')
        print(f'Segments: {len(segments)}')

    try:
        send_segments(args.host, args.port, segments, args.delay, quiet=args.quiet)
        return 0
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
