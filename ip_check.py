#!/usr/bin/env python3
"""
Galaxy IP Check (Heartbeat) Server

A minimal server that listens on a dedicated port for the proprietary
Honeywell "Path Viability Check" ping. It responds with a REJECT message,
which satisfies the panel's check without generating errors on the panel
or flooding the main SIA server.
"""

import asyncio
import logging
import sys
import signal

# Make uvloop optional for cross-platform compatibility
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

import config
from galaxy.constants import COMMAND_BYTES

# --- Setup minimal logging for this specific service ---
log = logging.getLogger('ip_check_server')
log.setLevel(getattr(logging, config.LOG_LEVEL, 'INFO'))
formatter = logging.Formatter('%(asctime)s - IP_CHECK - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
handler = logging.StreamHandler(sys.stderr) # Always log to console/journal for this simple service
handler.setFormatter(formatter)
log.addHandler(handler)

# We re-implement a minimal build_and_send here to be self-contained
async def build_and_send_reject(writer):
    """Builds and sends a standard REJECT message."""
    command_byte = COMMAND_BYTES['REJECT']
    payload = b''
    length_byte = len(payload) + 0x40
    message_part = bytes([length_byte, command_byte]) + payload
    
    checksum = 0xFF
    for byte in message_part:
        checksum ^= byte
        
    final_message = message_part + bytes([checksum])
    
    writer.write(final_message)
    await writer.drain()

async def handle_ip_check(reader, writer):
    """Handles an incoming IP Check connection."""
    addr = writer.get_extra_info('peername')
    
    try:
        data = await reader.read(1024)
        
        if data:
            # We have received the proprietary IP Check packet.
            # The correct response is a standard REJECT.
            log.info("Received IP Check ping from %s (%d bytes). Responding with REJECT.", addr[0], len(data))
            await build_and_send_reject(writer)
        else:
            log.info("IP Check client at %s connected but sent no data.", addr[0])
            
    except Exception as e:
        log.error("Error in IP Check handler: %s", e)
    finally:
        # The panel expects the connection to be closed after the response.
        log.debug("Closing IP Check connection from %r", addr)
        writer.close()
        await writer.wait_closed()

async def main():
    if not config.IP_CHECK_ENABLED:
        print("IP Check server is disabled in config.py. Exiting.")
        return

    log.info("="*60)
    log.info("Starting Galaxy IP Check (Heartbeat) Server...")
    
    server = await asyncio.start_server(
        handle_ip_check, config.IP_CHECK_ADDR, config.IP_CHECK_PORT
    )

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    log.info('Listening for heartbeats on: %s', addrs)
    log.info('='*60)

    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("IP Check server stopped.")
