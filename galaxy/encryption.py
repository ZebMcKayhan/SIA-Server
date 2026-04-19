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
START_ENC_HDR = b'\x05\x01' # The first two bytes for quick detection

# --- Internal Helper Constants and Functions (private to this module) ---
_SERVER_KEY_HEADER = b'\x08\x01\x01\x01\x00'
_KEY_ACK_FRAME = b'\x50\x01\x84\x01\x00\xb7\x2d'

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

# --- Public Function (to be defined next) ---
async def do_handshake(reader, writer, data, log) -> CryptoContext | None:
    # We will implement this function in the next step.
    pass
