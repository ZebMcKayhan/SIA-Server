
"""
Constants related to the Galaxy SIA Protocol.
"""

# Defines the meaning of the second byte (Command Byte) in each message block.
COMMANDS = {
    # Client to Server
    0x23: 'ACCOUNT_ID',
    0x4E: 'NEW_EVENT',
    0x41: 'ASCII',
    0x30: 'END_OF_DATA',
    
    # Server to Client
    0x38: 'ACKNOWLEDGE',
    0x39: 'REJECT',
    
    # Other known but unused commands
    0x31: 'WAIT',
    0x32: 'ABORT',
    0x37: 'ACK_AND_DISCONNECT',
}

# Create a reverse mapping for easily sending commands by name
COMMAND_BYTES = {name: byte for byte, name in COMMANDS.items()}
