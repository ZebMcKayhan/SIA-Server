#!/usr/bin/env python3
"""
Galaxy IP Check (Heartbeat) Server

Listens on a dedicated port for the proprietary Honeywell "Path Viability Check"
ping. It echoes the received data back to the panel and closes the connection.
This script is intended to be run as a subprocess by sia-server.py.
"""

import argparse
import asyncio
import logging
import sys

# --- SCRIPT INITIALIZATION ---
# 1. Parse arguments
parser = argparse.ArgumentParser(description='Galaxy IP Check Server')
parser.add_argument(
    '--config',
    default='sia-server.conf',
    help='Path to configuration file (default: sia-server.conf)'
)
args = parser.parse_args()

# 2. Import configuration loader
from configuration import load_logging_config, load_full_config

# 3. Load ONLY logging config first 
logging_config = load_logging_config(args.config)

# --- Logging Setup for Subprocess ---
# 4. Configure the ROOT logger so all modules (including notification.py)
# automatically inherit the same handler and format.
# Format transports level, logger name and message to sia-server.py for formatting.
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, logging_config.LOG_LEVEL, 'INFO'))
root_logger.handlers.clear()
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
root_logger.addHandler(handler)

log = logging.getLogger(__name__)

# 5. NOW load full config - logging is ready so all warnings/errors are captured
config = load_full_config(args.config)

# 6. Now, import the rest of our modules.
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass # uvloop is optional

# --- Optional Encryption Support ---
ENCRYPTION_AVAILABLE = False
START_ENC_HEADER = b'\x05\x01'
CryptoContext = None
do_handshake = None
try:
    from galaxy.encryption import do_handshake, CryptoContext, START_ENC_HEADER
    ENCRYPTION_AVAILABLE = True
    log.debug("Encryption modules loaded.")
except (ImportError, ModuleNotFoundError):
    pass
    
# --- END INITIALIZATION ---

def validate_ip_check_packet(data: bytes) -> bool:
    """
    Validates an incoming IP Check packet.
    Returns True if the packet is valid, False otherwise.
    
    Validation checks:
    1. Length must be exactly 26 bytes
    2. First byte (header) must be 0x00
    3. Checksum - algorithm unknown, not validated
    """
    # Check 1: Length
    if len(data) != 26:
        log.debug("IP Check: Invalid length %d (expected 26)", len(data))
        return False
    
    # Check 2: Header byte
    if data[0] != 0x00:
        log.debug("IP Check: Invalid header byte 0x%02x (expected 0x00)", data[0])
        return False
    
    # Check 3: checksum

    # Algo unknown...
    
    return True

def extract_account(data: bytes) -> str:
    """Extract account number from IP Check packet bytes 1-8."""
    return data[1:9].decode('ascii', errors='ignore').lstrip('0')
    
async def handle_ip_check(reader, writer):
    """Handles an incoming IP Check connection by echoing the received data."""
    addr = writer.get_extra_info('peername')
    crypto = None
    
    try:
        data = await reader.read(1024)
        if not data:
            return

        # --- Encryption detection ---
        if data.startswith(START_ENC_HEADER):
            if ENCRYPTION_AVAILABLE:
                log.debug("Encrypted header detected from %s", addr[0])
                crypto = await do_handshake(reader, writer, data, log)
                if crypto is None:
                    #log.warning("IP Check handshake failed from %s - ignored.", addr[0])
                    return
                # Read the actual ping after handshake
                log.info("Encrypted session established from %r", addr)
                data = await reader.read(1024)
                if not data:
                    return
            else:
                log.warning("Encrypted session requested from %s but encryption not available - ignored.", addr[0])
                return

        # Decrypt if encrypted session
        if crypto:
            data = crypto.decrypt(data)
            
        log.debug("Ping HEX: %s", data.hex())
        # Validate the packet before responding
        if not validate_ip_check_packet(data):
            log.debug("Invalid IP Check packet from %s - ignored.", addr[0])
            return  # Silent drop

        # --- ACCOUNT POLICY ENFORCEMENT ---
        account_number = extract_account(data)
        policy = config.ACCOUNT_POLICIES.get(
            account_number,
            config.ACCOUNT_POLICIES.get('default', 'yes')
        )
        is_encrypted = crypto is not None

        if policy == 'no':
            log.warning("IP Check from disabled account '%s' - ignored.", account_number)
            return

        if policy == 'secure' and not is_encrypted:
            log.warning("IP Check from '%s' requires encrypted connection - ignored.", account_number)
            return

        log.debug("IP Check account '%s' policy satisfied.", account_number)
        site_name = config.ACCOUNT_SITES.get(account_number, account_number)
        log.info("Received ping from site: %s (Account: %s) from %s. Echoing response.",
                 site_name, account_number, addr[0])

        response = crypto.encrypt(data) if crypto else data
        # Echo the exact same data back to the panel.
        writer.write(response)
        await writer.drain()

        # Wait for the panel to close the connection.
        # Note: The panel closes the connection after 15s:
        await reader.read(-1)
        log.debug("Panel at %r has closed the connection.", addr)

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
            pass  # Client already closed the connection
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
