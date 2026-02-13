#!/usr/bin/env python3
"""
Galaxy IP Check (Heartbeat) Server

A minimal server that listens on a dedicated port for the proprietary
Honeywell "Path Viability Check" ping. It can send various responses
to test the panel's behavior.
"""
import asyncio
import logging
import sys
# The 'signal' import is not needed for this script
# import signal 

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
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(formatter)
log.addHandler(handler)

async def handle_ip_check(reader, writer):
    """
    Handles an incoming IP Check connection by sending an experimental response
    and waiting for the panel to close the connection.
    """
    addr = writer.get_extra_info('peername')
    log.info("Received IP Check connection from %r", addr)
    
    try:
        data = await reader.read(1024) # Read the panel's ping
        if not data:
            log.info("IP Check client connected but sent no data.")
            return

        log.info("Received IP Check ping: %r", data)
        
        # --- YOUR EXPERIMENT GOES HERE ---
        
        # Experiment 1: Send a standard REJECT
        command_to_send = 'REJECT'
        payload_to_send = b''
        
        # Experiment 2: Send a standard ACKNOWLEDGE
        # command_to_send = 'ACKNOWLEDGE'
        # payload_to_send = b''
        
        # Experiment 3: Send a custom, fixed byte string
        # custom_response = b'some test data'

        # --- END OF EXPERIMENT CONFIGURATION ---
        
        # Build and send the response based on the chosen experiment
        if 'custom_response' in locals():
            log.info("Sending custom response: %r", custom_response)
            writer.write(custom_response)
            await writer.drain()
        elif 'command_to_send' in locals():
            command_byte = COMMAND_BYTES[command_to_send]
            length_byte = len(payload_to_send) + 0x40
            message_part = bytes([length_byte, command_byte]) + payload_to_send
            checksum = 0xFF
            for byte in message_part:
                checksum ^= byte
            final_message = message_part + bytes([checksum])
            
            log.info("Sending experimental response (%s): %r", command_to_send, final_message)
            writer.write(final_message)
            await writer.drain()
        else:
            log.info("No response configured, will wait for panel to close.")

        
        # Now, wait indefinitely for the panel to close the connection
        log.info("Waiting for panel to close the connection...")
        await reader.read(-1)
        log.info("Panel at %r has closed the connection.", addr)

    except asyncio.IncompleteReadError:
        # This is the expected outcome when the other side closes the connection
        log.info("Panel at %r has closed the connection (IncompleteReadError).", addr)
    except Exception as e:
        log.error("Error in IP Check handler: %s", e)
    finally:
        log.info("Closing our side of the IP Check connection from %r", addr)
        writer.close()
        await writer.wait_closed()

async def main():
    if not hasattr(config, 'IP_CHECK_ENABLED') or not config.IP_CHECK_ENABLED:
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
