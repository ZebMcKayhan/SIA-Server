"""
Module for handling the Honeywell Galaxy Flex proprietary encrypted SIA protocol.
This is an optional dependency for the main SIA server. It requires 'pycryptodome'.
"""
import asyncio
import logging
import binascii
from Cryptodome.PublicKey import RSA
from Cryptodome.Cipher import AES

# Get a logger instance that will inherit its configuration from the main server.
log = logging.getLogger(__name__)

# --- Public Constants (to be imported by sia-server.py) ---
START_ENC_HEADER = b'\x05\x01' # The first two bytes for quick detection

# --- Internal Helper Constants and Functions (private to this module) ---
_SERVER_KEY_HEADER = b'\x08\x01\x01\x01\x00'
_PANEL_KEY_HEADER = b'\x88\x01'
_DECRYPTED_HEADER = b'\xbe\x01'
_KEY_ACK_HEADER = b'\x50\x01\x84\x01\x00'

def _calc_crc(data: bytes) -> bytes:
    """Calculates CRC-16/XMODEM using the standard library."""
    return binascii.crc_hqx(data, 0x0000).to_bytes(2, 'big')

# --- Public Class ---
class CryptoContext:
    """
    Holds the state (AES cipher) for an active encrypted session and provides
    methods to wrap/unwrap SIA frames.
    """
    def __init__(self, aes_key: bytes):
        self.cipher = AES.new(aes_key, AES.MODE_ECB)

    def decrypt(self, encrypted_data: bytes) -> bytes:
        """
        Decrypts one or more AES blocks and unwraps the clean SIA frame.
        Returns a byte string ready for validate_and_strip().
        """
        if len(encrypted_data) % 16 != 0:
            log.error("Received encrypted data with a length (%d) that is not a multiple of 16. Discarding.", len(encrypted_data))
            return b''
        
        decrypted_padded = b''
        # Decrypt the raw data in 16-byte chunks.
        for i in range(0, len(encrypted_data), 16):
            block = encrypted_data[i:i+16]
            if len(block) == 16:
                decrypted_padded += self.cipher.decrypt(block)
        
        if not decrypted_padded:
            log.warning("Decryption resulted in an empty byte string.")
            return b''

        # The first byte of the decrypted data is the length of the actual SIA frame.
        sia_frame_len = decrypted_padded[0]
        
        # Slice out the clean SIA frame and return it.
        clean_sia_frame = decrypted_padded[1 : 1 + sia_frame_len]
        log.debug("Decrypted and unwrapped clean SIA frame: %r", clean_sia_frame)
        return clean_sia_frame

    def encrypt(self, clean_sia_frame: bytes) -> bytes:
        """
        Takes a clean SIA frame from build_and_send(), wraps it with a
        length prefix, pads it, and encrypts it for sending.
        """
        # Add the length prefix, which is the length of the clean SIA frame itself.
        prefixed_frame = bytes([len(clean_sia_frame)]) + clean_sia_frame
        
        # Pad the result to the next 16-byte boundary.
        padding_needed = 16 - (len(prefixed_frame) % 16)
        if padding_needed == 16: padding_needed = 0 # It's already a multiple of 16
        padded_block = prefixed_frame + (b'\x00' * padding_needed)
        
        log.debug("Plaintext block to be encrypted: %r", padded_block)
        return self.cipher.encrypt(padded_block)

async def do_handshake(reader, writer, data: bytes, log) -> CryptoContext | None:
    """
    Performs the full RSA handshake and returns a CryptoContext on success.
    
    This function takes over the connection after the initial StartEnc header
    is detected and handles the entire key exchange process.
    
    Args:
        reader: The asyncio StreamReader for the connection.
        writer: The asyncio StreamWriter for the connection.
        data: The initial 5-byte StartEnc frame received from the panel.
        log: The logger instance from the main server.

    Returns:
        A new CryptoContext object on successful handshake, or None on failure.
    """
    try:
        # --- Step 1: Validate the incoming StartEnc frame ---
        log.debug("ENCRYPTION: Step 1/5 - Validating StartEnc frame...")
        if len(data) != 5:
            log.error("Handshake Error: StartEnc frame is not 5 bytes long. Got %d bytes.", len(data))
            return None
        if data[2:] != _calc_crc(data[:3]):
            log.error("Handshake Error: StartEnc frame has an invalid CRC.")
            return None
        log.debug("✓ StartEnc frame is valid.")

        # --- Step 2: Generate and send the ServerKey ---
        log.debug("ENCRYPTION: Step 2/5 - Generating and sending ServerKey...")
        rsa_key = RSA.generate(1024, e=3)
        modulus_le = rsa_key.n.to_bytes(128, 'little')
        
        server_key_payload = _SERVER_KEY_HEADER + modulus_le
        server_key_frame = server_key_payload + _calc_crc(server_key_payload)
        
        writer.write(server_key_frame)
        await writer.drain()
        log.debug("✓ ServerKey sent.")

        # --- Step 3: Receive and validate the PanelKey ---
        log.debug("ENCRYPTION: Step 3/5 - Receiving and validating PanelKey...")
        try:
            panel_key_frame = await asyncio.wait_for(
                reader.readexactly(132),
                timeout=3.0  # A reasonable timeout for the panel to respond
            )
        except asyncio.TimeoutError:
            log.error("Handshake Error: Timeout while waiting for PanelKey.")
            return None
        except asyncio.IncompleteReadError as e:
            log.error(
                "Handshake Error: Connection closed by panel while sending PanelKey. Expected 132 bytes, got %d.",
                len(e.partial)
            )
            return None
        if not panel_key_frame.startswith(_PANEL_KEY_HEADER):
            log.error("Handshake Error: PanelKey frame has an invalid header.")
            return None
        if panel_key_frame[-2:] != _calc_crc(panel_key_frame[:-2]):
            log.error("Handshake Error: PanelKey frame has an invalid CRC.")
            return None
        log.debug("✓ PanelKey frame is valid.")

        # --- Step 4: Decrypt the RSA block and validate its contents ---
        log.debug("ENCRYPTION: Step 4/5 - Decrypting and validating session key...")
        encrypted_block = panel_key_frame[2:-2]
        
        encrypted_int = int.from_bytes(encrypted_block, 'little')
        decrypted_int = pow(encrypted_int, rsa_key.d, rsa_key.n)
        decrypted_block = decrypted_int.to_bytes(128, 'little')
        
        # Perform all internal validation checks
        header = decrypted_block[0:2]
        key1 = decrypted_block[2:18]
        key2 = decrypted_block[20:36]
        internal_crc_bytes = decrypted_block[36:38]
        data_to_check = decrypted_block[0:36]
        
        if header != _DECRYPTED_HEADER:
            log.error("Handshake Error: Decrypted block has invalid internal header. Expected '%s', got '%s'",
                      _DECRYPTED_HEADER.hex(), header.hex())
            return None
        
        if key1 != key2:
            log.error("Handshake Error: AES key copies in decrypted block do not match!")
            return None
        
        calculated_crc = _calc_crc(data_to_check)
        if internal_crc_bytes != calculated_crc:
            log.error("Handshake Error: Decrypted block internal CRC mismatch. Expected '%s', got '%s'",
                      internal_crc_bytes.hex(), calculated_crc.hex())
            return None
            
        log.debug("✓ Decrypted block passed all internal validation checks.")
        aes_session_key = key1
        
        # --- Step 5: Send the final KeyAck ---
        log.debug("ENCRYPTION: Step 5/5 - Sending KeyAck...")
        key_ack_frame = _KEY_ACK_HEADER + _calc_crc(_KEY_ACK_HEADER)
        writer.write(key_ack_frame)
        await writer.drain()
        log.debug("✓ Handshake successful. Encrypted session is now active.")
        
        return CryptoContext(aes_session_key)

    except asyncio.IncompleteReadError:
        log.error("Handshake Error: Connection closed by panel prematurely.")
        return None
    except Exception as e:
        log.error(f"Handshake Error: An unexpected error occurred: {e}", exc_info=True)
        return None
