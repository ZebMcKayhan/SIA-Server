"""
Configuration loader for the Galaxy SIA Server.

Reads and validates settings from 'sia-server.conf',
and provides them as clean Python objects to the main application.

Loading is done in three phases:
  Phase 1: load_logging_config()     - reads only [Logging] section so that
           logging can be set up as early as possible.
  Phase 2: load_application_config() - reads all server/infrastructure
           configuration with logging now fully available.
  Phase 3: load_accounts()           - reads all account sections and returns
           an AccountsConfig object with provider-agnostic raw config.
"""

import configparser
import logging
import logging.handlers
import sys
import re
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from galaxy.constants import UNKNOWN_CHAR_MAP

log = logging.getLogger(__name__)

NOTIFICATION_FIELDS = {
    'time',
    'action_text',
    'account',
    'site_name',
    'event_type',
    'user_id',
    'peripheral',
    'group',
    'value',
    'event_code',
    'event_description',
    'zone',
}

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


def load_logging_config(config_file: str = 'sia-server.conf') -> LoggingConfig:
    """
    Phase 1: Reads ONLY the [Logging] section from the configuration file.
    This is intentionally minimal and fast so that logging can be
    configured as early as possible in the startup sequence.
    Returns a LoggingConfig object with defaults if the section is missing.
    """
    logging_config = LoggingConfig()

    config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))

    try:
        if not config.read(config_file):
            print(f"CRITICAL: '{config_file}' was not found or is empty.", file=sys.stderr)
            sys.exit(1)
    except configparser.DuplicateSectionError as e:
        print(f"CRITICAL: Duplicate section in '{config_file}': {e}", file=sys.stderr)
        print("CRITICAL: Please ensure each account number appears only once.", file=sys.stderr)
        sys.exit(1)

    if not config.has_section('Logging'):
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
                pass

    return logging_config

def load_log_level(config_file: str = 'sia-server.conf') -> str:
    """Read just the log level from the config file for SIGHUP reload."""
    config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
    config.read(config_file)
    return config.get('Logging', 'log_level', fallback='INFO').upper()
  
# ===================================================================
# PHASE 2: Application Configuration
# ===================================================================

class AppConfig:
    """Holds the complete, validated application configuration."""
    def __init__(self):
        self.SIA_SERVER_ENABLED    = True
        self.LISTEN_ADDR           = '0.0.0.0'
        self.LISTEN_PORT           = 10000
        self.REJECT_POLICY         = 'respond'
        self.IP_CHECK_ENABLED      = False
        self.IP_CHECK_ADDR         = '0.0.0.0'
        self.IP_CHECK_PORT         = 10001
        self.IP_CHECK_WATCHDOG     = 2.1
        self.IP_CHECK_LOST_PRIO    = 4
        self.IP_CHECK_RESTORE_PRIO = 2
        self.MAX_QUEUE_SIZE        = 50
        self.MAX_RETRIES           = 10
        self.MAX_RETRY_TIME        = 30
        self.NOTIFICATION_FORMAT_ASCII = (
            "%time %action_text [(Group: %group)]"
        )
        self.NOTIFICATION_FORMAT_DATA = (
            "%time Event: %event_code [(%event_description)]"
            "[ User: %user_id]"
            "[ Zone: %zone]"
            "[ Group: %group]"
            "[ Peripheral: %peripheral]"
            "[ Value: %value]"
        )
        self.EVENT_PRIORITIES      = {}
        self.DEFAULT_PRIORITY      = 5
        self.UNKNOWN_CHAR_MAP      = UNKNOWN_CHAR_MAP


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

def _validate_notification_format(template: str, name: str) -> bool:
    """Validate a notification format string."""
    is_valid = True
    bracket_depth = 0

    for char in template:
        if char == '[':
            bracket_depth += 1
            if bracket_depth > 1:
                log.warning(
                    "Invalid %s: nested optional sections are not supported.",
                    name
                )
                is_valid = False
                break

        elif char == ']':
            bracket_depth -= 1
            if bracket_depth < 0:
                log.warning(
                    "Invalid %s: unexpected ']' in format.",
                    name
                )
                is_valid = False
                break

    if bracket_depth != 0:
        log.warning(
            "Invalid %s: unmatched '[' or ']'.",
            name
        )
        is_valid = False

    fields = re.findall(r'%([a-zA-Z_][a-zA-Z0-9_]*)', template)

    for field_name in fields:
        if field_name not in NOTIFICATION_FIELDS:
            log.warning(
                "Invalid %s: unknown field '%%%s'.",
                name,
                field_name
            )
            is_valid = False

    return is_valid
  
def load_application_config(config_file: str = 'sia-server.conf') -> AppConfig:
    """
    Phase 2: Reads and validates server/infrastructure configuration.
    Logging is fully available at this point.
    Account configuration is handled separately by load_accounts().
    """
    config = configparser.ConfigParser(
        inline_comment_prefixes=('#', ';'),
        interpolation=None,
    )

    try:
        if not config.read(config_file):
            log.critical("Configuration Error: '%s' was not found or is empty.", config_file)
            sys.exit(1)
    except configparser.DuplicateSectionError as e:
        log.critical("Configuration Error: Duplicate section in '%s': %s", config_file, e)
        log.critical("Please ensure each account number appears only once.")
        sys.exit(1)

    app_config = AppConfig()
    is_valid = True

    # --- Validate and load [SIA-Server] section ---
    if not config.has_section('SIA-Server'):
        log.critical("Configuration error: [SIA-Server] section is missing in '%s'.", config_file)
        is_valid = False

    sia_enabled = config.get('SIA-Server', 'enabled', fallback='yes').lower()
    if sia_enabled in ('yes', 'true'):
        app_config.SIA_SERVER_ENABLED = True
    elif sia_enabled in ('no', 'false'):
        app_config.SIA_SERVER_ENABLED = False
    else:
        log.warning("Invalid ENABLED value '%s' in [SIA-Server]. Defaulting to 'yes'.", sia_enabled)
        app_config.SIA_SERVER_ENABLED = True

    if app_config.SIA_SERVER_ENABLED:
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

            try:
                threshold = config.getfloat('IP-Check', 'watchdog_threshold',
                                            fallback=app_config.IP_CHECK_WATCHDOG)
                if threshold <= 1.0:
                    log.info("Watchdog is DISABLED (watchdog_threshold = %.1f).", threshold)
                    app_config.IP_CHECK_WATCHDOG = threshold
                elif threshold > 10.0:
                    log.warning("Invalid WATCHDOG_THRESHOLD '%.1f' in [IP-Check]. "
                                "Must be 1.1 - 10.0 or <= 1.0 to disable. Using default %.1f.",
                                threshold, app_config.IP_CHECK_WATCHDOG)
                else:
                    app_config.IP_CHECK_WATCHDOG = threshold
            except ValueError:
                log.warning("Invalid WATCHDOG_THRESHOLD in [IP-Check]. Must be a number. "
                            "Using default %.1f.", app_config.IP_CHECK_WATCHDOG)

            try:
                lost_prio = config.getint('IP-Check', 'watchdog_lost_prio',
                                          fallback=app_config.IP_CHECK_LOST_PRIO)
                if not 1 <= lost_prio <= 5:
                    log.warning("Invalid WATCHDOG_LOST_PRIO '%d' in [IP-Check]. "
                                "Must be 1-5. Using default %d.",
                                lost_prio, app_config.IP_CHECK_LOST_PRIO)
                else:
                    app_config.IP_CHECK_LOST_PRIO = lost_prio
            except ValueError:
                log.warning("Invalid WATCHDOG_LOST_PRIO in [IP-Check]. Must be a number. "
                            "Using default %d.", app_config.IP_CHECK_LOST_PRIO)

            try:
                restore_prio = config.getint('IP-Check', 'watchdog_restore_prio',
                                             fallback=app_config.IP_CHECK_RESTORE_PRIO)
                if not 1 <= restore_prio <= 5:
                    log.warning("Invalid WATCHDOG_RESTORE_PRIO '%d' in [IP-Check]. "
                                "Must be 1-5. Using default %d.",
                                restore_prio, app_config.IP_CHECK_RESTORE_PRIO)
                else:
                    app_config.IP_CHECK_RESTORE_PRIO = restore_prio
            except ValueError:
                log.warning("Invalid WATCHDOG_RESTORE_PRIO in [IP-Check]. Must be a number. "
                            "Using default %d.", app_config.IP_CHECK_RESTORE_PRIO)

    # --- Check for port conflicts ---
    if app_config.SIA_SERVER_ENABLED and app_config.IP_CHECK_ENABLED and \
       app_config.LISTEN_PORT == app_config.IP_CHECK_PORT:
        log.critical("Configuration Error: The listen_port for [SIA-Server] and [IP-Check] "
                     "cannot be the same (%d).", app_config.LISTEN_PORT)
        is_valid = False

    # --- Validate and load [Notification] section ---
    if config.has_section('Notification'):
        try:
            # --- Parse Notification Formats ---
            notification_format_ascii = config.get(
                'Notification',
                'notification_format_ascii',
                fallback=app_config.NOTIFICATION_FORMAT_ASCII
            )

            if _validate_notification_format(
                notification_format_ascii,
                'NOTIFICATION_FORMAT_ASCII'
            ):
                app_config.NOTIFICATION_FORMAT_ASCII = notification_format_ascii
            else:
                log.warning(
                    "Invalid NOTIFICATION_FORMAT_ASCII. Using default format."
                )

            notification_format_data = config.get(
                'Notification',
                'notification_format_data',
                fallback=app_config.NOTIFICATION_FORMAT_DATA
            )

            if _validate_notification_format(
                notification_format_data,
                'NOTIFICATION_FORMAT_DATA'
            ):
                app_config.NOTIFICATION_FORMAT_DATA = notification_format_data
            else:
                log.warning(
                    "Invalid NOTIFICATION_FORMAT_DATA. Using default format."
                )
            # --- Parse queue config ---
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

            app_config.DEFAULT_PRIORITY = config.getint('Notification', 'default_priority',
                                                         fallback=5)
            if not 1 <= app_config.DEFAULT_PRIORITY <= 5:
                log.warning("Invalid DEFAULT_PRIORITY '%d'. Must be 1-5. Using default 5.",
                            app_config.DEFAULT_PRIORITY)
                app_config.DEFAULT_PRIORITY = 5

        except ValueError:
            log.warning("Invalid number in [Notification] section. Using default queue settings.")

    if not is_valid:
        log.critical("Configuration validation failed. Please check the errors above. Exiting.")
        sys.exit(1)

    log.info("Application configuration loaded successfully from '%s'.", config_file)
    return app_config


# ===================================================================
# PHASE 3: Account Configuration
# ===================================================================

@dataclass
class AccountConfig:
    """Configuration for a single account/site."""
    account_number: str
    site_name: Optional[str]
    policy: str              # 'yes' | 'no' | 'secure'
    provider_config: dict    # raw key-value pairs, provider-agnostic


@dataclass
class AccountsConfig:
    """All configured accounts including the default fallback."""
    load_time: float
    accounts: Dict[str, AccountConfig] = field(default_factory=dict)

    def get(self, account_number: str) -> Optional[AccountConfig]:
        """Get account config, falling back to default if not found."""
        return self.accounts.get(account_number,
                                 self.accounts.get('default'))


def load_accounts(config_file: str = 'sia-server.conf') -> AccountsConfig:
    """
    Phase 3: Reads all account sections from the config file and returns
    an AccountsConfig object. Each account's provider-specific settings
    are stored as a raw dict - notification.py decides what to do with them.
    """
    config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))

    try:
        if not config.read(config_file):
            log.critical("Configuration Error: '%s' was not found or is empty.", config_file)
            sys.exit(1)
    except configparser.DuplicateSectionError as e:
        log.critical("Configuration Error: Duplicate section in '%s': %s", config_file, e)
        log.critical("Please ensure each account number appears only once.")
        sys.exit(1)

    accounts_config = AccountsConfig(load_time=time.time())

    system_sections = {'SIA-Server', 'IP-Check', 'Logging', 'Notification'}
    account_sections = [s for s in config.sections() if s not in system_sections]

    for section_name in account_sections:
        is_default     = (section_name == 'Default')
        account_number = 'default' if is_default else section_name.lstrip('0') or '0'

        # Site name - None if not configured, account number used as fallback at display time
        site_name = config.get(section_name, 'site_name', fallback=None)

        # Connection policy
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

        # Raw provider config - everything in the section as-is
        provider_config = dict(config.items(section_name))

        accounts_config.accounts[account_number] = AccountConfig(
            account_number=account_number,
            site_name=site_name,
            policy=policy,
            provider_config=provider_config,
        )

        log.debug("Loaded account '%s' (site: '%s', policy: '%s')",
                  account_number, site_name, policy)

    log.info("Loaded %d account(s) from '%s'.",
             len(accounts_config.accounts), config_file)
    return accounts_config
