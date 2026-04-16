# Honeywell Galaxy Flex — Encrypted ARC Protocol
## Research Notes — Fully Reverse Engineered and Validated

This document describes the encrypted variant of the proprietary TCP-based protocol
used by the Honeywell Galaxy Flex ethernet module when communicating with an ARC
(Alarm Receiving Centre) server. It covers the complete encrypted session 
establishment and data transfer for SIA Level 3 (ARC notifications).

---

## Background

The Galaxy Flex ethernet module supports both plaintext and encrypted ARC
communication. Encryption is configured independently for notifications and remote
access in the panel settings. When encryption is enabled, the panel initiates a
proprietary key exchange before sending any SIA data.

This protocol was reverse engineered from:
- Captured network traffic (tcpdump) of both plaintext and encrypted sessions
- Decompiled Java source from the GX Remote Control Android APK (jadx)
- Native library analysis (libBackendFirmware.so) using Ghidra
- Live validation against a Honeywell Galaxy Flex panel

**Status**: ✅ **Fully working implementation validated** (April 2026)

The file included here **galaxy/SIA-ENC_POC.py** implements a proof-of-concept 
receiver that handles the encrypted handshake and decrypts the event data and
displays it on the screen. It requires the installation of crcmod and cryptodome
extensions to operate.

implementation in SIA-Server.py is pending.

---

## Encryption Architecture

The ARC notification path (SIA Level 3, panel-to-server) uses a **custom proprietary 
encryption scheme**:

- **Key exchange**: RSA-1024 with **e=3** (non-standard)
- **Number representation**: **Little-endian word order** (32-bit words)
- **Encryption**: Textbook RSA (no PKCS#1 padding)
- **Session encryption**: AES-128-ECB
- **Integrity**: CRC-16/XMODEM on handshake frames

### Critical Implementation Details

⚠️ **The panel uses non-standard cryptography:**

1. **RSA public exponent e=3** instead of the standard 65537.
2. **Little-endian multi-precision arithmetic** for RSA operations.
3. **Textbook RSA** without PKCS#1 v1.5 or OAEP padding.
4. **Raw modulus transmission** (128 bytes, not DER-encoded).

These were discovered through analysis of the native library functions:

    CDataEncryption::GeneratePublicKey        // Sets e=3 explicitly
    CDataEncryption::DecodePrivateKeyMessageBlock
    mpModExp                                   // Implements little-endian word order
    MTcomms::GenerateRSAKeys
    MTcomms::SendPPKComWithKey
    MTprot::Encrypt / Decrypt                  // Implements AES-128-ECB

---

## Frame Format

All handshake frames use a consistent structure:

    [Header bytes] [Payload] [CRC-16/XMODEM — 2 bytes, big-endian]

The CRC is calculated over all bytes **except** the CRC itself.

**CRC-16/XMODEM parameters:**

    Width:  16
    Poly:   0x1021
    Init:   0x0000
    RefIn:  False
    RefOut: False
    XorOut: 0x0000

Python implementation:

    import crcmod
    
    crc16_xmodem = crcmod.predefined.mkCrcFun('xmodem')
    
    def calc_crc(data: bytes) -> bytes:
        return crc16_xmodem(data).to_bytes(2, 'big')

---

## Handshake Sequence

The complete encrypted session establishment:

    Panel  →  Server:    5 bytes   StartEnc
    Server →  Panel:   135 bytes   ServerKey (RSA-1024 public key modulus)
    Panel  →  Server:  132 bytes   PanelKey  (RSA-encrypted session data)
    Server →  Panel:     7 bytes   KeyAck
    
    --- Handshake complete, all subsequent data is AES-128-ECB encrypted ---
    
    Panel  →  Server:   16 bytes   Encrypted SIA block (Account ID)
    Server →  Panel:    16 bytes   Encrypted ACK
    Panel  →  Server:   32 bytes   Encrypted SIA block (Event)
    Server →  Panel:    16 bytes   Encrypted ACK
    Panel  →  Server:   32 bytes   Encrypted SIA block (ASCII - optional)
    Server →  Panel:    16 bytes   Encrypted ACK
    Panel  →  Server:   16 bytes   Encrypted EndOfData
    Server →  Panel:    16 bytes   Encrypted AckAndDisconnect

---

## Frame Definitions

### StartEnc — Panel → Server (5 bytes)

    05 01 81 | 59 68

- `05 01 81` — Fixed header
- `59 68` — CRC-16/XMODEM of `05 01 81`

This is a **static, fixed sequence** that signals the panel requires encrypted communication.

### ServerKey — Server → Panel (135 bytes)

    08 01 01 01 00 | [128 bytes RSA modulus, little-endian] | [2 bytes CRC]

- `08 01 01 01 00` — Fixed 5-byte header
- 128 bytes — RSA-1024 public key **modulus (n)** in **little-endian byte order**
- 2 bytes — CRC-16/XMODEM of all preceding 133 bytes

⚠️ **Critical**: The modulus must be sent in **little-endian byte order** to match
the panel's multi-precision library format.

### PanelKey — Panel → Server (132 bytes)

    88 01 | [128 bytes RSA-encrypted session data] | [2 bytes CRC]

- `88 01` — Frame type header
- 128 bytes — RSA-encrypted block containing session data.
- 2 bytes — CRC-16/XMODEM

**Structure of data block (before RSA encryption):**

    [~39 bytes session data] [89 bytes zero padding]

After decryption, the **16-byte AES session key** is located at **bytes 2-17** of the 
decrypted 128-byte block. The first two bytes (`be 01`) appear to be metadata.

### KeyAck — Server → Panel (7 bytes)

    50 01 84 01 00 | b7 2d

- `50 01 84 01 00` — Fixed header
- `b7 2d` — CRC-16/XMODEM of `50 01 84 01 00`

This is a **static, fixed sequence** sent to acknowledge a successful key exchange.

---

## Encrypted Data Phase

After the handshake, all SIA messages are encrypted with **AES-128-ECB**.

### Block Structure (Decrypted)

Each decrypted AES block (16 or 32 bytes) has a framing structure where the first byte indicates the length of the actual SIA frame that follows.

    [SIA_Frame_Length] [Actual_SIA_Frame] [Padding]

The `Actual_SIA_Frame` follows the standard Honeywell SIA format:

    [Length] [Command] [Payload] [Checksum]

**Example decrypted block (Account ID):**

    09 46 23 30 32 37 39 37 38 99 ae ae ae ae ae ae
    |  └───────────┬───────────┘ └──────┬───────┘
    |              |                    └─ AES Padding
    |              └─ Actual SIA Frame (9 bytes)
    └─ Length Prefix: The SIA frame is 9 bytes long.

**Parsing the `Actual_SIA_Frame`:**

    46 23 30 32 37 39 37 38 99
    |  |  └───────┬──────┘  |
    |  |          |         └─ SIA Checksum (XOR of bytes 0-7)
    |  |          └─ SIA Payload (account: "027978")
    |  └─ SIA Command ('#')
    └─ SIA Length (with +0x40 offset)

### Encrypted Block Sizes

| SIA Block Type | Typical SIA Frame | Encrypted Size |
|:---------------|:-----------------|:---------------|
| Account ID     | ~9 bytes         | 16 bytes (1 AES block) |
| New Event      | ~19 bytes        | 32 bytes (2 AES blocks) |
| ASCII Text     | ~20 bytes        | 32 bytes (2 AES blocks) |
| End of Data    | 3 bytes          | 16 bytes (1 AES block) |
| ACK            | 3 bytes          | 16 bytes (1 AES block) |

---

## Core Implementation Logic

### RSA Key Exchange

    from Cryptodome.PublicKey import RSA
    
    # 1. Generate RSA-1024 keypair with non-standard e=3
    rsa_key = RSA.generate(1024, e=3)
    
    # 2. Export modulus in little-endian format to send to the panel
    modulus_le = rsa_key.n.to_bytes(128, 'little')
    
    # ... send ServerKey frame ...
    
    # 3. Receive PanelKey frame and extract the 128-byte encrypted block
    encrypted_block = panel_key_frame[2:-2]
    
    # 4. Decrypt using textbook RSA with little-endian integer representation
    encrypted_int = int.from_bytes(encrypted_block, 'little')
    decrypted_int = pow(encrypted_int, rsa_key.d, rsa_key.n)
    decrypted_block = decrypted_int.to_bytes(128, 'little')
    
    # 5. Extract AES key from the known offset (bytes 2-17)
    aes_session_key = decrypted_block[2:18]

### AES Message Processing

    from Cryptodome.Cipher import AES
    
    def process_sia_message(decrypted_data: bytes):
        """Parses a decrypted AES block."""
        
        # 1. The first byte is the length of the actual SIA frame.
        sia_frame_length = decrypted_data[0]
        
        # 2. Slice out the SIA frame.
        sia_frame = decrypted_data[1 : 1 + sia_frame_length]
        
        # 3. Validate the SIA checksum.
        # Checksum is calculated over the entire SIA frame except the last byte.
        data_to_check = sia_frame[:-1]
        expected_checksum = sia_frame[-1]
        
        calculated_checksum = 0xFF
        for byte in data_to_check:
            calculated_checksum ^= byte
        
        if calculated_checksum != expected_checksum:
            raise ValueError("SIA Checksum Mismatch!")
            
        # 4. The SIA frame is now valid and ready for processing.
        # ... parse command, payload, etc. ...

    def create_encrypted_ack(cipher_aes):
        """Creates a correctly framed and encrypted SIA ACK."""
        
        # SIA ACK data: Command='@' (0x40), Payload='8' (0x38)
        ack_data = b'\x40\x38'
        
        # Frame for checksum: [Length][Data]
        frame_to_check = bytes([len(ack_data)]) + ack_data
        
        # Calculate checksum
        checksum = 0xFF
        for byte in frame_to_check:
            checksum ^= byte
            
        # Full SIA frame: [Length][Data][Checksum]
        sia_ack_frame = frame_to_check + bytes([checksum])
        
        # Pre-encryption block: [SIA_Frame_Length][SIA_Frame][Padding]
        plaintext_block = bytes([len(sia_ack_frame)]) + sia_ack_frame
        plaintext_block += b'\x00' * (16 - len(plaintext_block))
        
        return cipher_aes.encrypt(plaintext_block)

---

## Security Considerations

⚠️ **This protocol uses weak cryptography:**

1. **RSA with e=3** is vulnerable to low-exponent and cube root attacks.
2. **Textbook RSA** (no padding) is vulnerable to chosen ciphertext attacks.
3. **AES-ECB mode** is vulnerable to pattern analysis and block reordering.
4. **No message authentication** (MAC); only non-cryptographic checksums.

**This protocol should be considered obfuscation rather than strong encryption.**
It provides protection against casual interception but not targeted attacks.

---

## Validation and Testing

This protocol implementation has been validated through:

✅ Successful RSA handshake with a live Galaxy Flex panel.  
✅ AES session key extraction and verification.  
✅ Full decryption of a multi-message SIA event sequence.  
✅ Successful SIA checksum validation for all received messages.  
✅ Successful session termination after sending ACKs.  

Test equipment:
- Honeywell Galaxy Flex 3-20 control panel
- GX Ethernet Module
- `galaxy/SIA-ENC_POC.py` test script

---

## References

- GX Remote Control Android APK — com.honeywell.galaxyapp.apk v4.5.0
- Native library — libBackendFirmware.so (ARM64)
- Ghidra reverse engineering tool
- Network captures and live panel testing (April 2026)
- Homey community forum thread:  
  https://community.homey.app/t/honeywell-galaxy-flex-alarm-with-ethernet-module/5991

---

## Legal Notice

This documentation was produced through independent security research for the purpose
of enabling interoperability with a legally owned device. No proprietary keys or
credentials are included. Any implementation requires the user to supply their own
panel configuration. This research is provided for educational and interoperability
purposes only. The authors make no warranties and accept no liability for the use of
this information.

**Status**: Protocol fully reverse engineered and working (2026-04-16)
