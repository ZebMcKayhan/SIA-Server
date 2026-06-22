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
    'BB': "Burglary Bypass",
    'BC': "Burglary Cancelled",
    'BF': "Intruder High",
    'BH': "Burglary Alarm Restored", # SIA-Library (not galaxy)
    'BJ': "Burglary Trouble Restored",
    'BL': "Intruder Low",
    'BR': "Burglary Alarm Restored",
    'BS': "Burglary Supervisory", # SIA-Library (not galaxy)
    'BT': "Burglary Trouble",
    'BU': "Burglary Unbypass",
    'BV': "Burglary Verified",
    'BX': "Burglary Test",

    # C - Closing
    'CA': "Closing Report (Automatic)",
    'CE': "Closing Extend",
    'CF': "Forced Closing", # SIA-Library (not galaxy)
    'CG': "Area Closed",
    'CI': "Fail to Set", 
    'CJ': "Late to Set",
    'CK': "Early Close", # SIA-Library (not galaxy)
    'CL': "Closing Report (User Armed)",
    'CP': "Auto Closing",
    'CR': "Recent Close",
    'CS': "Closing Switch", # SIA-Library (not galaxy)
    'CT': "Late to Open",
    'CW': "Was Force Armed", # SIA-Library (not galaxy)
    'CZ': "Point Closing", # SIA-Library (not galaxy)

    # D - Access
    'DC': "Access Closed", # SIA-Library (not galaxy)
    'DD': "Access Denied",
    'DF': "Door Forced",
    'DG': "Access Granted",
    'DK': "Access Lockout",
    'DO': "Access Open", # SIA-Library (not galaxy)
    'DR': "Door Restoral", # SIA-Library (not galaxy)
    'DS': "Door Station", # SIA-Library (not galaxy)
    'DT': "Door Propped",
    'DU': "Dealer ID", # SIA-Library (not galaxy)

    # E - Exit / System Trouble
    'EA': "Exit Alarm", # SIA-Library (not galaxy)
    'EE': "Exit Error", # SIA-Library (not galaxy)
    'ER': "Module Removed",
    'ET': "RF NVM Fail",

    # F - Fire
    'FA': "Fire Alarm",
    'FB': "Fire Bypass",
    'FH': "Fire Alarm Restored", # SIA-Library (not galaxy)
    'FI': "Fire Test Begin", # SIA-Library (not galaxy)
    'FJ': "Fire Trouble Restored",
    'FK': "Fire Test End", # SIA-Library (not galaxy)
    'FR': "Fire Alarm Restored",
    'FS': "Fire Supervisory", # SIA-Library (not galaxy)
    'FT': "Fire Trouble",
    'FU': "Fire Unbypass",
    'FX': "Fire Test",
    'FY': "Missing Fire Trouble", # SIA-Library (not galaxy)

    # G - Gas (Custom SIA)
    'GA': "Gas Alarm",
    'GB': "Gas Bypass",
    'GH': "Gas Alarm Restored", # SIA-Library (not galaxy)
    'GJ': "Gas Trouble Restored",
    'GR': "Gas Alarm Restore",
    'GS': "Gas Supervisory", # SIA-Library (not galaxy)
    'GT': "Gas Trouble",
    'GU': "Gas Unbypass",
    'GX': "Gas Test", # SIA-Library (not galaxy)

    # H - Holdup
    'HA': "Holdup / Duress Alarm",
    'HB': "Holdup Bypass",
    'HH': "Holdup Alarm Restored", # SIA-Library (not galaxy)
    'HJ': "Holdup Trouble Restored",
    'HR': "Holdup Alarm Restored",
    'HS': "Holdup Supervisory", # SIA-Library (not galaxy)
    'HT': "Holdup Trouble",
    'HU': "Holdup Unbypass",

    # I - Peripheral Fault
    'IA': "Equipment Failure",
    'IR': "Equipment Failure Restored",

    # J - User/Log
    'JA': "Code Tamper",
    'JD': "Date Changed", # SIA-Library (not galaxy)
    'JH': "Holiday Changed", # SIA-Library (not galaxy)
    'JL': "Log Almost Full",
    'JR': "Timer Event",
    'JT': "Time/Date Changed",
    'JO': "Log Overflow", # SIA-Library (not galaxy)
    'JS': "Schedule Change", # SIA-Library (not galaxy)
    'JV': "User Code Change", # SIA-Library (not galaxy)
    'JX': "User Code Delete", # SIA-Library (not galaxy)

    # K - Heat (Custom SIA)
    'KA': "Heat Alarm",
    'KB': "Heat Bypass",
    'KH': "Heat Alarm Restored", # SIA-Library (not galaxy)
    'KJ': "Heat Trouble Restored", # SIA-Library (not galaxy)
    'KR': "Heat Alarm Restored",
    'KS': "Heat Supervisory", # SIA-Library (not galaxy)
    'KT': "Heat Trouble",
    'KU': "Heat Unbypass",

    # L - Phone / Program
    'LB': "Program Begin",
    'LD': "Local Program Denied", # SIA-Library (not galaxy)
    'LE': "Listen-in Ended", # SIA-Library (not galaxy)
    'LF': "Listen-in Begin", # SIA-Library (not galaxy)
    'LR': "Phone Line Restore",
    'LS': "Local Program Success", # SIA-Library (not galaxy)
    'LT': "Phone Line Trouble",
    'LU': "Local Program Failed", # SIA-Library (not galaxy)
    'LX': "Local Program End", # SIA-Library (not galaxy)

    # M - Medical (Custom SIA)
    'MA': "Medical Alarm",
    'MB': "Medical Bypass",
    'MH': "Medical Alarm Restored", # SIA-Library (not galaxy)
    'MJ': "Medical Trouble Restored",
    'MR': "Medical Alarm Restored",
    'MS': "Medical Supervisory", # SIA-Library (not galaxy)
    'MT': "Medical Trouble",
    'MU': "Medical Unbypass",

    # N - No Activity
    'NA': "No Activity",
    'NF': "Forced Perimeter Arm", # SIA-Library (not galaxy)
    'NL': "Perimeter Armed", # SIA-Library (not galaxy)

    # O - Opening
    'OA': "Opening Report (Automatic)",
    'OC': "Cancel Report", # SIA-Library (not galaxy)
    'OG': "Area Opened",
    'OI': "Fail to Open", # SIA-Library (not galaxy)
    'OJ': "Late Open", # SIA-Library (not galaxy)
    'OK': "Early Open", # SIA-Library (not galaxy)
    'OP': "Opening Report (User Disarmed)",
    'OR': "Disarm from Alarm",
    'OS': "Opening Keyswitch", # SIA-Library (not galaxy)
    'OT': "Late to Close", # SIA-Library (not galaxy)
    'OZ': "Point Opening", # SIA-Library (not galaxy)

    # P - Panic
    'PA': "Panic Alarm",
    'PB': "Panic Bypass",
    'PH': "Panic Alarm Restored", # SIA-Library (not galaxy)
    'PJ': "Panic Trouble Restored",
    'PR': "Panic Alarm Restored",
    'PS': "Panic Supervisory", # SIA-Library (not galaxy)
    'PT': "Panic Trouble",
    'PU': "Panic Unbypass",

    # Q - Assist (Custom SIA)
    'QA': "Assist Alarm",
    'QB': "Assist Bypass",
    'QH': "Emergency Alarm Restored", # SIA-Library (not galaxy)
    'QJ': "Assist Trouble Restored",
    'QR': "Assist Alarm Restored",
    'QS': "Emergency Supervisory", # SIA-Library (not galaxy)
    'QT': "Assist Trouble",
    'QU': "Assist Unbypass",

    # R - Remote, Log, Test
    'RA': "Remote Program Call Failed", # SIA-Library (not galaxy)
    'RB': "Remote Program Begin",
    'RC': "Relay Closed",
    'RD': "Program Denied",
    'RN': "Remote Reset", # SIA-Library (not galaxy)
    'RO': "Relay Open",
    'RP': "Automatic Test",
    'RR': "Power Up",
    'RS': "Program Success",
    'RT': "Data Lost", # SIA-Library (not galaxy)
    'RU': "Remote Program Failed", # SIA-Library (not galaxy)
    'RX': "Manual Test",

    # S - Sprinkler (Custom SIA)
    'SA': "Sprinkler Alarm",
    'SB': "Sprinkler Bypass",
    'SH': "Sprinkler Alarm Restored", # SIA-Library (not galaxy)
    'SJ': "Sprinkler Trouble Restored",
    'SR': "Sprinkler Alarm Restored",
    'SS': "Sprinkler Supervisory", # SIA-Library (not galaxy)
    'ST': "Sprinkler Trouble",
    'SU': "Sprinkler Unbypass",

    # T - Tamper, Test
    'TA': "Tamper Alarm",
    'TB': "Tamper Bypass", # SIA-Library (not galaxy)
    'TE': "Test End",
    'TR': "Tamper Restore",
    'TS': "Test Start",
    'TU': "Tamper Unbypass", # SIA-Library (not galaxy)
    'TX': "Test Report",

    # U - Untyped Zone
    'UA': "Untyped Zone Alarm",
    'UB': "Untyped Zone Bypass",
    'UH': "Untyped Zone Alarm Restored", # SIA-Library (not galaxy)
    'UJ': "Untyped Zone Trouble Restored",
    'UR': "Untyped Zone Alarm Restored",
    'US': "Untyped Zone Supervisory", # SIA-Library (not galaxy)
    'UT': "Untyped Zone Trouble",
    'UU': "Untyped Zone Unbypass",
    'UX': "Undefined Alarm", # SIA-Library (not galaxy)
    'UY': "Untyped Zone Missing Trouble", # SIA-Library (not galaxy)
    'UZ': "Untyped Zone Missing Alarm", # SIA-Library (not galaxy)
    
    # V
    'VI': "Printer Paper In", # SIA-Library (not galaxy)
    'VO': "Printer Paper Out", # SIA-Library (not galaxy)
    'VR': "Printer Restored", # SIA-Library (not galaxy)
    'VT': "Printer Trouble", # SIA-Library (not galaxy)
    'VX': "Printer Test", # SIA-Library (not galaxy)
    'VY': "Print OC OL", # Note: Unclear code from Installer manual.
    'VZ': "Printer Off Line", # SIA-Library (not galaxy)

    # W - Water (Custom SIA)
    'WA': "Water Alarm",
    'WB': "Water Bypass",
    'WH': "Water Alarm Restored", # SIA-Library (not galaxy)
    'WJ': "Water Trouble Restored",
    'WR': "Water Alarm Restored",
    'WS': "Water Supervisory", # SIA-Library (not galaxy)
    'WT': "Water Trouble",
    'WU': "Water Unbypass",

    # X - RF (Radio Frequency)
    'XE': "Extra Point", # SIA-Library (not galaxy)
    'XF': "Extra RF Point", # SIA-Library (not galaxy)
    'XH': "RF Jam Restore",
    'XI': "Sensor Reset", # SIA-Library (not galaxy)
    'XQ': "RF Jam",
    'XR': "RF Battery Low Restore",
    'XT': "RF Battery Low",
    'XW': "Forced Point", # SIA-Library (not galaxy)

    # Y - Comms / System Status
    'YB': "Busy Seconds", # SIA-Library (not galaxy)
    'YC': "Comms Fail",
    'YD': "Receiver Line Card Trouble", # SIA-Library (not galaxy)
    'YE': "Receiver Line Card Restored", # SIA-Library (not galaxy)
    'YF': "Panel Cold Start",
    'YG': "Parameter Changed", # SIA-Library (not galaxy)
    'YK': "Comm Restoral",
    'YL': "+AC+ Battery Fail",
    'YM': "System Battery Missing",
    'YN': "Invalid Report", # SIA-Library (not galaxy)
    'YO': "Unknown Message", # SIA-Library (not galaxy)
    'YP': "PSU Fail",
    'YQ': "Power Supply Restored", # SIA-Library (not galaxy)
    'YR': "System Battery Restored",
    'YS': "Communication Trouble", # SIA-Library (not galaxy)
    'YT': "System Battery Trouble",
    'YW': "Watchdog Reset", # SIA-Library (not galaxy)
    'YX': "Service Required", # SIA-Library (not galaxy)
    'YY': "Status Report", # SIA-Library (not galaxy)
    'YZ': "Service Completed", # SIA-Library (not galaxy)

    # Z - Freezer (Custom SIA)
    'ZA': "Freezer Alarm",
    'ZB': "Freezer Bypass",
    'ZH': "Freeze Alarm Restored", # SIA-Library (not galaxy)
    'ZJ': "Freezer Trouble Restored",
    'ZR': "Freezer Alarm Restored",
    'ZS': "Freeze Supervisory", # SIA-Library (not galaxy)
    'ZT': "Freezer Trouble",
    'ZU': "Freezer Unbypass",

    # ============================================
    # Internal server event codes (not SIA protocol)
    # ============================================
    'MSG': 'Server Message',   # Generated by the server for watchdog alerts etc.
}

# ============================================
# CHARACTER ENCODING
# ============================================

# The panel transmits text using an 8-bit character encoding based on the
# IBM PC Code Page family (CP437 and variants). The specific variant may 
# depend on the panel's configured language/region setting.
#
# This server decodes text using CP437 as the base and applies the overrides
# below to correct characters that differ from standard CP437 on this panel.
# If you see incorrectly decoded characters, identify the hex value from the
# debug log and add an override entry here.
UNKNOWN_CHAR_MAP = {
    0xE9: 'Ø',  # Confirmed: panel shows Ø, CP437 gives Θ
    0xED: 'ø',  # Confirmed: panel shows ø, CP437 gives φ
}

