
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

# event codes from https://github.com/666djb/SIA2MQTT4HA:
#    end_of_data        = 0x30,    #Already used
#    wait               = 0x31,    #Already used
#    abort              = 0x32,    #Already used
#    res_3              = 0x33,
#    res_4              = 0x34,
#    res_5              = 0x35,
#    ack_and_standby    = 0x36,
#    ack_and_disconnect = 0x37,    #Already used
#    acknowledge        = 0x38,    #Already used
#    alt_acknowledge    = 0x08,
#    reject             = 0x39,    #Already used
#    alt_reject         = 0x09,
#    // Info blocks
#    control            = 0x43,
#    environmental      = 0x45,
#    new_event          = 0x4E,    #Already used
#    old_event          = 0x4F,
#    program            = 0x50,
#    // Special blocks
#    configuration      = 0x40,
#    remote_login       = 0x3F,
#    account_id         = 0x23,    #Already used
#    origin_id          = 0x26,
#    ascii              = 0x41,    #Already used
#    extended           = 0x58,
#    listen_in          = 0x4C,
#    vchn_request       = 0x56,
#    vchn_frame         = 0x76,
#    video              = 0x49
