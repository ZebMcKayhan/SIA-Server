"""
Configuration loader for the Galaxy SIA Server.

Reads and validates settings from 'sia-server.conf' and 'defaults.py',
and provides them as clean Python objects to the main application.
"""

import configparser
import logging
import sys
import re
from galaxy.constants import UNKNOWN_CHAR_MAP

log = logging.getLogger(__name__)

class AppConfig:
    """A simple class to hold the final, validated configuration."""
    def __init__(self):
        # --- Settings from sia-server.conf ---
        self.LISTEN_ADDR = '0.0.0.0'
        self.LISTEN_PORT = 10000
        self.IP_CHECK_ENABLED = False
        self.IP_CHECK_ADDR = '0.0.0.0'
        self.IP_CHECK_PORT = 10001
        self.LOG_LEVEL = 'INFO'
        self.LOG_TO_FILE = False
        self.LOG_FILE = None
        self.ACCOUNT_SITES = {}
        self.NTFY_TOPICS = {}
        self.MAX_QUEUE_SIZE = 50
        self.MAX_RETRIES = 10
        self.MAX_RETRY_TIME = 30
        self.LOG_MAX_MB = 10
        self.LOG_BACKUP_COUNT = 5
        self.EVENT_PRIORITIES = {}
        self.DEFAULT_PRIORITY = 5
        self.UNKNOWN_CHAR_MAP = UNKNOWN_CHAR_MAP
        
        # --- Settings from defaults.py (advanced) ---
        self.EVENT_PRIORITIES = getattr(defaults, 'EVENT_PRIORITIES', {})
        self.DEFAULT_PRIORITY = getattr(defaults, 'DEFAULT_PRIORITY', 5)
        self.UNKNOWN_CHAR_MAP = getattr(defaults, 'UNKNOWN_CHAR_MAP', {})
        self.LOG_FORMAT = getattr(defaults, 'LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.LOG_DATE_FORMAT = getattr(defaults, 'LOG_DATE_FORMAT', '%Y-%m-%d %H:%M:%S')

def _validate_port(port: int, section: str, key: str) -> bool:
    """Helper function to validate a port number."""
    if not 1 <= port <= 65535:
        log.critical("Configuration Error in section [%s]: %s must be between 1 and 65535, but got %d.",
                     section, key, port)
        return False
    if port < 1024:
        # It's not a fatal error, but it requires special permissions. Warn the user.
        log.warning("Configuration Info in section [%s]: The port %d is a 'privileged' port (< 1024). "
                    "This may require running the server as a root user.", section, port)
    return True

def _parse_topic_config(config: configparser.ConfigParser, section_name: str) -> dict | None:
    """Helper function to parse notification settings for a given section."""
    
    # Rule 2: If NTFY_ENABLED is missing or No, or if NTFY_TOPIC is missing, disable.
    if not config.getboolean(section_name, 'ntfy_enabled', fallback=False):
        return None
    if not config.has_option(section_name, 'ntfy_topic'):
        log.warning("Section [%s] has NTFY_ENABLED=Yes but is missing NTFY_TOPIC. Notifications for this section will be disabled.", section_name)
        return None
        
    topic_config = {'enabled': True}
    topic_config['url'] = config.get(section_name, 'ntfy_topic')
    topic_config['title'] = config.get(section_name, 'ntfy_title', fallback='Galaxy Alarm')
    
    # Rule 3: If NTFY_AUTH is missing, default to None.
    auth_method = config.get(section_name, 'ntfy_auth', fallback='None').lower()
    
    if auth_method == 'token':
        token = config.get(section_name, 'ntfy_token', fallback=None)
        if token:
            topic_config['auth'] = {'method': 'token', 'token': token}
        else:
            log.warning("In section [%s], auth is 'Token' but 'ntfy_token' is missing. Auth will be disabled.", section_name)
    elif auth_method == 'userpass':
        user = config.get(section_name, 'ntfy_user', fallback=None)
        password = config.get(section_name, 'ntfy_pass', fallback=None)
        if user and password:
            topic_config['auth'] = {'method': 'userpass', 'user': user, 'pass': password}
        else:
            log.warning("In section [%s], auth is 'Userpass' but user/pass is incomplete. Auth will be disabled.", section_name)
            
    return topic_config


def load_and_validate_config() -> AppConfig:
    """
    Reads sia-server.conf, validates its contents, and returns a final
    AppConfig object.
    """
    config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
    if not config.read('sia-server.conf'):
        log.critical("Configuration Error: The 'sia-server.conf' file was not found or is empty.")
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
        log.critical("Configuration Error: The listen_port for [SIA-Server] and [IP-Check] cannot be the same (%d).", app_config.LISTEN_PORT)
        is_valid = False

    # --- Validate and load [Logging] section
    if config.has_section('Logging'):
        app_config.LOG_LEVEL = config.get('Logging', 'log_level', fallback='INFO').upper()
        log_to = config.get('Logging', 'log_to', fallback='Screen').lower()
        app_config.LOG_TO_FILE = (log_to == 'file')
        if app_config.LOG_TO_FILE:
            app_config.LOG_FILE = config.get('Logging', 'log_file', fallback=None)
            if not app_config.LOG_FILE:
                log.warning("LOG_TO is set to File, but no LOG_FILE was specified. Logging to screen instead.")
                app_config.LOG_TO_FILE = False
            # Parse and validate the log rotation settings
            try:
                max_mb = config.getint('Logging', 'log_max_mb', fallback=10)
                if 1 <= max_mb <= 100:
                    app_config.LOG_MAX_MB = max_mb
                else:
                    log.warning("Invalid LOG_MAX_MB '%d'. Must be between 1 and 100. Using default 10.", max_mb)
                
                backup_count = config.getint('Logging', 'log_backup_count', fallback=5)
                if 1 <= backup_count <= 10:
                    app_config.LOG_BACKUP_COUNT = backup_count
                else:
                    log.warning("Invalid LOG_BACKUP_COUNT '%d'. Must be between 1 and 10. Using default 5.", backup_count)
            except ValueError:
                log.warning("Invalid number in [Logging] for rotation settings. Using defaults.")

    # Validate and load [Notification] section ---
    if config.has_section('Notification'):
        try:
            app_config.MAX_QUEUE_SIZE = config.getint('Notification', 'max_que_size', fallback=50)
            app_config.MAX_RETRIES = config.getint('Notification', 'max_retries', fallback=10)
            app_config.MAX_RETRY_TIME = config.getint('Notification', 'max_retry_time', fallback=30)

            # Add some validation for the ranges
            if not 1 <= app_config.MAX_QUEUE_SIZE <= 1000:
                log.warning("Invalid MAX_QUE_SIZE '%d'. Must be between 1 and 1000. Using default 50.", app_config.MAX_QUEUE_SIZE)
                app_config.MAX_QUEUE_SIZE = 50
            if app_config.MAX_RETRIES < 0:
                log.warning("Invalid MAX_RETRIES '%d'. Cannot be negative. Using default 10.", app_config.MAX_RETRIES)
                app_config.MAX_RETRIES = 10
            if not 1 <= app_config.MAX_RETRY_TIME <= 1000:
                log.warning("Invalid MAX_RETRY_TIME '%d'. Must be between 1 and 1000. Using default 30.", app_config.MAX_RETRY_TIME)
                app_config.MAX_RETRY_TIME = 30

            # Parsing EC Codes Notification Priorities:
            event_priorities = {}
            for i in range(1, 6): # Check for PRIORITY_1 through PRIORITY_5
                key = f'priority_{i}'
                # Get the string, falling back to empty if the key is missing
                priority_str = config.get('Notification', key, fallback='')
                
                # Split by commas OR spaces, and filter out any empty strings
                codes = [code.strip().upper() for code in re.split(r'[, ]+', priority_str) if code.strip()]
                
                for code in codes:
                    if len(code) == 2:
                        event_priorities[code] = i
                    else:
                        log.warning("In [Notification], ignoring invalid event code '%s' in %s. Codes must be 2 characters.", code, key.upper())
            
            app_config.EVENT_PRIORITIES = event_priorities
            
            # Parse the default priority
            app_config.DEFAULT_PRIORITY = config.getint('Notification', 'default_priority', fallback=5)
            if not 1 <= app_config.DEFAULT_PRIORITY <= 5:
                log.warning("Invalid DEFAULT_PRIORITY '%d'. Must be between 1 and 5. Using default 5.", app_config.DEFAULT_PRIORITY)
                app_config.DEFAULT_PRIORITY = 5
        
        except ValueError:
            log.warning("Invalid number in [Notification] section. Using default queue settings.")
            # Defaults are already set in AppConfig, so no action needed.
            pass

    # --- Load Site and Default Sections ---
    system_sections = ['SIA-Server', 'IP-Check', 'Logging']
    account_sections = [s for s in config.sections() if s not in system_sections]

    for section_name in account_sections:
        # The section name IS the account number, unless it's the special 'Default' section
        is_default = (section_name == 'Default')
        account_number = 'default' if is_default else section_name
        
        # Rule 1: If SITE_NAME is missing, default to the account number.
        if not is_default:
            site_name = config.get(section_name, 'site_name', fallback=account_number)
            app_config.ACCOUNT_SITES[account_number] = site_name
        
        # Parse notification settings for this section
        topic_config = _parse_topic_config(config, section_name)
        if topic_config:
            app_config.NTFY_TOPICS[account_number] = topic_config
        
    if not is_valid:
        log.critical("Configuration validation failed. Please check the errors above. Exiting.")
        sys.exit(1)
        
    log.info("Configuration loaded successfully from sia-server.conf and defaults.py.")
    return app_config
