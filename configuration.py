"""
Configuration loader for the Galaxy SIA Server.

Reads and validates settings from 'sia-server.conf',
and provides them as clean Python objects to the main application.

Loading is done in two phases:
  Phase 1: load_logging_config() - reads only [Logging] section so that
           logging can be set up as early as possible.
  Phase 2: load_full_config()    - reads all remaining configuration with
           logging now fully available.
"""

import configparser
import logging
import logging.handlers
import sys
import re
from galaxy.constants import UNKNOWN_CHAR_MAP

log = logging.getLogger(__name__)

# ===================================================================
# PHASE 1: Logging Configuration
# ===================================================================

class LoggingConfig:
    """Holds only the logging-related configuration settings."""
    def __init__(self):
        self.LOG_LEVEL        = 'INFO'
        self.LOG_TO_FILE      = False
        self.LOG_TO_SYSLOG    = False
        self.LOG_FILE         = None
        self.LOG_MAX_MB       = 10
        self.LOG_BACKUP_COUNT = 5
        self.LOG_FORMAT       = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        self.LOG_DATE_FORMAT  = '%Y-%m-%d %H:%M:%S'
        self.SYSLOG_FORMAT    = 'SIA-Server: %(levelname)s - %(message)s'
        self.SYSLOG_SOCKET    = '/dev/log'
        self.SYSLOG_FACILITY  = logging.handlers.SysLogHandler.LOG_USER


def load_logging_config() -> LoggingConfig:
    """
    Phase 1: Reads ONLY the [Logging] section from sia-server.conf.
    This is intentionally minimal and fast so that logging can be
    configured as early as possible in the startup sequence.
    Returns a LoggingConfig object with defaults if the section is missing.
    """
    logging_config = LoggingConfig()

    config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))

    try:
        if not config.read('sia-server.conf'):
            print("CRITICAL: 'sia-server.conf' was not found or is empty.", file=sys.stderr)
            sys.exit(1)
    except configparser.DuplicateSectionError as e:
        print(f"CRITICAL: Duplicate section in sia-server.conf: {e}", file=sys.stderr)
        print("CRITICAL: Please ensure each account number appears only once.", file=sys.stderr)
        sys.exit(1)

    if not config.has_section('Logging'):
        # No logging section found, use all defaults silently.
        return logging_config

    logging_config.LOG_LEVEL = config.get('Logging', 'log_level', fallback='INFO').upper()

    log_to = config.get('Logging', 'log_to', fallback='Screen').lower()
    logging_config.LOG_TO_FILE   = (log_to == 'file')
    logging_config.LOG_TO_SYSLOG = (log_to == 'syslog')

    if logging_config.LOG_TO_SYSLOG:
        logging_config.SYSLOG_SOCKET = config.get('Logging', 'syslog_socket', fallback='/dev/log')

        facility_str = config.get('Logging', 'syslog_facility', fallback='user').lower()
        facility_map = {
            'user':   logging.handlers.SysLogHandler.LOG_USER,
            'daemon': logging.handlers.SysLogHandler.LOG_DAEMON,
            'local0': logging.handlers.SysLogHandler.LOG_LOCAL0,
            'local1': logging.handlers.SysLogHandler.LOG_LOCAL1,
            'local2': logging.handlers.SysLogHandler.LOG_LOCAL2,
            'local3': logging.handlers.SysLogHandler.LOG_LOCAL3,
            'local4': logging.handlers.SysLogHandler.LOG_LOCAL4,
            'local5': logging.handlers.SysLogHandler.LOG_LOCAL5,
            'local6': logging.handlers.SysLogHandler.LOG_LOCAL6,
            'local7': logging.handlers.SysLogHandler.LOG_LOCAL7,
        }
        if facility_str in facility_map:
            logging_config.SYSLOG_FACILITY = facility_map[facility_str]
        else:
            print(f"WARNING: Invalid SYSLOG_FACILITY '{facility_str}'. Using default 'user'.",
                  file=sys.stderr)

    if logging_config.LOG_TO_FILE:
        logging_config.LOG_FILE = config.get('Logging', 'log_file', fallback=None)
        if not logging_config.LOG_FILE:
            print("WARNING: LOG_TO = File but no LOG_FILE specified. Falling back to screen.",
                  file=sys.stderr)
            logging_config.LOG_TO_FILE = False
        else:
            try:
                max_mb = config.getint('Logging', 'log_max_mb', fallback=10)
                logging_config.LOG_MAX_MB = max_mb if 1 <= max_mb <= 100 else 10

                backup_count = config.getint('Logging', 'log_backup_count', fallback=5)
                logging_config.LOG_BACKUP_COUNT = backup_count if 1 <= backup_count <= 10 else 5
            except ValueError:
                pass  # Use defaults

    return logging_config


# ===================================================================
# PHASE 2: Full Application Configuration
# ===================================================================

class AppConfig:
    """Holds the complete, validated application configuration."""
    def __init__(self):
        # --- Settings from sia-server.conf ---
        self.LISTEN_ADDR      = '0.0.0.0'
        self.LISTEN_PORT      = 10000
        self.REJECT_POLICY    = 'respond'
        self.IP_CHECK_ENABLED = False
        self.IP_CHECK_ADDR    = '0.0.0.0'
        self.IP_CHECK_PORT    = 10001
        self.ACCOUNT_SITES    = {}
        self.NTFY_TOPICS      = {}
        self.ACCOUNT_POLICIES = {}
        self.MAX_QUEUE_SIZE   = 50
        self.MAX_RETRIES      = 10
        self.MAX_RETRY_TIME   = 30
        self.EVENT_PRIORITIES = {}
        self.DEFAULT_PRIORITY = 5
        # --- Advanced / Constant Defaults ---
        self.UNKNOWN_CHAR_MAP = UNKNOWN_CHAR_MAP


def _validate_port(port: int, section: str, key: str) -> bool:
    """Helper function to validate a port number."""
    if not 1 <= port <= 65535:
        log.critical("Configuration Error in section [%s]: %s must be between 1 and 65535, but got %d.",
                     section, key, port)
        return False
    if port < 1024:
        log.warning("Configuration Info in section [%s]: The port %d is a 'privileged' port (< 1024). "
                    "This may require running the server as a root user.", section, port)
    return True


def _parse_topic_config(config: configparser.ConfigParser, section_name: str) -> dict | None:
    """Helper function to parse notification settings for a given section."""
    if not config.getboolean(section_name, 'ntfy_enabled', fallback=False):
        return None
    if not config.has_option(section_name, 'ntfy_topic'):
        log.warning("Section [%s] has NTFY_ENABLED=Yes but is missing NTFY_TOPIC. "
                    "Notifications for this section will be disabled.", section_name)
        return None

    topic_config = {'enabled': True}
    topic_config['url']   = config.get(section_name, 'ntfy_topic')
    topic_config['title'] = config.get(section_name, 'ntfy_title', fallback='Galaxy Alarm')

    auth_method = config.get(section_name, 'ntfy_auth', fallback='None').lower()

    if auth_method == 'token':
        token = config.get(section_name, 'ntfy_token', fallback=None)
        if token:
            topic_config['auth'] = {'method': 'token', 'token': token}
        else:
            log.warning("In section [%s], auth is 'Token' but 'ntfy_token' is missing. "
                        "Auth will be disabled.", section_name)
    elif auth_method == 'userpass':
        user     = config.get(section_name, 'ntfy_user', fallback=None)
        password = config.get(section_name, 'ntfy_pass', fallback=None)
        if user and password:
            topic_config['auth'] = {'method': 'userpass', 'user': user, 'pass': password}
        else:
            log.warning("In section [%s], auth is 'Userpass' but user/pass is incomplete. "
                        "Auth will be disabled.", section_name)

    return topic_config


def load_full_config() -> AppConfig:
    """
    Phase 2: Reads and validates all remaining configuration from sia-server.conf.
    Logging is fully available at this point so all warnings and errors
    will be captured correctly.
    """
    config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))

    try:
        if not config.read('sia-server.conf'):
            log.critical("Configuration Error: 'sia-server.conf' was not found or is empty.")
            sys.exit(1)
    except configparser.DuplicateSectionError as e:
        log.critical("Configuration Error: Duplicate section in sia-server.conf: %s", e)
        log.critical("Please ensure each account number appears only once.")
        sys.exit(1)

    app_config = AppConfig()
    is_valid = True

    # --- Validate and load [SIA-Server] section ---
    if not config.has_section('SIA-Server'):
        log.critical("Configuration error: [SIA-Server] section is missing in sia-server.conf")
        is_valid = False

    try:
        app_config.LISTEN_ADDR = config.get('SIA-Server', 'listen_addr', fallback='0.0.0.0')
        sia_port = config.getint('SIA-Server', 'listen_port', fallback=10000)
        if _validate_port(sia_port, 'SIA-Server', 'listen_port'):
            app_config.LISTEN_PORT = sia_port
        else:
            is_valid = False
    except ValueError:
        log.critical("Configuration Error in [SIA-Server]: listen_port must be a number.")
        is_valid = False

    # --- Parse REJECT_POLICY ---
    reject_policy = config.get('SIA-Server', 'reject_policy', fallback='respond').lower()
    if reject_policy not in ['drop', 'respond']:
        log.warning("Invalid REJECT_POLICY '%s' in [SIA-Server]. "
                    "Must be 'drop' or 'respond'. Using default 'respond'.", reject_policy)
        reject_policy = 'respond'
    app_config.REJECT_POLICY = reject_policy

    if reject_policy == 'drop':
        log.info("Reject Policy: DROP - Invalid connections will be silently closed.")
    else:
        log.info("Reject Policy: RESPOND - Invalid connections will receive a SIA REJECT.")

    # --- Validate and load [IP-Check] section ---
    if config.has_section('IP-Check'):
        if config.getboolean('IP-Check', 'enabled', fallback=False):
            app_config.IP_CHECK_ENABLED = True
            app_config.IP_CHECK_ADDR = config.get('IP-Check', 'listen_addr', fallback='0.0.0.0')
            try:
                ip_check_port = config.getint('IP-Check', 'listen_port', fallback=10001)
                if _validate_port(ip_check_port, 'IP-Check', 'listen_port'):
                    app_config.IP_CHECK_PORT = ip_check_port
                else:
                    is_valid = False
            except ValueError:
                log.critical("Configuration Error in [IP-Check]: listen_port must be a number.")
                is_valid = False

    # --- Check for port conflicts ---
    if app_config.IP_CHECK_ENABLED and app_config.LISTEN_PORT == app_config.IP_CHECK_PORT:
        log.critical("Configuration Error: The listen_port for [SIA-Server] and [IP-Check] "
                     "cannot be the same (%d).", app_config.LISTEN_PORT)
        is_valid = False

    # --- Validate and load [Notification] section ---
    if config.has_section('Notification'):
        try:
            app_config.MAX_QUEUE_SIZE = config.getint('Notification', 'max_que_size', fallback=50)
            app_config.MAX_RETRIES    = config.getint('Notification', 'max_retries', fallback=10)
            app_config.MAX_RETRY_TIME = config.getint('Notification', 'max_retry_time', fallback=30)

            if not 1 <= app_config.MAX_QUEUE_SIZE <= 1000:
                log.warning("Invalid MAX_QUE_SIZE '%d'. Must be 1-1000. Using default 50.",
                            app_config.MAX_QUEUE_SIZE)
                app_config.MAX_QUEUE_SIZE = 50
            if app_config.MAX_RETRIES < 0:
                log.warning("Invalid MAX_RETRIES '%d'. Cannot be negative. Using default 10.",
                            app_config.MAX_RETRIES)
                app_config.MAX_RETRIES = 10
            if not 1 <= app_config.MAX_RETRY_TIME <= 1000:
                log.warning("Invalid MAX_RETRY_TIME '%d'. Must be 1-1000. Using default 30.",
                            app_config.MAX_RETRY_TIME)
                app_config.MAX_RETRY_TIME = 30

            # --- Parse Event Priorities ---
            event_priorities = {}
            for i in range(1, 6):
                key = f'priority_{i}'
                priority_str = config.get('Notification', key, fallback='')
                codes = [code.strip().upper()
                         for code in re.split(r'[, ]+', priority_str) if code.strip()]
                for code in codes:
                    if len(code) == 2:
                        if code in event_priorities:
                            old_priority = event_priorities[code]
                            log.warning("Duplicate event code '%s': found in PRIORITY_%d and "
                                        "PRIORITY_%d. Using highest priority (%d).",
                                        code, old_priority, i, i)
                        event_priorities[code] = i
                    else:
                        log.warning("In [Notification], ignoring invalid event code '%s' in %s. "
                                    "Codes must be 2 characters.", code, key.upper())
            app_config.EVENT_PRIORITIES = event_priorities

            # --- Parse Default Priority ---
            app_config.DEFAULT_PRIORITY = config.getint('Notification', 'default_priority',
                                                         fallback=5)
            if not 1 <= app_config.DEFAULT_PRIORITY <= 5:
                log.warning("Invalid DEFAULT_PRIORITY '%d'. Must be 1-5. Using default 5.",
                            app_config.DEFAULT_PRIORITY)
                app_config.DEFAULT_PRIORITY = 5

        except ValueError:
            log.warning("Invalid number in [Notification] section. Using default queue settings.")

    # --- Load Site and Default Sections ---
    system_sections = ['SIA-Server', 'IP-Check', 'Logging', 'Notification']
    account_sections = [s for s in config.sections() if s not in system_sections]

    for section_name in account_sections:
        is_default     = (section_name == 'Default')
        account_number = 'default' if is_default else section_name

        if not is_default:
            site_name = config.get(section_name, 'site_name', fallback=account_number)
            app_config.ACCOUNT_SITES[account_number] = site_name

        topic_config = _parse_topic_config(config, section_name)
        if topic_config:
            app_config.NTFY_TOPICS[account_number] = topic_config

        # --- Parse Connection Policy ---
        policy_str = config.get(section_name, 'enabled', fallback='yes').lower()
        if policy_str in ['true', 'yes']:
            policy = 'yes'
        elif policy_str in ['false', 'no']:
            policy = 'no'
        elif policy_str == 'secure':
            policy = 'secure'
        else:
            log.warning("Invalid 'enabled' value '%s' in section [%s]. Defaulting to 'yes'.",
                        policy_str, section_name)
            policy = 'yes'
        app_config.ACCOUNT_POLICIES[account_number] = policy

    if not is_valid:
        log.critical("Configuration validation failed. Please check the errors above. Exiting.")
        sys.exit(1)

    log.info("Configuration loaded successfully from sia-server.conf.")
    return app_config
