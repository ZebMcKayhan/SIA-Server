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
| `0x23` | `#`   | `ACCOUNT_ID`      | Client | Identifies the alarm panel account.                     |
| `0x4E` | `N`   | `NEW_EVENT`       | Client | Contains the core event data (time, codes, zones, etc.).|
| `0x4F` | `O`   | `OLD_EVENT`       | Client | Same as NEW_EVENT but for previously confirmed events.  |
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
`[Section1]/[Section2]/.../[EventCodeSection]`

-   **Modifier Sections:** Sections starting with two **lowercase** letters are modifier 
    codes that describe the event (time, user, area etc.).

-   **Event Code Section:** The section starting with two **uppercase** letters is the 
    Event Code, which may be followed immediately by a Zone Number.

**Known Section Identifiers:**

| Identifier | Description              | Example Payload Section |
| :--------- | :----------------------- | :---------------------- |
| `ti`       | **Time**                 | `ti11:45`               |
| `ri`       | **Group/Area ID**        | `ri01`                  |
| `id`       | **User ID**              | `id001`                 |
| `pi`       | **Peripheral ID**        | `pi010`                 |
| `va`       | **Value** (for tests)    | `va1440`                |

**Event Code Section:**

The structure of the Event Code section, which is always observed as the last section, is always a **two-character uppercase Event Code**, which may be followed immediately by a 3-4 digit Zone Number.

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
    -   `pi010`: Peripheral ID is 010
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

The panel uses the **IBM Code Page 437 (CP437)** character encoding for text in the ASCII block. This is the original IBM PC character set, which includes support for accented characters used in many European languages.

Python's built-in `cp437` codec handles the vast majority of characters correctly. However, the panel deviates from standard CP437 for a small number of characters, most notably the Nordic letters Ø and ø:

| Byte | Standard CP437 | Panel displays |
| :--- | :------------- | :------------- |
| `0xe9` | Θ (Greek Theta) | Ø |
| `0xed` | φ (Greek Phi) | ø |

These overrides are defined in `galaxy/constants.py` in the `UNKNOWN_CHAR_MAP` dictionary. If you encounter incorrectly decoded characters, identify the byte value from the debug log and add an entry to this map.

The panel's character set appears to be related to **IBM Code Page 865 (Nordic)**, which is a variant of CP437 designed for Scandinavian languages. The exact variant may depend on the country/language setting selected during initial panel setup.

### IP Check Protocol (Heartbeat)

In addition to the main SIA event reporting, the Galaxy panel has an optional, proprietary "IP Check" feature designed for high-frequency path viability testing. This feature operates on a separate, user-configurable TCP port (e.g., 10001).

Our analysis shows this is a proprietary binary protocol, completely distinct from the main SIA event protocol. Its purpose is for the panel to "ping" the server to ensure a connection is possible.

#### The "Ping" Packet (Panel to Server)

When an IP Check is performed, the panel sends a single, fixed-length **26-byte** TCP packet. This packet has a well-defined structure, reverse-engineered from captured network traffic.

**Structure of the 26-byte IP Check Packet:**

| Byte Index(es) | Length  | Example Hex              | Description |
| :------------- | :------ | :------------------------| :---------- |
| **0**          | 1 byte  | `00`                     | **Header:** Always `0x00`. Identifies this as an IP Check ping. |
| **1-8**        | 8 bytes | `30 30 30 32 37 39 37 38` | **Account Number:** The panel's account number, ASCII encoded and zero-padded to 8 characters. |
| **9-14**       | 6 bytes | `11 0c 00 fd 09 00`       | **Static ID Block:** Never changes across any capture. Likely a hardware or firmware identifier. |
| **15-18**      | 4 bytes | `e8 80 f1 69`             | **Timestamp:** A 32-bit little-endian Unix timestamp (seconds since 1970-01-01 00:00:00). Reflects the panel's configured local time, which may differ from the host system's timezone. |
| **19**         | 1 byte  | `3c`                      | **Unknown:** Always observed as `0x3c` (=60). Purpose unknown. Possibly a separator, clock resolution indicator, or part of an extended field. |
| **20-23**      | 4 bytes | `78 00 00 00`             | **IP Check Interval:** A 32-bit little-endian value representing the configured IP Check interval in seconds. Maximum value is 359,940 seconds (99h 59min). |
| **24-25**      | 2 bytes | *(dynamic)*               | **Unknown:** Changes with each ping. Not a standard CRC (exhaustive brute-force search found no matching algorithm). Likely related to the timestamp but the exact algorithm is unknown. |

**Notes on the timestamp (bytes 15-18):**
- The panel does not appear to have an explicit timezone setting in its user interface.
- The stored timestamp may reflect the panel's RTC time as configured, which may not be synchronized to UTC or the local timezone.
- The country/region defaults selected during initial panel setup may influence this behaviour.
- Relative differences between consecutive pings are always exact (proven by matching to the configured interval to the second), confirming the seconds-based counter interpretation.

#### The "Pong" Response (Server to Panel)

I have not been able to capture this as I don't have an IP Check capable Honeywell server. Using the same port as for SIA messages gives a standard SIA **REJECT** reply and the panel seems ok with this and does not give an IP Check error. It could be that any data response is considered a success. The panel closes the connection after 15 seconds which could indicate that this was not the response it was expecting.

I have not found a response that makes the panel close the connection earlier than 15s, so it would be a bad idea to use the same port as the SIA Event Server as it would block connections for real alarms. Instead, the IP Check Service runs on a separate, dedicated port. Currently it echoes back the same data as it received and the panel seems content.

