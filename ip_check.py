#!/usr/bin/env python3
"""
Galaxy IP Check (Heartbeat) Server

Listens on a dedicated port for the proprietary Honeywell "Path Viability Check"
ping. It echoes the received data back to the panel and closes the connection.
While this may not be the "correct" response, it is a simple and
deterministic behavior for handling the proprietary heartbeat.
"""

import asyncio
import logging
import sys

# Make uvloop optional for cross-platform compatibility
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

# --- Configuration (can be run standalone or use config from sia-server) ---
try:
    import config
    IP_CHECK_ENABLED = getattr(config, 'IP_CHECK_ENABLED', True)
    IP_CHECK_ADDR = getattr(config, 'IP_CHECK_ADDR', '0.0.0.0')
    IP_CHECK_PORT = getattr(config, 'IP_CHECK_PORT', 10001)
    LOG_LEVEL = getattr(config, 'LOG_LEVEL', 'INFO')
except ImportError:
    # Standalone defaults if config.py is not present
    IP_CHECK_ENABLED = True
    IP_CHECK_ADDR = '0.0.0.0'
    IP_CHECK_PORT = 10001
    LOG_LEVEL = 'INFO'

# --- Smart Logging Setup ---
# This setup ensures logs are clean whether run as a subprocess or standalone.
log = logging.getLogger('ip_check_server')
# Check if a handler is already configured (e.g., by sia-server's logger)
if not log.hasHandlers():
    log.setLevel(LOG_LEVEL)
    # If run standalone, use a full formatter with timestamps.
    # If run as a subprocess, the parent will add the timestamp.
    is_standalone = sys.stdout.isatty()
    log_format = '%(asctime)s - IP_CHECK - %(message)s' if is_standalone else '%(message)s'
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    log.addHandler(handler)

async def handle_ip_check(reader, writer):
    """Handles an incoming IP Check connection by echoing the received data."""
    addr = writer.get_extra_info('peername')
    
    try:
        data = await reader.read(1024) # Read the panel's ping
        if not data:
            return # Client connected and immediately disconnected.

        # Log a single, clean line for this event at INFO level.
        log.info("Received %d-byte ping from %s. Echoing response.", len(data), addr[0])
        log.debug("Ping HEX: %s", data.hex()) # Keep detailed hex for DEBUG level
        
        # Echo the exact same data back to the panel.
        writer.write(data)
        await writer.drain()

    except Exception as e:
        log.error("Error in IP Check handler for %s: %s", addr[0], e)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass # Ignore errors on final close

async def main():
    if not IP_CHECK_ENABLED:
        if sys.stdout.isatty():
            print("IP Check server is disabled in config.py. Exiting.")
        return

    log.info("="*50)
    log.info("Starting Galaxy IP Check (Heartbeat) Server")
    
    try:
        server = await asyncio.start_server(
            handle_ip_check, IP_CHECK_ADDR, IP_CHECK_PORT
        )
    except OSError as e:
        log.error("Failed to start server on %s:%d - %s", IP_CHECK_ADDR, IP_CHECK_PORT, e)
        log.error("Check if the port is already in use or if you have permissions.")
        return

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    log.info('Listening for heartbeats on: %s', addrs)
    log.info("="*50)

    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
