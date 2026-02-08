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

# --- SIA Event Code Translations ---
# A human-readable description for each 2-character SIA Event Code.
# This can be used to generate descriptive notifications for SIA Level 2 events.
# Source: Honeywell Galaxy Flex Installer Manual & community contributions.
EVENT_CODE_DESCRIPTIONS = {
    # A - Alarm Cause / AC Power
    'AC': "Alarm Cause Reported",
    'AR': "AC Power Restored",
    'AT': "AC Power Trouble / Failure",

    # B - Burglary
    'BA': "Burglary Alarm",
    'BC': "Burglary Cancelled",
    'BF': "Intruder High",
    'BJ': "Burglary Trouble (Resistance)",
    'BL': "Intruder Low",
    'BR': "Burglary Alarm Restored",
    'BT': "Burglary Trouble",
    'BV': "Burglary Verified",
    'BX': "Burglary Test",

    # C - Closing
    'CA': "Closing Report (Automatic)",
    'CE': "Closing Extend",
    'CG': "Area Closed",
    'CI': "Fail to Set", # Corrected from "Cl"
    'CJ': "Late to Set",
    'CL': "Closing Report (User Armed)",
    'CP': "Auto Closing",
    'CR': "Recent Close",
    'CT': "Late to Open",

    # D - Access
    'DD': "Access Denied",
    'DF': "Door Forced",
    'DG': "Access Granted",
    'DK': "Access Lockout",
    'DT': "Door Propped",

    # E - System Trouble
    'ER': "Module Removed",
    'ET': "RF NVM Fail",

    # F - Fire
    'FA': "Fire Alarm",
    'FB': "Fire Bypass",
    'FJ': "Fire Trouble (Resistance)",
    'FR': "Fire Alarm Restored",
    'FT': "Fire Trouble",
    'FU': "Fire Unbypass",
    'FX': "Fire Test",

    # G - Gas (Custom SIA)
    'GA': "Gas Alarm",
    'GB': "Gas Bypass",
    'GJ': "Gas Trouble Restored",
    'GR': "Gas Alarm Restore",
    'GT': "Gas Trouble",
    'GU': "Gas Unbypass",

    # H - Holdup
    'HA': "Holdup / Duress Alarm",
    'HB': "Holdup Bypass",
    'HJ': "Holdup Trouble (Resistance)",
    'HR': "Holdup Alarm Restored",
    'HT': "Holdup Trouble",
    'HU': "Holdup Unbypass",

    # I - Peripheral Fault
    'IA': "Equipment Failure",
    'IR': "Equipment Failure Restored",

    # J - Wrong Code / Time Changed
    'JA': "Code Tamper",
    'JL': "Log Almost Full",
    'JR': "Timer Event",
    'JT': "Time/Date Changed",

    # K - Heat (Custom SIA)
    'KA': "Heat Alarm",
    'KB': "Heat Bypass",
    'KJ': "Heat Trouble (Resistance)",
    'KR': "Heat Alarm Restore",
    'KT': "Heat Trouble",
    'KU': "Heat Unbypass",

    # L - Phone / Program
    'LB': "Program Begin",
    'LR': "Line Restore",
    'LT': "Line Trouble",
    'LX': "Local Program End",

    # M - Medical (Custom SIA)
    'MA': "Medical Alarm",
    'MB': "Medical Bypass",
    'MJ': "Medical Trouble Restored",
    'MR': "Medical Alarm Restore",
    'MT': "Medical Trouble",
    'MU': "Medical Unbypass",

    # O - Opening
    'OA': "Opening Report (Automatic)",
    'OG': "Area Opened",
    'OK': "Early Open",
    'OP': "Opening Report (User Disarmed)",
    'OR': "Disarm from Alarm",

    # P - Panic
    'PA': "Panic Alarm",
    'PB': "Panic Bypass",
    'PJ': "Panic Trouble (Resistance)",
    'PR': "Panic Alarm Restored",
    'PT': "Panic Trouble",
    'PU': "Panic Unbypass",

    # Q - Assist (Custom SIA)
    'QA': "Assist Alarm",
    'QB': "Assist Bypass",
    'QJ': "Assist Trouble Restored",
    'QR': "Assist Alarm Restore",
    'QT': "Assist Trouble",
    'QU': "Assist Unbypass",

    # R - Remote, Log, Test
    'RB': "Remote Program Begin",
    'RC': "Relay Closed",
    'RD': "Program Denied",
    'RO': "Relay Open",
    'RP': "Automatic Test",

    'RR': "Power Up",
    'RS': "Program Success",
    'RX': "Manual Test",

    # S - Sprinkler (Custom SIA)
    'SA': "Sprinkler Alarm",
    'SB': "Sprinkler Bypass",
    'SJ': "Sprinkler Trouble (Resistance)",
    'SR': "Sprinkler Alarm Restore",
    'ST': "Sprinkler Trouble",
    'SU': "Sprinkler Unbypass",

    # T - Tamper, Test
    'TA': "Tamper Alarm",
    'TE': "Test End",
    'TR': "Tamper Restore",
    'TS': "Test Start",

    # V
    'VY': "Print OC OL", # Note: Unclear code from list

    # W - Water (Custom SIA)
    'WA': "Water Alarm",
    'WB': "Water Bypass",
    'WJ': "Water Trouble (Resistance)",
    'WR': "Water Alarm Restore",
    'WT': "Water Trouble",
    'WU': "Water Unbypass",

    # X - RF (Radio Frequency)
    'XQ': "RF Jam",
    'XT': "RF Battery Low",
    'XH': "RF Jam Restore",
    'XR': "RF Battery Low Restore",

    # Y - Comms / System Status
    'YC': "Comms Fail",
    'YF': "Panel Cold Start",
    'YK': "Comm Restoral",
    'YL': "+AC+ Battery Fail",
    'YP': "PSU Fail",
    'YR': "System Battery Restored",
    'YT': "System Battery Trouble",

    # Z - Freezer (Custom SIA)
    'ZA': "Freezer Alarm",
    'ZB': "Freezer Bypass",
    'ZJ': "Freezer Trouble (Resistance)",
    'ZR': "Freezer Alarm Restore",
    'ZT': "Freezer Trouble",
    'ZU': "Freezer Unbypass",
}
