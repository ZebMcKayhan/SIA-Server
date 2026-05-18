#!/usr/bin/env python3
"""SIA Server Test Client

Builds and sends valid Galaxy SIA message blocks to the SIA server.
This script is useful for testing the server with variable input values.

Example:
    python sia_server_tester.py --host 127.0.0.1 --port 10000 \
      --account-id 023499 --new-event 'ti23:42/id023/pi013/CG' \
      --ascii ' PART SET USER' --delay 0.05

Example using raw hex segments:
    python sia_server_tester.py --segment 46233032333439399f \
      --segment 564e746932333a34322f69643032332f70693031332f4347fb \
      --segment 4e41205041525420534554205553455294 \
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
SAMPLE_ACCOUNT = '023499'
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


def build_sample_message(account_id: str, new_event: str, ascii_text: str) -> List[bytes]:
    """Build a standard ACCOUNT_ID + NEW_EVENT + ASCII + END_OF_DATA sequence."""
    return [
        build_sia_block('ACCOUNT_ID', account_id.encode('ascii')),
        build_sia_block('NEW_EVENT', new_event.encode('ascii')),
        build_sia_block('ASCII', ascii_text.encode('ascii')),
        build_sia_block('END_OF_DATA', b''),
    ]


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
        if not args.account_id or not args.new_event or args.ascii_text is None:
            parser.error('When building a message from command payloads, all of --account-id, --new-event, and --ascii must be provided.')
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
