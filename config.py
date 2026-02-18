"""
Galaxy SIA Server Configuration

User-configurable settings for the SIA server.

Note: Most configuration moved to sia-server.conf.
      Left here are more complex configs, like EC priorities, Log format details and charachter encoding.
      This file is still in python format and very strict about formatting, indentation and such.
      Edit the file with care.
"""

# ============================================
# NOTIFICATION CONFIGURATION
# ============================================

# Only codes listed here will have custom priority.
# All other codes default to priority 5 (urgent - safest for unknown alarms)
EVENT_PRIORITIES = {
    # Low priority (2) - Tests and routine events
    'RX': 2,  # Manual test / Engineering test
    'RP': 2,  # Automatic test / Report
    'TS': 2,  # Test start
    'TE': 2,  # Test end
    
    # Normal priority (3) - Arm/Disarm/User actions
    'CL': 3,  # Closing (Armed)
    'OP': 3,  # Opening (Disarmed)
    'CA': 3,  # Automatic closing
    'OA': 3,  # Automatic opening
    'BC': 3,  # Burglary cancelled (user reset)
    'OR': 3,  # Opening restore / Alarm restore
    
    # High priority (4) - System issues (non-critical)
    'AR': 4,  # AC restore (mains power back)
    'XR': 4,  # Battery restore
    
    # All unlisted codes default to priority 5 (urgent)
    # This includes:
    # - BA: Burglary alarm
    # - BV: Burglary verified
    # - TA: Tamper alarm
    # - FA: Fire alarm
    # - PA: Panic alarm
    # - AT: AC trouble (mains failure)
    # - XT: Battery trouble
    # etc. (see full list in galaxy/constants.py)
}

# Default priority for unknown/unlisted event codes
DEFAULT_PRIORITY = 5  # Urgent - better safe than sorry!

# ============================================
# LOGGING CONFIGURATION
# ============================================

# Log file rotation settings
# Maximum log file size in bytes (10MB default)
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

# Number of backup log files to keep
LOG_BACKUP_COUNT = 5

# Log format
# Available fields: %(asctime)s, %(name)s, %(levelname)s, %(message)s
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# ============================================
# CHARACTER ENCODING
# ============================================

# Unknown character mapping - Galaxy proprietary encoding
# Used for mapping special language specific characters
# These are confirmed from actual captures
# You can add more as you discover them
UNKNOWN_CHAR_MAP = {
    b'\x8e': 'Ä',  # Confirmed in: ÅTERSTÄLL
    b'\x8f': 'Å',  # Confirmed in: PÅSLAG, SYSTEMÅT
    b'\x99': 'Ö',  # Confirmed in: FÖRDRÖJD
    b'\x86': 'å',  # Confirmed in: username test
    b'\x84': 'ä',  # Confirmed in: username test
    b'\x94': 'ö',  # Confirmed in: username test
}
