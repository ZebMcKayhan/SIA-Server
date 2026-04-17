#!/usr/bin/env python3
"""
Honeywell Galaxy Flex - Encrypted SIA Test Server

Note: This is just a proof-of-concept file that is meant to handle the key-exchange handshake and receive 
encrypted messages to display them on the screen. 

It has been tested using Engineering test messages, but nothing else. But it successfully receives the encrypted data.

It requires to install the folowing python modules:
cryptodome
crcmod
"""
import asyncio
import logging
from Cryptodome.PublicKey import RSA
from Cryptodome.Cipher import AES
import crcmod

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)
LISTEN_ADDR, LISTEN_PORT = '0.0.0.0', 10000
EXPECTED_START_ENC = b'\x05\x01\x81\x59\x68'
SERVER_KEY_HEADER = b'\x08\x01\x01\x01\x00'
KEY_ACK_FRAME = b'\x50\x01\x84\x01\x00\xb7\x2d'
crc16_xmodem = crcmod.predefined.mkCrcFun('xmodem')

def calc_crc(data: bytes) -> bytes:
    return crc16_xmodem(data).to_bytes(2, 'big')

def print_hex(label: str, data: bytes):
    hex_str = ' '.join(f'{b:02x}' for b in data)
    print(f"  {label}: {hex_str}")
    print(f"  {' ' * len(label)}  ({len(data)} bytes)")

def create_encrypted_ack(cipher_aes) -> bytes:
    sia_ack = bytes([0x40, 0x38])
    checksum = 0xFF
    for byte in sia_ack: checksum ^= byte
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
        # --- HANDSHAKE LOGIC ---
        log.info("STEP 1: Waiting for StartEnc...")
        data = await reader.read(5)
        if data != EXPECTED_START_ENC: return
        log.info("✓ Valid StartEnc received")
        
        log.info("\nSTEP 2: Generating RSA-1024 keypair (e=3)...")
        rsa_key = RSA.generate(1024, e=3)
        log.info(f"✓ RSA key generated")
        
        modulus_le = rsa_key.n.to_bytes(128, 'little')
        server_key_payload = SERVER_KEY_HEADER + modulus_le
        server_key_frame = server_key_payload + calc_crc(server_key_payload)
        
        log.info("Sending ServerKey to panel...")
        writer.write(server_key_frame)
        await writer.drain()
        log.info("✓ ServerKey sent")
        
        log.info("\nSTEP 3: Waiting for PanelKey...")
        data = await reader.read(132)
        if len(data) != 132 or data[-2:] != calc_crc(data[:-2]): return
        log.info("✓ PanelKey CRC valid")
        
        encrypted_block = data[2:-2]
        encrypted_int = int.from_bytes(encrypted_block, 'little')
        decrypted_int = pow(encrypted_int, rsa_key.d, rsa_key.n)
        decrypted_block = decrypted_int.to_bytes(128, 'little')
        
        aes_session_key = decrypted_block[2:18]
        log.info("✓ AES session key extracted")
        print_hex("AES Session Key", aes_session_key)

        log.info("\nSTEP 4: Sending KeyAck...")
        writer.write(KEY_ACK_FRAME)
        await writer.drain()
        log.info("✓ Handshake complete!")
        # --- END OF HANDSHAKE ---
        
        log.info("\nSTEP 5: Entering encrypted data loop...")
        log.info(f"{'='*80}")
        
        cipher_aes = AES.new(aes_session_key, AES.MODE_ECB)
        message_count = 0
        
        while True:
            log.info(f"\nWaiting for encrypted message #{message_count + 1}...")
            encrypted_data = await reader.read(32)
            
            if not encrypted_data:
                log.info("Panel closed connection")
                break
            
            message_count += 1
            log.info(f"--- MESSAGE #{message_count} ---")
            print_hex("Encrypted data", encrypted_data)
            
            decrypted_data = b''
            for i in range(0, len(encrypted_data), 16):
                block = encrypted_data[i:i+16]
                if len(block) == 16:
                    decrypted_data += cipher_aes.decrypt(block)
            
            print_hex("Full decrypted message (with length prefix)", decrypted_data)
            
            # *** PARSING LOGIC ***
            if not decrypted_data:
                continue

            # The first byte is the length of the actual SIA frame that follows.
            actual_frame_len = decrypted_data[0]
            log.info(f"  Frame length prefix indicates {actual_frame_len} bytes of SIA data.")
            
            # Slice out the real SIA frame
            sia_frame = decrypted_data[1 : 1 + actual_frame_len]
            print_hex("SIA frame (Length+Cmd+Payload+CRC)", sia_frame)

            if len(sia_frame) < 3:
                log.warning("  Sliced SIA frame is too short to parse.")
                continue

            # Now parse the correctly sliced frame
            length = sia_frame[0]
            command = chr(sia_frame[1]) if 32 <= sia_frame[1] <= 126 else '?'
            payload = sia_frame[2:-1] if len(sia_frame) > 2 else b''
            checksum = sia_frame[-1] if len(sia_frame) > 0 else 0
            ascii_payload = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in payload)

            log.info(f"  SIA Length:   0x{length:02x}")
            log.info(f"  SIA Command:  '{command}' (0x{sia_frame[1]:02x})")
            log.info(f"  SIA Payload (hex):   {payload.hex() if payload else '(none)'}")
            log.info(f"  SIA Payload (ASCII): {ascii_payload}")
            log.info(f"  SIA Checksum: 0x{checksum:02x}")
            
            # Verify checksum (calculated on the entire sliced SIA frame, except its own checksum)
            data_to_check = sia_frame[:-1]
            log.info("  Data being used for checksum calculation:")
            print_hex("    Bytes to check", data_to_check)
            
            calc_checksum = 0xFF
            for byte in data_to_check:
                calc_checksum ^= byte
            
            if calc_checksum == checksum:
                log.info("  ✓ SIA checksum valid")
            else:
                log.error("  ❌ SIA checksum MISMATCH!")
                log.error(f"    Calculated: 0x{calc_checksum:02x}")

            # Send ACK
            log.info("Sending encrypted ACK...")
            ack = create_encrypted_ack(cipher_aes)
            writer.write(ack)
            await writer.drain()
            log.info("✓ ACK sent")
            log.info(f"----------------------")

    except asyncio.IncompleteReadError:
        log.info("Panel closed connection (incomplete read)")
    except Exception as e:
        log.error(f"ERROR: {e}", exc_info=True)
    
    finally:
        log.info("Closing connection")
        writer.close()
        await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle_encrypted_session, LISTEN_ADDR, LISTEN_PORT)
    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    log.info(f"Galaxy Encrypted SIA Test Server\nListening on: {addrs}")
    await server.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
