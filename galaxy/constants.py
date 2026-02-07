"""
Constants related to the Galaxy SIA Protocol.

This file defines the known Command Bytes (the second byte of every message block)
and their human-readable names.
"""

# Defines the meaning of the second byte (Command Byte) in each message block.
# Source: Reverse-engineered and cross-referenced with public SIA documentation.
COMMANDS = {
    # --- Client to Server Commands (Observed) ---
    0x23: 'ACCOUNT_ID',
    0x4E: 'NEW_EVENT',
    0x41: 'ASCII',
    0x30: 'END_OF_DATA',

    # --- Server to Client Commands (Implemented) ---
    0x38: 'ACKNOWLEDGE',
    0x39: 'REJECT',

    # --- Other Known SIA Command Codes (Not yet observed/implemented) ---
    # Control Commands
    0x31: 'WAIT',
    0x32: 'ABORT',
    0x36: 'ACK_AND_STANDBY',
    0x37: 'ACK_AND_DISCONNECT',
    0x08: 'ALT_ACKNOWLEDGE',
    0x09: 'ALT_REJECT',
    
    # Info Blocks
    0x43: 'CONTROL',
    0x45: 'ENVIRONMENTAL',
    0x4F: 'OLD_EVENT',
    0x50: 'PROGRAM',
    
    # Special Blocks
    0x40: 'CONFIGURATION',
    0x3F: 'REMOTE_LOGIN',
    0x26: 'ORIGIN_ID',
    0x58: 'EXTENDED',
    0x4C: 'LISTEN_IN',
    0x56: 'VCHN_REQUEST',
    0x76: 'VCHN_FRAME',
    0x49: 'VIDEO',
}

# Create a reverse mapping for easily sending commands by name.
# This allows us to use 'ACKNOWLEDGE' in the code instead of the raw hex value.
COMMAND_BYTES = {name: byte for byte, name in COMMANDS.items()}
