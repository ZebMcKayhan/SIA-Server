# Galaxy SIA Protocol Specification

This document describes the proprietary, TCP-based SIA protocol variant used by Honeywell Galaxy Flex alarm systems, as reverse-engineered from captured network traffic. It serves as the technical documentation for the parsing logic in this module.

## High-Level Overview

The protocol is a stateful, sequential exchange over a single TCP connection. Unlike standard SIA which often uses UDP, this variant uses TCP to ensure message delivery. An "event" is not a single message, but a sequence of message "blocks".

The typical flow for a single event sequence is:
1.  Client (Alarm Panel) establishes a TCP connection to the server.
2.  Client sends **Block 1 (Account)**.
3.  Server sends an **ACK**.
4.  Client sends **Block 2 (Data)**.
5.  Server sends an **ACK**.
6.  Client sends **Block 3 (ASCII)** (This is optional and may be omitted, e.g., in SIA Level 2).
7.  Server sends an **ACK**.
8.  Client sends a **Close Handshake** message.
9.  Server sends a final **ACK**.
10. The connection is closed.

**Important:** During an alarm state, the panel may send multiple complete event sequences (each containing multiple blocks) over a single TCP connection before sending the final Close Handshake. In such case the sequence repeats after step 7 and back to step 2.

## Message Block Formats

Each block is terminated by a single checksum byte.

### Block 1: Account Block

This block identifies the alarm panel.

-   **Format:** `<Prefix>#<AccountID><Checksum>`
-   **Example:** `F#027178\x99`

| Part          | Example    | Description                                                 |
| :------------ | :--------- | :---------------------------------------------------------- |
| **Prefix**    | `F`        | An identifier. Appears to be consistently `F`.              |
| **Delimiter** | `#`        | Separates the prefix from the account ID.                   |
| **AccountID** | `027178`   | The 4 or 6-digit account number of the panel.               |
| **Checksum**  | `\x99`     | A single checksum byte for the preceding data (`F#027178`). |

---

### Block 2: Data Block (N Block)

This block contains the core event data in a semi-structured format.

-   **Format:** `<Prefix><section1>/<section2>/.../<EventCode_and_Zone>`
-   **Logic:** The block consists of a 2-character prefix followed by sections delimited by `/`. All sections *except the last one* have a 2-character identifier (e.g., `ti`, `id`, `pi`). The final section is always the event code, which may have a zone number appended directly to it.

**Examples:**
-   `VNti11:45/id001/pi010/CL\xf5` (User Event)
-   `NNti11:46/BA1011\xf7` (Zone Alarm)
-   `QNti12:16/va1440/RP\xd7` (Auto Test)
-   `JNti11:46/BV\xe5` (Simple Event)

**Known Prefixes:**

| Prefix | Type (Guessed)       | Observed In                                |
| :----- | :------------------- | :----------------------------------------- |
| `VN`   | User/Verified Event  | Arm, Disarm, Reset                         |
| `PN`   | Panel Event          | Manual Engineering Test                    |
| `QN`   | Queued/Periodic Event | Automatic Test                             |
| `NN`   | New/Notification Alarm | Burglary Alarms                            |
| `JN`   | Just-in/Join Event   | Burglary Verified, "Just Armed" confirmation |

**Known Section Identifiers:**

| ID   | Meaning          | Example     |
| :--- | :--------------- | :---------- |
| `ti` | Time             | `ti11:45`   |
| `id` | User ID          | `id001`     |
| `pi` | Partition/Peripheral | `pi010`     |
| `va` | Value            | `va1440`    |

**Final Section (Event Code & Zone):**

The final section has two forms:
1.  **Event Code Only:** `CL`, `OP`, `BC`, `BV`, `RP`
2.  **Event Code + Zone:** `BA1011` (Event `BA`, Zone `1011`)

---

### Block 3: ASCII Block (A Block)

This block provides a human-readable description of the event. It appears to have at least two different variants but in common the block consists of a 1 character prefix, the letter A followed by text.

**Format:** `<prefix>A<Ascii text>`

**Variant 1: User Events (Variable Length)**
-   **Prefix:** `Q`
-   **Structure:** `QA <Action Text> <Username>`
-   **Example:** `QA PÅSLAG    Kalle*`

**Variant 2: Zone/System Events (Fixed Length)**
-   **Prefix:** `e`, `[`, `J`
-   **Structure:** `<Prefix>A<LogEvent(9)><State(1)><Site(8)><Descriptor(16)>`
-   **Example (`[`):** `[A+INBROTT        IR Sovrum Ö\x34`
    -   **Prefix:** `[`
    -   **A:** `A`
    -   **LogEvent:** `+INBROTT ` (9 chars)
    -   **State:** ` ` (space)
    -   **Site:** `        ` (8 spaces - unused)
    -   **Descriptor:** `IR Sovrum Ö` (16 chars, padded)

The meaning of the prefix is not known.

---


### Close Handshake Block

This block is sent by the client to signal the end of all event transmissions for the current connection.

-   **Format:** `\x40\x30<Checksum>`
-   **Example:** `\x40\x30\x8f`

---

## Server Acknowledgments (ACK/NACK)

The server must respond to **every block** received from the panel, **including the final Close Handshake**, with a 3-byte acknowledgment. This confirms receipt of each message at the application level before the TCP connection is eventually closed.

-   **Format:** `\x40<Status><Checksum>`

| Response | Bytes         | Meaning                               |
| :------- | :------------ | :------------------------------------ |
| **ACK**  | `\x40\x38\x87`| Message received successfully.        |
| **NACK** | `\x40\x39\x86`| Message received with an error (e.g., bad checksum). |

---

## Implementation Details

### Checksums

The panel uses at least two different checksum algorithms:
1.  **For short 2-byte messages (like ACKs):** The checksum is a single byte calculated as `(0xFF - sum_of_previous_bytes) & 0xFF`.
2.  **For longer data blocks:** The algorithm is more complex and has not been fully reverse-engineered. It is not necessary to validate these checksums to operate the server, as TCP provides transport-level integrity.

### Character Encoding

The panel does **not** use standard UTF-8 or ISO-8859-1. It uses a proprietary mapping where common Swedish characters (Å, Ä, Ö, etc.) are mapped into the C1 Controls and Latin-1 Supplement range (`0x80` - `0x9F`). The parser must manually replace these bytes with their correct UTF-8 equivalents. Refer to `UNKNOWN_CHAR_MAP` in `config.py` for the known mappings.
