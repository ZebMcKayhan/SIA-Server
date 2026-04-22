#!/usr/bin/env python3
"""
Honeywell Galaxy Flex - Encrypted SIA Test Server (Proof of Concept)

Note: This is a diagnostic/proof-of-concept file intended to handle the 
key-exchange handshake and receive encrypted messages to display them on screen.

It has been tested using Engineering test messages and full alarm cascades.
It successfully receives, decrypts and parses all encrypted SIA data.

If you are experiencing issues with the main sia-server.py, you can run this
file directly for diagnostic purposes.

Requirements:
    pip install pycryptodome
"""
import asyncio
import logging
import binascii
from Cryptodome.PublicKey import RSA
from Cryptodome.Cipher import AES

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

LISTEN_ADDR, LISTEN_PORT = '0.0.0.0', 10000

# --- Protocol Constants ---
START_ENC_HEADER   = b'\x05\x01'           # First 2 bytes for detection
SERVER_KEY_HEADER  = b'\x08\x01\x01\x01\x00'
PANEL_KEY_HEADER   = b'\x88\x01'
KEY_ACK_HEADER     = b'\x50\x01\x84\x01\x00'
DECRYPTED_HEADER   = b'\xbe\x01'

def _calc_crc(data: bytes) -> bytes:
    """Calculates CRC-16/XMODEM using the standard library."""
    return binascii.crc_hqx(data, 0x0000).to_bytes(2, 'big')

def print_hex(label: str, data: bytes):
    """Print a hex dump with a label."""
    hex_str = ' '.join(f'{b:02x}' for b in data)
    print(f"  {label}: {hex_str}")
    print(f"  {' ' * len(label)}  ({len(data)} bytes)")

def create_encrypted_ack(cipher_aes) -> bytes:
    """Creates a correctly framed and encrypted SIA ACK."""
    sia_ack = bytes([0x40, 0x38])
    checksum = 0xFF
    for byte in sia_ack:
        checksum ^= byte
    length = len(sia_ack) + 1
    plaintext = bytes([length]) + sia_ack + bytes([checksum])
    plaintext = plaintext + b'\x00' * (16 - len(plaintext))
    print_hex("Plaintext ACK", plaintext)
    encrypted = cipher_aes.encrypt(plaintext)
    print_hex("Encrypted ACK", encrypted)
    return encrypted

async def handle_encrypted_session(reader, writer):
    addr = writer.get_extra_info('peername')
    log.info(f"{'='*80}\nNEW CONNECTION from {addr}\n{'='*80}")

    try:
        # ===================================================================
        # STEP 1: Receive and validate StartEnc frame
        # ===================================================================
        log.info("STEP 1: Waiting for StartEnc...")
        data = await reader.read(1024)

        if not data.startswith(START_ENC_HEADER):
            log.error("ERROR: Data does not start with StartEnc header. Aborting.")
            return

        if len(data) != 5:
            log.error("ERROR: StartEnc frame is not 5 bytes. Got %d bytes. Aborting.", len(data))
            return

        if not data.endswith(_calc_crc(data[:-2])):
            log.error("ERROR: StartEnc frame has invalid CRC. Aborting.")
            log.error("  Received CRC:   %s", data[-2:].hex())
            log.error("  Calculated CRC: %s", _calc_crc(data[:-2]).hex())
            return

        log.info("✓ Valid StartEnc received")
        print_hex("StartEnc frame", data)

        # ===================================================================
        # STEP 2: Generate RSA-1024 keypair (e=3) and send ServerKey
        # ===================================================================
        log.info("\nSTEP 2: Generating RSA-1024 keypair (e=3)...")
        rsa_key = RSA.generate(1024, e=3)
        log.info("✓ RSA key generated")
        log.info("  Public exponent (e): %d", rsa_key.e)
        log.info("  Modulus (n): %s...", str(rsa_key.n)[:60])

        # Send modulus in little-endian (panel native format)
        modulus_le = rsa_key.n.to_bytes(128, 'little')
        server_key_payload = SERVER_KEY_HEADER + modulus_le
        server_key_frame = server_key_payload + _calc_crc(server_key_payload)

        log.info("Sending ServerKey to panel...")
        print_hex("ServerKey frame", server_key_frame)
        writer.write(server_key_frame)
        await writer.drain()
        log.info("✓ ServerKey sent")

        # ===================================================================
        # STEP 3: Receive and validate PanelKey
        # ===================================================================
        log.info("\nSTEP 3: Waiting for PanelKey...")

        try:
            panel_key_frame = await asyncio.wait_for(
                reader.readexactly(132),
                timeout=3.0
            )
        except asyncio.TimeoutError:
            log.error("ERROR: Timeout waiting for PanelKey.")
            return
        except asyncio.IncompleteReadError as e:
            log.error("ERROR: Connection closed early. Expected 132 bytes, got %d.", len(e.partial))
            return

        print_hex("PanelKey frame received", panel_key_frame)

        if not panel_key_frame.startswith(PANEL_KEY_HEADER):
            log.error("ERROR: PanelKey frame has invalid header. Aborting.")
            return

        if not panel_key_frame.endswith(_calc_crc(panel_key_frame[:-2])):
            log.error("ERROR: PanelKey frame has invalid CRC. Aborting.")
            log.error("  Received CRC:   %s", panel_key_frame[-2:].hex())
            log.error("  Calculated CRC: %s", _calc_crc(panel_key_frame[:-2]).hex())
            return

        log.info("✓ PanelKey frame is valid")

        # ===================================================================
        # STEP 4: Decrypt RSA block and validate its contents
        # ===================================================================
        log.info("\nSTEP 4: Decrypting RSA block...")

        encrypted_block = panel_key_frame[2:-2]
        print_hex("Encrypted RSA block (128 bytes)", encrypted_block)

        encrypted_int = int.from_bytes(encrypted_block, 'little')
        decrypted_int = pow(encrypted_int, rsa_key.d, rsa_key.n)
        decrypted_block = decrypted_int.to_bytes(128, 'little')

        print_hex("Decrypted RSA block (128 bytes)", decrypted_block)

        # Validate internal structure
        header             = decrypted_block[0:2]
        key1               = decrypted_block[2:18]
        key2               = decrypted_block[20:36]
        internal_crc_bytes = decrypted_block[36:38]
        data_to_check      = decrypted_block[0:36]

        log.info("  Internal header:  %s (expected: %s)", header.hex(), DECRYPTED_HEADER.hex())
        log.info("  AES Key (copy 1): %s", key1.hex())
        log.info("  AES Key (copy 2): %s", key2.hex())
        log.info("  Internal CRC:     %s", internal_crc_bytes.hex())

        if header != DECRYPTED_HEADER:
            log.error("ERROR: Decrypted block has invalid internal header!")
            log.error("  Expected: %s", DECRYPTED_HEADER.hex())
            log.error("  Got:      %s", header.hex())
            return

        if key1 != key2:
            log.error("ERROR: AES key copies do not match!")
            log.error("  Copy 1: %s", key1.hex())
            log.error("  Copy 2: %s", key2.hex())
            return

        calculated_internal_crc = _calc_crc(data_to_check)
        if internal_crc_bytes != calculated_internal_crc:
            log.error("ERROR: Decrypted block internal CRC mismatch!")
            log.error("  Received:   %s", internal_crc_bytes.hex())
            log.error("  Calculated: %s", calculated_internal_crc.hex())
            return

        aes_session_key = key1
        log.info("✓ All internal validation checks passed")
        print_hex("AES Session Key (16 bytes)", aes_session_key)

        # ===================================================================
        # STEP 5: Send KeyAck
        # ===================================================================
        log.info("\nSTEP 5: Sending KeyAck...")
        key_ack_frame = KEY_ACK_HEADER + _calc_crc(KEY_ACK_HEADER)
        print_hex("KeyAck frame", key_ack_frame)
        writer.write(key_ack_frame)
        await writer.drain()
        log.info("✓ Handshake complete! Encrypted session is now active.")

        # ===================================================================
        # STEP 6: Encrypted data loop
        # ===================================================================
        log.info("\nSTEP 6: Entering encrypted data loop...")
        log.info(f"{'='*80}")

        cipher_aes = AES.new(aes_session_key, AES.MODE_ECB)
        message_count = 0

        while True:
            log.info(f"\nWaiting for encrypted message #{message_count + 1}...")
            encrypted_data = await reader.read(32)

            if not encrypted_data:
                log.info("Panel closed connection.")
                break

            message_count += 1
            log.info(f"--- MESSAGE #{message_count} ---")
            print_hex("Encrypted data", encrypted_data)

            # Validate block size
            if len(encrypted_data) % 16 != 0:
                log.error("ERROR: Received data length (%d) is not a multiple of 16!", len(encrypted_data))
                continue

            # Decrypt in 16-byte blocks
            decrypted_data = b''
            for i in range(0, len(encrypted_data), 16):
                block = encrypted_data[i:i+16]
                decrypted_data += cipher_aes.decrypt(block)

            print_hex("Full decrypted message (with length prefix)", decrypted_data)

            # Parse the length prefix and slice out the clean SIA frame
            if not decrypted_data:
                continue

            actual_frame_len = decrypted_data[0]
            log.info("  Frame length prefix: %d bytes of SIA data", actual_frame_len)

            sia_frame = decrypted_data[1 : 1 + actual_frame_len]
            print_hex("SIA frame (Length+Cmd+Payload+CRC)", sia_frame)

            if len(sia_frame) < 3:
                log.warning("  SIA frame is too short to parse (%d bytes).", len(sia_frame))
                continue

            # Parse SIA frame fields
            length    = sia_frame[0]
            command   = chr(sia_frame[1]) if 32 <= sia_frame[1] <= 126 else '?'
            payload   = sia_frame[2:-1] if len(sia_frame) > 2 else b''
            checksum  = sia_frame[-1]
            ascii_payload = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in payload)

            log.info("  SIA Length:          0x%02x", length)
            log.info("  SIA Command:         '%s' (0x%02x)", command, sia_frame[1])
            log.info("  SIA Payload (hex):   %s", payload.hex() if payload else '(none)')
            log.info("  SIA Payload (ASCII): %s", ascii_payload)
            log.info("  SIA Checksum:        0x%02x", checksum)

            # Verify SIA checksum
            calc_checksum = 0xFF
            for byte in sia_frame[:-1]:
                calc_checksum ^= byte

            if calc_checksum == checksum:
                log.info("  ✓ SIA checksum valid")
            else:
                log.error("  ❌ SIA checksum MISMATCH! Calculated: 0x%02x, Expected: 0x%02x",
                          calc_checksum, checksum)

            # Send encrypted ACK
            log.info("Sending encrypted ACK...")
            ack = create_encrypted_ack(cipher_aes)
            writer.write(ack)
            await writer.drain()
            log.info("✓ ACK sent")
            log.info("----------------------")

    except asyncio.IncompleteReadError:
        log.info("Panel closed connection (incomplete read).")
    except Exception as e:
        log.error("ERROR: An unexpected error occurred: %s", e, exc_info=True)
    finally:
        log.info("Closing connection.")
        writer.close()
        await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle_encrypted_session, LISTEN_ADDR, LISTEN_PORT)
    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    log.info("="*80)
    log.info("Galaxy Encrypted SIA - Proof of Concept Test Server")
    log.info("Listening on: %s", addrs)
    log.info("="*80)
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
