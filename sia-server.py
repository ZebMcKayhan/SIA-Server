#!/usr/bin/env python3
"""
Galaxy SIA Server

Receives SIA protocol messages from Galaxy Flex alarm systems,
parses events, and sends notifications via ntfy.sh.

Author: Built with assistance from Claude (Anthropic)
License: MIT
"""

import asyncio
import logging
import logging.handlers
import sys
import signal

import config
from galaxy.parser import parse_galaxy_event
from galaxy.notification import send_notification

# Try to use uvloop for performance, but fall back to standard asyncio on Windows
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("Using uvloop for event loop.")
except ImportError:
    print("uvloop not found, using standard asyncio event loop.")
    pass # On Windows, this will automatically use the standard ProactorEventLoop


def setup_logging():
    """Configure logging based on config.py settings"""
    
    log = logging.getLogger()
    
    # Avoid adding handlers multiple times if already configured
    if log.handlers:
        return log
        
    log.setLevel(getattr(logging, config.LOG_LEVEL))
    
    # Create formatter
    formatter = logging.Formatter(
        config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT
    )
    
    if config.LOG_TO_FILE:
        # Log to rotating file
        file_handler = logging.handlers.RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=config.LOG_MAX_BYTES,
            backupCount=config.LOG_BACKUP_COUNT
        )
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
        print(f"Logging to file: {config.LOG_FILE}")
    else:
        # Log to console/screen
        console_handler = logging.StreamHandler(stream=sys.stderr)
        console_handler.setFormatter(formatter)
        log.addHandler(console_handler)
        print("Logging to console")
    
    return log


# Setup logging
log = setup_logging()


async def handle_connection(reader, writer):
    """
    Handle incoming SIA connection from alarm panel.
    
    Collects all message blocks, sends ACKs, chunks them into separate events,
    parses each event, and sends notifications.
    """
    addr = writer.get_extra_info('peername')
    log.info("Connection from %r", addr)
    
    all_messages = []
    
    try:
        # --- 1. Collect all messages from the connection ---
        while True:
            data = await reader.read(1024)
            
            if not data:
                log.info("Connection closed by peer")
                break
            
            all_messages.append(data)
            
            # Log the raw block as it's received
            log.info("Received raw block: %r", data)
            log.debug("Raw block HEX: %s", data.hex())
            
            # Always send ACK
            writer.write(b'@8\x87')
            await writer.drain()
            log.debug("Sent ACK")
            
            # Break on close message
            if data.startswith(b'@0'):
                log.info("Close message received, ending collection")
                break
        
        if not all_messages:
            return
            
        # --- 2. Chunk all messages into separate events ---
        event_chunks = []
        current_chunk = []
        
        for msg in all_messages:
            # An event always starts with an account block, which has '#' as the second character
            if len(msg) >= 2 and msg[1:2] == b'#' and current_chunk:
                # This is the start of a new event, so save the previous one
                event_chunks.append(current_chunk)
                current_chunk = [msg]
            elif not msg.startswith(b'@0'):
                # Add message to the current event chunk
                current_chunk.append(msg)
        
        # Add the last chunk if it's not empty
        if current_chunk:
            event_chunks.append(current_chunk)
        
        log.info("Found %d distinct event(s) in this connection", len(event_chunks))

        # --- 3. Process each event chunk individually ---
        for i, chunk in enumerate(event_chunks, 1):
            log.info("--- Processing Event %d of %d ---", i, len(event_chunks))
            
            # Make sure the chunk is valid
            if len(chunk) < 2:
                log.warning("Skipping incomplete event chunk: %r", chunk)
                continue
                
            # Parse the event
            event = parse_galaxy_event(
                chunk,
                config.ACCOUNT_SITES,
                config.DEFAULT_SITE,
                config.UNKNOWN_CHAR_MAP
            )
            
            # Log parsed event details
            log.info("Site: %s (Account: %s)", event.site_name, event.account)
            log.info("Time: %s", event.time)
            log.info("Message Type: %s", event.message_type)
            log.info("Event Code: %s", event.event_code)
            if event.user_id:
                log.info("User ID: %s", event.user_id)
            if event.partition:
                log.info("Partition: %s", event.partition)
            if event.zone:
                log.info("Zone: %s", event.zone)
            if event.action_text:
                log.info("Action: %s", event.action_text)
            
            # Send notification
            notification_sent = send_notification(
                event,
                config.NTFY_URL,
                config.EVENT_PRIORITIES,
                config.DEFAULT_PRIORITY,
                config.NTFY_ENABLED,
                config.NOTIFICATION_TITLE
            )
            
            if notification_sent:
                log.info("Event processed and notification sent successfully")
            else:
                log.info("Event processed (notification skipped or failed)")
            
            log.info("--- Event %d complete ---", i)
        
    except Exception as e:
        log.error("Error handling connection: %s", e, exc_info=True)
    
    finally:
        log.info("Closing connection from %r", addr)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            log.error("Error closing connection: %s", e)


async def start_server(address, port):
    """
    Start the SIA server.
    
    Args:
        address: IP address to listen on
        port: Port number to listen on
    """
    server = await asyncio.start_server(handle_connection, address, port)
    
    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    log.info('='*60)
    log.info('Galaxy SIA Server Started')
    log.info('Listening on: %s', addrs)
    log.info('Notifications: %s', 'ENABLED' if config.NTFY_ENABLED else 'DISABLED')
    if config.NTFY_ENABLED:
        log.info('ntfy.sh URL: %s', config.NTFY_URL)
    log.info('='*60)
    
    async with server:
        await server.serve_forever()


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully"""
    log.info("Received shutdown signal (%d), stopping server...", signum)
    # The asyncio.run in main() will handle cleanup
    sys.exit(0)


def main():
    """Main entry point"""
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    log.info("Starting Galaxy SIA Server...")
    log.info("Configuration:")
    log.info("  Listen Address: %s", config.LISTEN_ADDR)
    log.info("  Listen Port: %d", config.LISTEN_PORT)
    log.info("  Log Level: %s", config.LOG_LEVEL)
    log.info("  Notifications: %s", 'Enabled' if config.NTFY_ENABLED else 'Disabled')
    log.info("  Configured Sites: %d", len(config.ACCOUNT_SITES))
    
    try:
        # Start the server
        asyncio.run(start_server(config.LISTEN_ADDR, config.LISTEN_PORT))
    except (KeyboardInterrupt, SystemExit):
        log.info("Server stopped")
    except Exception as e:
        log.error("Server error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
