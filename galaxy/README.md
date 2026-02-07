## Galaxy SIA Protocol Specification

This project interacts with a proprietary, TCP-based SIA protocol variant used by Honeywell Galaxy Flex alarm systems. The protocol was reverse-engineered from captured network traffic.

### High-Level Overview

The protocol is a stateful, sequential exchange over a single TCP connection. An "event" is not a single message, but a sequence of message "blocks". During an alarm state, the panel may send multiple complete event sequences over a single TCP connection.

The flow for a single event sequence is:
1.  Client (Alarm Panel) sends **Block 1 (Account)**.
2.  Server sends an **ACK**.
3.  Client sends **Block 2 (Data)**.
4.  Server sends an **ACK**.
5.  Client sends **Block 3 (ASCII)** (This is optional and may be omitted).
6.  Server sends an **ACK**.
7.  (This repeats for any subsequent events in the same connection).
8.  Client sends a **Close Handshake** message.
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
    -   `CL`: Event Code is "Closing" (2 chars)

-   **Burglary Alarm Event Payload:** `ti11:46/BA1011`
    -   `ti11:46`: Time is 11:46
    -   `BA1011`: Event Code is "Burglary Alarm" (`BA` - 2 chars) in Zone `1011`.

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
