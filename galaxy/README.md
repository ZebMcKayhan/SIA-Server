## Galaxy SIA Protocol Specification

This project interacts with a proprietary, TCP-based SIA protocol variant used by Honeywell Galaxy Flex alarm systems. The protocol was reverse-engineered from captured network traffic.

### High-Level Overview

The protocol is a stateful, sequential exchange over a single TCP connection. An "event" is not a single message, but a sequence of message "blocks". During an alarm state, the panel may send multiple complete event sequences over a single TCP connection.

The flow for a single event sequence is:
1.  Client (Alarm Panel) sends **Block 1 (ACCOUNT_ID)**.
2.  Server sends an **ACK**.
3.  Client sends **Block 2 (NEW_EVENT)**.
4.  Server sends an **ACK**.
5.  Client sends **Block 3 (ASCII)** (This is optional and may be omitted).
6.  Server sends an **ACK**.
7.  (This repeats for any subsequent events in the same connection).
8.  Client sends a **END_OF_DATA** message.
9.  Server sends a final **ACK**.
10. The connection is closed.

### Message Block Framing

Every message block, whether from the client or server, follows a unified structure:

`<Length Byte><Command Byte><Payload><Checksum Byte>`

-   **Length Byte:** A single byte representing the length of the `<Payload>` with an offset of +64 (`0x40`).
    -   *Formula:* `Length Byte = len(Payload) + 0x40`

-   **Command Byte:** A single byte that defines the purpose of the block.

-   **Payload:** The data content of the block. Its length can be from 0 to 191 bytes.

-   **Checksum Byte:** A single byte used for integrity checking.
    -   *Algorithm:* The checksum is a simple XOR calculation starting with `0xFF`.
    -   *Formula:* `Checksum = 0xFF ^ (Length Byte + 0x40) ^ Command Byte ^ (all bytes in Payload)`

### Known Command Bytes

The `Command Byte` (the second byte of every block) determines the message's meaning.

| Hex    | ASCII | Command Name      | Source | Description                                             |
| :----- | :---- | :---------------- | :----- | :------------------------------------------------------ |
| `0x23` | `#`   | `ACCOUNT_ID`      | Client | Identifies the alarm panel account.                       |
| `0x4E` | `N`   | `NEW_EVENT`       | Client | Contains the core event data (time, codes, zones, etc.).|
| `0x41` | `A`   | `ASCII`           | Client | Contains a human-readable description of the event.     |
| `0x30` | `0`   | `END_OF_DATA`     | Client | Signals the end of all transmissions for the connection.|
| `0x38` | `8`   | `ACKNOWLEDGE`     | Server | Sent by the server to confirm a block was received OK.  |
| `0x39` | `9`   | `REJECT`          | Server | Sent by the server to indicate a block was invalid.     |

### Payload Structures

#### ACCOUNT_ID (`#`) Payload
-   The payload is simply the account number.
-   *Example Payload:* `b'012345'`

#### NEW_EVENT (`N`) Payload

This is the most information-rich block, containing the core details of the alarm event. The payload is a string composed of one or more sections delimited by a forward slash (`/`).

**General Structure:**
`[Section1]/[Section2]/.../[FinalSection]`

-   **Identifier Sections:** Every section *before the last one* is prefixed with a 2-character identifier that defines its content.

-   **Final Section:** The *very last section* of the string is always the **Event Code**, and it does not have an identifier. It may also have a Zone Number appended directly to it.

**Known Section Identifiers:**

| Identifier | Description          | Example Payload Section |
| :--------- | :------------------- | :---------------------- |
| `ti`       | **Time**             | `ti11:45`               |
| `id`       | **User ID**          | `id001`                 |
| `pi`       | **Partition ID**     | `pi010`                 |
| `va`       | **Value** (for tests)| `va1440`                |

**Final Section (Event Code & Zone):**

The structure of the last section is always a **two-character uppercase Event Code**, which may be followed immediately by a 3-4 digit Zone Number.

1.  **Event Code only:**
    -   *Format:* `[EventCode(2)]`
    -   *Example:* `CL` (Closing/Arm)

2.  **Event Code + Zone Number:**
    -   *Format:* `[EventCode(2)][ZoneNumber]`
    -   *Example:* `BA1011` (Burglary Alarm in Zone 1011)

**Full Payload Examples:**

-   **User Arm Event Payload:** `ti11:45/id001/pi010/CL`
    -   `ti11:45`: Time is 11:45
    -   `id001`: User ID is 001
    -   `pi010`: Partition is 010
    -   `CL`: Event Code is "Closing"

-   **Burglary Alarm Event Payload:** `ti11:46/BA1011`
    -   `ti11:46`: Time is 11:46
    -   `BA1011`: Event Code is "Burglary Alarm" in Zone `1011`.

#### ASCII (`A`) Payload

This block's payload contains the full, human-readable description of the event. The examples below show the **clean payload** that is passed to the parser after the Length Byte, Command Byte (`A`), and Checksum Byte have been stripped by the server.

The content of this payload is what is used to generate the final notification message after being decoded.

**Example 1: Zone Alarm Event**
-   **Original Raw Block:** `b'[A+INBROTT      IR Sovrum \x99\x34'`
-   **Clean Payload Sent to Parser:** `b'+INBROTT      IR Sovrum \x99'`
-   **Note:** The trailing `\x99` in this payload is the proprietary byte for the character `Ö` and is part of the zone name ("IR Sovrum Ö"). 
-   **Final Decoded Text:** `"+INBROTT      IR Sovrum Ö"`

**Example 2: System Auto Test**
-   **Original Raw Block:** `b'eA AUTO TEST...Modul\x9a'`
-   **Clean Payload Sent to Parser:** `b' AUTO TEST...Modul'`
-   **Final Decoded Text:** `"AUTO TEST...Modul"`

### Character Encoding

The panel uses a proprietary character set for the ASCII block, where some non-standard characters in the `0x80`-`0x9F` range are used to represent Swedish letters (Å, Ä, Ö, etc.). This server's parser includes a mapping to translate these bytes into correct UTF-8 characters.

### IP Check Protocol (Heartbeat)

In addition to the main SIA event reporting, the Galaxy panel has an optional, proprietary "IP Check" feature designed for high-frequency path viability testing. This feature operates on a separate, user-configurable TCP port (e.g., 10001).

Our analysis shows this is a proprietary binary protocol, completely distinct from the main SIA event protocol. Its purpose is for the panel to "ping" the server to ensure a connection is possible.

#### The "Ping" Packet (Panel to Server)

When an IP Check is performed, the panel sends a single, fixed-length **26-byte** TCP packet. This packet has a well-defined structure.

**Structure of the 26-byte IP Check Packet:**

| Byte Index(es) | Length | Example Hex               | Description                                     |
| :------------- | :----- | :------------------------ | :---------------------------------------------- |
| **0**          | 1 byte | `00`                      | **Header:** A static byte, likely identifying this as an IP Check ping. |
| **1-8**        | 8 bytes| `30 30 30 32 37 39 37 38` | **Account Number:** The panel's account number, ASCII encoded and padded with leading zeros. |
| **9-14**       | 6 bytes| `11 0c 00 fd 09 00`       | **Static ID Block 1:** An unknown but static block of identifier data. |
| **15**         | 1 byte | *(dynamic)*               | **Nonce:** A pseudo-random byte that changes with each ping to ensure message uniqueness. |
| **16**         | 1 byte | *(dynamic)*               | **Sequence Counter:** A byte that increments over time, likely to prevent replay attacks. |
| **17-21**      | 5 bytes| `8d 69 3c 78 00`          | **Static ID Block 2:** Another unknown but static block of data. |
| **22-23**      | 2 bytes| `00 00`                   | **Padding:** Static null bytes for alignment. |
| **24-25**      | 2 bytes| *(dynamic)*               | **Checksum:** A 16-bit value composed of two independent 8-bit checksums (see below). |

#### The "Pong" Response (Server to Panel)

I have not been able to capture this as I dont have a ip-check available Honywell server. Using same port as for SIA messages gives a standard SIA **REJECT** reply and the panel seems ok with this and does not give an ip-check error. It could be that any data response is considered a success. The panel closes the connection after 15 seconds which could indicate that this was not the response it was expecting. 
I have not found a response that makes the panel close the connection earlier than 15s and as so, it would be a bad idea to keep using the same port as the SIA server. Instead, I have created ip_check.py to run as a separate instance on a separate port, so it does not block the connection for real alarms. Currently ip_check.py echoes back the same data as it recieved and the panel seems contempt.

#### Checksum Algorithm (Interleaved 8-bit XOR)

The final two bytes of the IP Check packet are not a standard 16-bit CRC. They are two separate 8-bit checksums calculated over the preceding 24 bytes of the payload.

-   **First Checksum Byte (at index 24):** This is a checksum of all the **even-indexed** bytes of the payload.
    -   **Formula:** `0xFF ^ payload[0] ^ payload[2] ^ payload[4] ^ ... ^ payload[22]`

-   **Second Checksum Byte (at index 25):** This is a checksum of all the **odd-indexed** bytes of the payload.
    -   **Formula:** `0xFF ^ payload[1] ^ payload[3] ^ payload[5] ^ ... ^ payload[23]`

This unconventional, interleaved design explains why a change in an odd-indexed byte (like the Nonce at index 15) only affects the second checksum byte, while a change in an even-indexed byte (like the Counter at index 16) only affects the first checksum byte.
