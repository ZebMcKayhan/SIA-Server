# In galaxy/constants.py or top of parser.py

COMMANDS = {
    # Client to Server
    0x23: 'ACCOUNT_ID',
    0x4E: 'NEW_EVENT',
    0x41: 'ASCII',
    0x30: 'END_OF_DATA',
    # Server to Client
    0x38: 'ACKNOWLEDGE',
    0x39: 'REJECT',
}

# Create a reverse mapping for sending commands
COMMAND_BYTES = {name: byte for byte, name in COMMANDS.items()}
