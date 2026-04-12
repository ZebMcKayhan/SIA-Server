# Honeywell Galaxy Flex — Encrypted ARC Protocol

## Research Notes — Reverse Engineered from Network Captures and APK Analysis

This document describes the encrypted variant of the proprietary TCP-based protocol
used by the Honeywell Galaxy Flex ethernet module when communicating with an ARC
(Alarm Receiving Centre) server. It is a companion to the main SIA protocol
documentation and covers only the encrypted session establishment and data transfer.

---

## Background

The Galaxy Flex ethernet module supports both plaintext and encrypted ARC
communication. Encryption is configured independently for notifications and remote
access in the panel settings. When encryption is enabled, the panel initiates a
proprietary key exchange before sending any SIA data.

This protocol was reverse engineered from:
- Captured network traffic (tcpdump) of both plaintext and encrypted sessions
- Decompiled Java source from the GX Remote Control Android APK (jadx)
- Native library strings analysis (`libBackendFirmware.so`)

---

## Encryption Architecture

Despite the presence of TLS-related code in the Android app (used for SIA Level 4
app-to-panel connections), the ARC notification path (SIA Level 3, panel-to-server)
uses a **custom proprietary encryption scheme**:

- **Key exchange**: RSA-1024
- **Session encryption**: AES-128
- **Integrity**: CRC-16/XMODEM on handshake frames

This was confirmed by function names extracted from `libBackendFirmware.so`:
```
CDataEncryption::GeneratePublicKey
CDataEncryption::GenRsaPrime
CDataEncryption::DecodePrivateKeyMessageBlock
MTcomms::GenerateRSAKeys
MTcomms::SendPPKComNoKey
MTcomms::SendPPKComWithKey
MTcomms::WaitKey
MTcomms::SendKey
MTprot::Encrypt / AESEncryptData
MTprot::Decrypt / AESDecryptData
MTprot::RxCipherPacket
AESsubBytes, AESshiftRows, AESmixColumns (custom AES implementation)
```

---

## Frame Format

All handshake frames (pre-encryption) follow a unified structure:

```
[Header bytes] [Payload] [CRC-16/XMODEM — 2 bytes, big-endian]
```

The CRC is calculated over all bytes **except** the CRC itself.

**CRC-16/XMODEM parameters:**
```
Width:  16
Poly:   0x1021
Init:   0x0000
RefIn:  False
RefOut: False
XorOut: 0x0000
```

Python implementation:
```python
import crcmod
crc16_xmodem = crcmod.predefined.mkCrcFun('xmodem')

def calc_crc(data: bytes) -> bytes:
    return crc16_xmodem(data).to_bytes(2, 'big')
```

---

## Handshake Sequence

The complete encrypted session establishment before any SIA data is exchanged:

```
Panel  →  Server:    5 bytes   StartEnc
Server →  Panel:   135 bytes   ServerKey (RSA-1024 public key)
Panel  →  Server:  132 bytes   PanelKey  (AES session key, RSA encrypted)
Server →  Panel:     7 bytes   KeyAck
--- Handshake complete, all subsequent data is AES encrypted ---
Panel  →  Server:   16 bytes   Encrypted Account block
Server →  Panel:    16 bytes   Encrypted ACK
Panel  →  Server:   32 bytes   Encrypted Event block
Server →  Panel:    16 bytes   Encrypted ACK
Panel  →  Server:   32 bytes   Encrypted ASCII block  (optional)
Server →  Panel:    16 bytes   Encrypted ACK
Panel  →  Server:   16 bytes   Encrypted EndOfData
Server →  Panel:    16 bytes   Encrypted AckAndDisconnect
```

---

## Frame Definitions

### StartEnc — Panel → Server (5 bytes)
```
05 01 81 | 59 68
```
- `05 01 81` — fixed header (purpose of individual bytes unknown)
- `59 68` — CRC-16/XMODEM of `05 01 81`

This is a **static, fixed sequence** — identical across all panels and sessions.
It signals that the panel wishes to use encrypted communication.

### ServerKey — Server → Panel (135 bytes)
```
08 01 01 01 00 | [128 bytes RSA-1024 public key] | [2 bytes CRC]
```
- `08 01 01 01 00` — fixed 5-byte header (purpose unknown, copy as-is)
- 128 bytes — RSA-1024 public key in DER format
- 2 bytes — CRC-16/XMODEM of all preceding 133 bytes

The server generates a fresh RSA-1024 keypair per session and sends its public key.

### PanelKey — Panel → Server (132 bytes)
```
88 01 | [128 bytes RSA-encrypted AES key] | [2 bytes CRC]
```
- `88 01` — 2-byte header
- 128 bytes — RSA-1024 encrypted AES-128 session key
  - The AES key itself is 16 bytes, zero-padded to 128 bytes before RSA encryption
- `97 45` — CRC-16/XMODEM (observed value, will vary with content)

The panel encrypts the AES session key using the server's RSA public key and sends
it back. The server decrypts this with its RSA private key to recover the AES key.

### KeyAck — Server → Panel (7 bytes)
```
50 01 84 01 00 | b7 2d
```
- `50 01 84 01 00` — fixed 5-byte header (purpose unknown, copy as-is)
- `b7 2d` — CRC-16/XMODEM of `50 01 84 01 00`

This is a **static, fixed sequence** sent after successfully receiving the PanelKey.

---

## Encrypted Data Phase

After the handshake all SIA blocks are encrypted with AES-128. Each plaintext SIA
block is zero-padded to the next 16-byte boundary before encryption.

The encrypted block sizes map directly to the unencrypted equivalents:

| SIA Block    | Plaintext size | Encrypted size |
|:-------------|:--------------|:--------------|
| Account ID   | ~9 bytes       | 16 bytes (1 AES block) |
| New Event    | ~19 bytes      | 32 bytes (2 AES blocks) |
| ASCII        | ~20 bytes      | 32 bytes (2 AES blocks) |
| End of Data  | 3 bytes        | 16 bytes (1 AES block) |
| ACK          | 3 bytes        | 16 bytes (1 AES block) |

The ACK block sent by the server is the **same 16 bytes every time** within a
session — it is the AES encryption of the standard SIA ACK (`40 38 87` + padding).
Since AES-ECB produces identical output for identical input and key, this is expected.

The final AckAndDisconnect is different from the regular ACK as it encrypts a
different plaintext (disconnect acknowledgement vs regular ACK).

---

## Implementation Notes

### Detecting Encrypted vs Plaintext

```python
data = conn.recv(5)
if data == bytes([0x05, 0x01, 0x81, 0x59, 0x68]):
    handle_encrypted(conn)
else:
    handle_plaintext(conn, data)
```

### Server Key Exchange

```python
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5, AES
import crcmod

crc16 = crcmod.predefined.mkCrcFun('xmodem')

def calc_crc(data: bytes) -> bytes:
    return crc16(data).to_bytes(2, 'big')

def handle_encrypted(conn):
    # Generate RSA-1024 keypair
    rsa_key = RSA.generate(1024)
    pub_key = rsa_key.publickey().export_key('DER')  # Must be 128 bytes

    # Send ServerKey frame
    header = bytes([0x08, 0x01, 0x01, 0x01, 0x00])
    payload = header + pub_key
    conn.send(payload + calc_crc(payload))

    # Receive PanelKey frame (132 bytes)
    panel_frame = conn.recv(132)
    encrypted_aes_key = panel_frame[2:130]  # Strip 2-byte header and 2-byte CRC

    # Decrypt AES session key
    cipher_rsa = PKCS1_v1_5.new(rsa_key)
    aes_key = cipher_rsa.decrypt(encrypted_aes_key, None)

    # Send KeyAck
    KEY_ACK = bytes([0x50, 0x01, 0x84, 0x01, 0x00, 0xb7, 0x2d])
    conn.send(KEY_ACK)

    # All subsequent blocks are AES-128 encrypted
    cipher_aes = AES.new(aes_key, AES.MODE_ECB)

    while True:
        block = conn.recv(32)
        if not block:
            break
        decrypted = cipher_aes.decrypt(block)
        # Parse decrypted data as normal SIA blocks
        handle_sia_block(decrypted, conn, cipher_aes)
```

---

## Open Questions

1. **RSA key format** — the exact DER encoding expected by the panel is unconfirmed.
   It is possible the panel expects a raw 128-byte modulus rather than full DER.

2. **AES padding** — whether the panel uses zero-padding or PKCS#7 for the AES key
   before RSA encryption is unconfirmed.

3. **Header byte meanings** — the purpose of individual bytes in the 5-byte headers
   (`08 01 01 01 00` and `50 01 84 01 00`) is unknown. They are currently hardcoded
   from the captured session.

4. **AES mode** — ECB is assumed based on the repeated identical ACK blocks.
   CBC or CTR with a zero IV would also produce this behaviour on the first block.

5. **Experiment pending** — the full handshake has not yet been tested live.
   The above implementation is based purely on traffic analysis and should be
   validated against a real panel.

---

## References

- GX Remote Control Android APK — `com.honeywell.galaxyapp.apk` v4.5.0
- Native library — `libBackendFirmware.so` (from `config.arm64_v8a.apk`)
- Decompiled Java sources — `GalaxyCommunicationAsyncTask.java`,
  `GalaxyConnectionActivity.java`, `GalaxyPanelFunctions.java`
- Network captures — encrypted and plaintext tcpdump sessions
- Homey community forum thread —
  https://community.homey.app/t/honeywell-galaxy-flex-alarm-with-ethernet-module/5991

---

## Legal Notice

This documentation was produced through independent security research for the purpose
of enabling interoperability with a legally owned device. No proprietary keys or
credentials are included. Any implementation requires the user to supply their own
panel configuration. The authors make no warranties and accept no liability for
the use of this information.
