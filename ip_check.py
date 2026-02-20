#!/usr/bin/env python3
"""
Galaxy IP Check (Heartbeat) Server

Listens on a dedicated port for the proprietary Honeywell "Path Viability Check"
ping. It echoes the received data back to the panel and closes the connection.
This script is intended to be run as a subprocess by sia-server.py.
"""

import asyncio
import logging
import sys

# --- SCRIPT INITIALIZATION ---

# 1. Import the new configuration loader FIRST.
from configuration import load_and_validate_config

# 2. Load and validate all configuration from files.
# This single 'config' object holds all settings.
config = load_and_validate_config()

# --- Smart Logging Setup for Subprocess ---
# This logger is intentionally simple. It prefixes messages with the log level
# so the parent process (sia-server.py) can parse it and apply full formatting.
log = logging.getLogger('ip_check_server')
log.setLevel(getattr(logging, config.LOG_LEVEL, 'INFO'))
formatter = logging.Formatter('%(levelname)s:%(message)s')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
log.addHandler(handler)

# 3. Now, import the rest of our modules.
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass # uvloop is optional

# We don't need COMMAND_BYTES anymore since we are just echoing data.

# --- END INITIALIZATION ---

async def handle_ip_check(reader, writer):
    """Handles an incoming IP Check connection by echoing the received data."""
    addr = writer.get_extra_info('peername')
    
    try:
        data = await reader.read(1024)
        if not data:
            return

        log.info("Received %d-byte ping from %s. Echoing response.", len(data), addr[0])
        log.debug("Ping HEX: %s", data.hex())
        
        # Echo the exact same data back to the panel.
        writer.write(data)
        await writer.drain()

        # Wait for the panel to close the connection.
        await reader.read(-1)
        log.info("Panel at %r has closed the connection.", addr)

    except asyncio.IncompleteReadError:
        log.info("Panel at %r has closed the connection (IncompleteReadError).", addr)
    except Exception as e:
        log.error("Error in IP Check handler for %s: %s", addr[0], e)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

async def start_ip_check_server(): # Renamed from 'main' to be an async function
    """The main async function to start the server."""
    
    if not config.IP_CHECK_ENABLED:
        if sys.stdout.isatty():
            # This print is for when a user tries to run it directly while disabled
            print("IP Check server is disabled in sia-server.conf. Exiting.")
        return

    log.info("="*50)
    log.info("Starting Galaxy IP Check (Heartbeat) Server")
    
    # We move the try...except block here, inside the async function
    try:
        server = await asyncio.start_server(
            handle_ip_check, config.IP_CHECK_ADDR, config.IP_CHECK_PORT
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
        return # Gracefully exit the async function

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    log.info('Listening for heartbeats on: %s', addrs)
    log.info("="*50)

    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    # The main execution block is now just a simple try...except wrapper
    try:
        asyncio.run(start_ip_check_server())
    except (KeyboardInterrupt, SystemExit):
        log.info("IP Check server stopped.")
