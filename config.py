"""
Galaxy SIA Server Configuration

User-configurable settings for the SIA server.
"""

# ============================================
# SERVER CONFIGURATION
# ============================================

# Server listening address
# Use '0.0.0.0' to listen on all interfaces
# Use '127.0.0.1' to listen only locally
LISTEN_ADDR = '0.0.0.0'

# Server listening port
# Default SIA port is 10000
LISTEN_PORT = 10000


# ============================================
# ACCOUNT MAPPING
# ============================================

# Map account numbers to site names
# Add your alarm system account numbers here
# If account number does not exist in the list, it will just use the account number for log and notification.
ACCOUNT_SITES = {
    '023456': 'Main House',
    # Add more accounts if monitoring multiple sites:
    # '987654': 'Cabin',
    # '758432': 'Office',
}

# ============================================
# NOTIFICATION CONFIGURATION
# ============================================

# ntfy.sh configuration
NTFY_ENABLED = True #True / False
NOTIFICATION_TITLE = 'Galaxy FLEX'

# --- Notification Routing ---
# Define how notifications are sent. Each account number can be mapped to a
# specific ntfy.sh topic with its own authentication details.

NTFY_TOPICS = {
    # --- Example 1: A simple, public topic for a single user ---
    'default': {
        'url': 'https://ntfy.sh/my-public-alarm-topic',
        'auth': None, # No authentication needed
    },

# --- Example 2: A multi-user setup with different private topics ---
    # '027978': { # My Home (Private, using a token)
    #     'url': 'https://ntfy.sh/my-private-home-topic',
    #     'auth': {
    #         'method': 'token',
    #         'token': 'tk_secrettokenformyhome_abc123'
    #     }
    # },
    # '123456': { # Friend's Cabin (Private, using user/pass)
    #     'url': 'https://ntfy.sh/friends-private-cabin',
    #     'auth': {
    #         'method': 'userpass',
    #         'user': 'friend_user',
    #         'pass': 'friend_password'
    #     }
    # },
    # '789012': { # Another friend's public topic
    #     'url': 'https://ntfy.sh/another-friend-public',
    #     'auth': None # Explicitly no authentication
    # },
    # 'default': { # For any unknown accounts
    #     'url': 'https://ntfy.sh/unknown-alarm-logs',
    #     'auth': None
    # }
}
# Event code to notification priority mapping
# Priority levels (ntfy.sh):
#   1 = Min (no notification, no sound)
#   2 = Low (no sound)
#   3 = Default (sound)
#   4 = High (sound + popup)
#   5 = Urgent (sound + popup + vibration)
#
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

# Logging level: DEBUG, INFO, WARNING, ERROR
# DEBUG: Detailed information for diagnosing problems
# INFO: General informational messages
# WARNING: Warning messages
# ERROR: Error messages only
LOG_LEVEL = 'INFO'

# Log to file (True) or console/screen (False)
LOG_TO_FILE = True # True / False

# Log file path (only used if LOG_TO_FILE = True)
# Note, Windows users will need to escape \ like this: 'C:\\Temp\\sia-server.log'
LOG_FILE = '/tmp/sia-server.log'

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
