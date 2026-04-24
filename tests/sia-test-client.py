#!/usr/bin/env python3
"""
SIA Server Test Client
Sends test SIA frames to a local sia-server instance and displays the responses.
Used for testing connection policies, reject policies and state machine enforcement.

Usage: python3 sia-test-client.py
"""
import socket
import time

# --- Configuration ---
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 10000
TIMEOUT = 3.0

# --- SIA Frame Builder ---
def build_sia_frame(command_byte: int, payload: bytes = b'') -> bytes:
    """Builds a valid SIA frame with correct length and checksum."""
    length_byte = len(payload) + 0x40
    message_part = bytes([length_byte, command_byte]) + payload
    checksum = 0xFF
    for byte in message_part:
        checksum ^= byte
    return message_part + bytes([checksum])

# --- Known frames ---
ACCOUNT_ID_VALID   = build_sia_frame(0x23, b'123456')  # Valid account
ACCOUNT_ID_NO      = build_sia_frame(0x23, b'234567')  # Policy: no
ACCOUNT_ID_SECURE  = build_sia_frame(0x23, b'012345')  # Policy: secure
ACCOUNT_ID_UNKNOWN = build_sia_frame(0x23, b'999999')  # Unknown account
ACKNOWLEDGE        = build_sia_frame(0x38)              # ACK command
NEW_EVENT          = build_sia_frame(0x4E, b'ti12:00/id001/RX')  # Event
END_OF_DATA        = build_sia_frame(0x30)              # End of data

def send_and_receive(sock: socket.socket, data: bytes, description: str) -> bytes | None:
    """Sends a frame and waits for a response."""
    print(f"\n  → Sending:  [{description}] {data.hex(' ')}")
    try:
        sock.sendall(data)
        response = sock.recv(1024)
        if response:
            print(f"  ← Received: {response.hex(' ')}")
        else:
            print(f"  ← Received: (connection closed)")
        return response
    except socket.timeout:
        print(f"  ← Received: (timeout - no response)")
        return None
    except ConnectionResetError:
        print(f"  ← Received: (connection reset by server)")
        return None

def run_test(test_name: str, frames: list[tuple[bytes, str]], expected_outcome: str):
    """Runs a single test scenario."""
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"EXPECTED: {expected_outcome}")
    print(f"{'='*70}")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((SERVER_HOST, SERVER_PORT))
        print(f"  Connected to {SERVER_HOST}:{SERVER_PORT}")
        
        for frame, description in frames:
            response = send_and_receive(sock, frame, description)
            if response is None:
                print(f"  → No response or connection closed. Stopping test.")
                break
            time.sleep(0.1)
            
    except ConnectionRefusedError:
        print(f"  ERROR: Could not connect to {SERVER_HOST}:{SERVER_PORT}")
        print(f"  Is sia-server.py running?")
    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        try:
            sock.close()
        except:
            pass
    
    time.sleep(0.5)  # Brief pause between tests

def main():
    print("="*70)
    print("SIA Server Test Client")
    print(f"Target: {SERVER_HOST}:{SERVER_PORT}")
    print("="*70)
    print("\nNote: Set LOG_TO = Screen and LOG_LEVEL = DEBUG in sia-server.conf")
    print("to see the full server-side view of these tests.")

    # --- Test 1: Valid account, normal session ---
    run_test(
        "Valid account - normal plaintext session",
        [
            (ACCOUNT_ID_VALID,  "ACCOUNT_ID (valid account 027978)"),
            (NEW_EVENT,         "NEW_EVENT"),
            (END_OF_DATA,       "END_OF_DATA"),
        ],
        "Should receive ACK for each frame."
    )

    # --- Test 2: State machine - wrong first command ---
    run_test(
        "State machine violation - ACK sent before ACCOUNT_ID",
        [
            (ACKNOWLEDGE, "ACKNOWLEDGE (sent before ACCOUNT_ID)"),
        ],
        "Should be rejected or dropped immediately. No ACK."
    )

    # --- Test 3: State machine - NEW_EVENT before ACCOUNT_ID ---
    run_test(
        "State machine violation - NEW_EVENT sent before ACCOUNT_ID",
        [
            (NEW_EVENT, "NEW_EVENT (sent before ACCOUNT_ID)"),
        ],
        "Should be rejected or dropped immediately. No ACK."
    )

    # --- Test 4: Disabled account ---
    run_test(
        "Disabled account (policy: no)",
        [
            (ACCOUNT_ID_NO, "ACCOUNT_ID (account 027979, policy=no)"),
        ],
        "Should be rejected or dropped after ACCOUNT_ID."
    )

    # --- Test 5: Secure account via plaintext ---
    run_test(
        "Secure account via plaintext (policy: secure)",
        [
            (ACCOUNT_ID_SECURE, "ACCOUNT_ID (account 027977, policy=secure)"),
        ],
        "Should be rejected or dropped. Encrypted connection required."
    )

    # --- Test 6: Unknown account ---
    run_test(
        "Unknown account (falls back to [Default] policy)",
        [
            (ACCOUNT_ID_UNKNOWN, "ACCOUNT_ID (account 999999, unknown)"),
        ],
        "Depends on [Default] ENABLED setting in sia-server.conf."
    )

    # --- Test 7: Invalid/garbage data ---
    run_test(
        "Garbage data (not a valid SIA frame)",
        [
            (b'\x00\x01\x02\x03\x04\x05\x06\x07', "Random garbage bytes"),
        ],
        "Should be rejected or dropped. Checksum will fail."
    )

    # --- Test 8: Replayed END_OF_DATA before ACCOUNT_ID ---
    run_test(
        "State machine violation - END_OF_DATA before ACCOUNT_ID",
        [
            (END_OF_DATA, "END_OF_DATA (sent before ACCOUNT_ID)"),
        ],
        "Should be rejected or dropped immediately."
    )

    print(f"\n{'='*70}")
    print("All tests complete.")
    print("Compare the responses above with the server log for full details.")
    print(f"{'='*70}\n")

if __name__ == '__main__':
    main()
