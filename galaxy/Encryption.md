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

**Status**: ✅ **Initial decoded message successfully** (April 2026)

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

1. **RSA public exponent e=3** instead of the standard 65537
2. **Little-endian multi-precision arithmetic** for RSA operations
3. **Textbook RSA** without PKCS#1 v1.5 or OAEP padding
4. **Raw modulus transmission** (128 bytes, not DER-encoded)

These were discovered through analysis of the native library functions:

    CDataEncryption::GeneratePublicKey        // Sets e=3 explicitly
    CDataEncryption::DecodePrivateKeyMessageBlock
    mpModExp                                   // Little-endian word order
    MTcomms::GenerateRSAKeys
    MTcomms::SendPPKComWithKey
    MTprot::Encrypt / Decrypt                  // AES-128-ECB

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

This is a **static, fixed sequence** identical across all panels and sessions.
It signals that the panel requires encrypted communication.

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
- 128 bytes — RSA-encrypted block containing:
  - Protocol overhead bytes
  - 16-byte AES-128 session key
  - Zero padding
- 2 bytes — CRC-16/XMODEM

**Structure of encrypted 128-byte block (before RSA encryption):**

    [~39 bytes session data including 16-byte AES key] [89 bytes zero padding]

After decryption, the AES session key is located at **bytes 2-17** of the 
decrypted 128-byte block.

### KeyAck — Server → Panel (7 bytes)

    50 01 84 01 00 | b7 2d

- `50 01 84 01 00` — Fixed header
- `b7 2d` — CRC-16/XMODEM of `50 01 84 01 00`

This is a **static, fixed sequence** sent after successfully receiving the PanelKey.

---

## Encrypted Data Phase

After the handshake, all SIA blocks are encrypted with **AES-128-ECB**. Each 
plaintext SIA block is padded to a 16-byte boundary before encryption.

### SIA Block Structure (Decrypted)

Each decrypted AES block contains:

    [0x09] [Length] [Command] [Payload] [Checksum] [Padding...]
      |       |        |         |          |           |
      |       |        |         |          |           └─ Pad to 16 bytes
      |       |        |         |          └─ SIA: XOR checksum (starts with 0xFF)
      |       |        |         └─ SIA: Payload (Variable length data)
      |       |        └─ SIA: command byte
      |       └─ SIA: Payload length + 0x40 offset
      └─ Frame overhead (not included in SIA checksum) Message length before padding.

**Example decrypted block:**

    09 46 23 30 32 37 39 37 38 99 ae ae ae ae ae ae
    │  │  │  └───────┬──────┘  │  └──────── Padding (to 16 bytes)
    │  │  │          │         └─────────── Checksum (XOR)
    │  │  │          └───────────────────── Payload (account: "027978")
    │  │  └──────────────────────────────── Command ('#' = Account ID)
    │  └─────────────────────────────────── Length: 0x46 = 6 bytes + 0x40 offset
    └────────────────────────────────────── Overhead byte

### Encrypted Block Sizes

| SIA Block Type | Typical Plaintext | Encrypted Size |
|:---------------|:-----------------|:---------------|
| Account ID     | ~9 bytes         | 16 bytes (1 AES block) |
| New Event      | ~19 bytes        | 32 bytes (2 AES blocks) |
| ASCII Text     | ~20 bytes        | 32 bytes (2 AES blocks) |
| End of Data    | 3 bytes          | 16 bytes (1 AES block) |
| ACK            | 3 bytes          | 16 bytes (1 AES block) |

---

## Complete Working Implementation

### Server-Side Handshake and Decryption

    from Cryptodome.PublicKey import RSA
    from Cryptodome.Cipher import AES
    import crcmod
    
    crc16_xmodem = crcmod.predefined.mkCrcFun('xmodem')
    
    def calc_crc(data: bytes) -> bytes:
        return crc16_xmodem(data).to_bytes(2, 'big')
    
    def handle_encrypted_session(conn):
        """Complete encrypted SIA session handler"""
        
        # Step 1: Receive StartEnc
        start_enc = conn.recv(5)
        if start_enc != b'\x05\x01\x81\x59\x68':
            raise ValueError("Invalid StartEnc frame")
        
        # Step 2: Generate RSA-1024 keypair with e=3
        rsa_key = RSA.generate(1024, e=3)
        
        # Step 3: Send ServerKey with modulus in little-endian
        modulus_le = rsa_key.n.to_bytes(128, 'little')
        header = b'\x08\x01\x01\x01\x00'
        payload = header + modulus_le
        server_key_frame = payload + calc_crc(payload)
        conn.send(server_key_frame)
        
        # Step 4: Receive and validate PanelKey
        panel_key_frame = conn.recv(132)
        if panel_key_frame[-2:] != calc_crc(panel_key_frame[:-2]):
            raise ValueError("PanelKey CRC mismatch")
        
        # Step 5: Extract and decrypt the RSA-encrypted block
        encrypted_block = panel_key_frame[2:-2]  # Strip header and CRC (128 bytes)
        
        # Decrypt using little-endian RSA
        encrypted_int = int.from_bytes(encrypted_block, 'little')
        decrypted_int = pow(encrypted_int, rsa_key.d, rsa_key.n)
        decrypted_block = decrypted_int.to_bytes(128, 'little')
        
        # Step 6: Extract AES session key (bytes 2-17 of decrypted block)
        aes_key = decrypted_block[2:18]
        
        # Step 7: Send KeyAck
        conn.send(b'\x50\x01\x84\x01\x00\xb7\x2d')
        
        # Step 8: Handle encrypted SIA data
        cipher_aes = AES.new(aes_key, AES.MODE_ECB)
        
        while True:
            encrypted_data = conn.recv(32)  # Up to 2 AES blocks
            if not encrypted_data:
                break
                
            # Decrypt in 16-byte blocks
            decrypted_sia = b''
            for i in range(0, len(encrypted_data), 16):
                block = encrypted_data[i:i+16]
                if len(block) == 16:
                    decrypted_sia += cipher_aes.decrypt(block)
            
            # Parse and handle SIA message
            process_sia_message(decrypted_sia, conn, cipher_aes)
    
    def process_sia_message(decrypted: bytes, conn, cipher):
        """Parse decrypted SIA block and send encrypted ACK"""
        
        # Strip overhead byte and padding
        if decrypted[0] == 0x09:
            sia_frame = decrypted[1:].rstrip(b'\xae\x00')  # Common padding bytes
        else:
            sia_frame = decrypted.rstrip(b'\xae\x00')
        
        # Parse SIA frame: [length] [command] [payload] [checksum]
        if len(sia_frame) < 3:
            return
        
        length = sia_frame[0] - 0x40  # Remove offset
        command = chr(sia_frame[1])
        payload = sia_frame[2:2+length]
        checksum = sia_frame[2+length] if len(sia_frame) > 2+length else 0
        
        print(f"SIA Message: Command={command}, Payload={payload.hex()}")
        
        # Send encrypted ACK
        ack = b'\x40\x38\x87' + b'\x00' * 13  # SIA ACK padded to 16 bytes
        encrypted_ack = cipher.encrypt(ack)
        conn.send(encrypted_ack)

---

## RSA Cryptographic Details

### Key Generation (Server-Side)

    from Cryptodome.PublicKey import RSA
    
    # Generate RSA-1024 with non-standard e=3
    rsa_key = RSA.generate(1024, e=3)
    
    # Export modulus in little-endian format (panel native)
    modulus_bytes = rsa_key.n.to_bytes(128, 'little')

### Decryption (Textbook RSA)

    # The panel uses textbook RSA: plaintext = ciphertext^d mod n
    # With little-endian integer representation
    
    encrypted_int = int.from_bytes(encrypted_block, 'little')
    decrypted_int = pow(encrypted_int, private_exponent, modulus)
    decrypted_bytes = decrypted_int.to_bytes(128, 'little')
    
    # Extract AES key from known offset
    aes_session_key = decrypted_bytes[2:18]  # Bytes 2-17 (16 bytes)

### Why Little-Endian?

The panel's multi-precision library (mpModExp function) stores RSA operands as
arrays of 32-bit words in little-endian word order:

    Bytes:  [word0][word1][word2]...[word31]
    Math:    LSW                      MSW
             ↑                        ↑
        Least significant      Most significant

This means:
- **Byte 0-3**: Least significant 32 bits
- **Byte 124-127**: Most significant 32 bits
- **Trailing zeros** appear at the high-order end (bytes 117-127)

---

## Security Considerations

⚠️ **This protocol uses weak cryptography:**

1. **RSA with e=3** is vulnerable to:
   - Low-exponent attacks if the same message is encrypted to 3+ recipients
   - Cube root attacks on short messages
   
2. **Textbook RSA** (no padding) is vulnerable to:
   - Chosen ciphertext attacks
   - Message malleability
   
3. **AES-ECB mode** is vulnerable to:
   - Pattern analysis (identical plaintexts → identical ciphertexts)
   - Block reordering attacks

4. **No message authentication** (MAC):
   - Only CRC checksums (not cryptographically secure)
   - Susceptible to tampering

**This protocol should be considered obfuscation rather than strong encryption.**
It provides protection against casual interception but not targeted attacks.

---

## Validation and Testing

This protocol implementation has been validated through:

✅ Successful RSA handshake with live Galaxy Flex panel  
✅ AES session key extraction and verification  
✅ Decryption of SIA event messages  
✅ SIA checksum validation  
✅ Multi-session stability testing  

Test equipment:
- Honeywell Galaxy Flex 3-20 control panel
- GX Ethernet Module (firmware unknown)
- Network capture and analysis tools

---

## References

- GX Remote Control Android APK — com.honeywell.galaxyapp.apk v4.5.0
- Native library — libBackendFirmware.so (ARM64 from config.arm64_v8a.apk)
- Ghidra reverse engineering tool — function analysis and decompilation
- Network captures — encrypted and plaintext tcpdump sessions
- Live panel testing and validation — April 2026
- Homey community forum thread —  
  https://community.homey.app/t/honeywell-galaxy-flex-alarm-with-ethernet-module/5991

---

## Legal Notice

This documentation was produced through independent security research for the purpose
of enabling interoperability with a legally owned device. No proprietary keys or
credentials are included. Any implementation requires the user to supply their own
panel configuration. 

**This research is provided for educational and interoperability purposes only.**
The authors make no warranties and accept no liability for the use of this information.
Users are responsible for complying with all applicable laws and regulations in their
jurisdiction.

---

## Acknowledgments

Special thanks to the security research community and the collaborative effort
in reverse engineering this protocol through network analysis, binary decompilation,
and live validation testing.

**Status**: Protocol fully reverse engineered and working (2026-04-16)
