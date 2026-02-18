# In configuration.py

"""
Configuration loader for the Galaxy SIA Server.

Reads and validates settings from 'sia-server.conf' and 'defaults.py',
and provides them as clean Python objects to the main application.
"""

import configparser
import logging
import sys

# Import the advanced/default settings
import defaults

log = logging.getLogger(__name__)

# A simple class to hold the final, validated configuration
class AppConfig:
    def __init__(self):
        # Default values
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
        # Get advanced configs from defaults.py
        self.EVENT_PRIORITIES = defaults.EVENT_PRIORITIES
        self.DEFAULT_PRIORITY = defaults.DEFAULT_PRIORITY
        self.UNKNOWN_CHAR_MAP = defaults.UNKNOWN_CHAR_MAP
        self.LOG_FORMAT = defaults.LOG_FORMAT
        self.LOG_DATE_FORMAT = defaults.LOG_DATE_FORMAT
        self.LOG_MAX_BYTES = defaults.LOG_MAX_BYTES
        self.LOG_BACKUP_COUNT = defaults.LOG_BACKUP_COUNT

def load_and_validate_config() -> AppConfig:
    """
    Reads sia-server.conf, validates its contents, and returns a final
    AppConfig object.
    """
    config = configparser.ConfigParser()
    config.read('sia-server.conf')
    
    app_config = AppConfig()
    
    # --- Validate and load [SIA-Server] section ---
    if not config.has_section('SIA-Server'):
        log.critical("Configuration error: [SIA-Server] section is missing in sia-server.conf")
        sys.exit(1)
    app_config.LISTEN_ADDR = config.get('SIA-Server', 'listen_addr', fallback='0.0.0.0')
    app_config.LISTEN_PORT = config.getint('SIA-Server', 'listen_port', fallback=10000)

    # --- Validate and load [IP-Check] section ---
    if config.has_section('IP-Check'):
        app_config.IP_CHECK_ENABLED = config.getboolean('IP-Check', 'enabled', fallback=False)
        if app_config.IP_CHECK_ENABLED:
            app_config.IP_CHECK_ADDR = config.get('IP-Check', 'listen_addr', fallback='0.0.0.0')
            app_config.IP_CHECK_PORT = config.getint('IP-Check', 'listen_port', fallback=10001)

    # --- Validate and load [Logging] section ---
    if config.has_section('Logging'):
        app_config.LOG_LEVEL = config.get('Logging', 'log_level', fallback='INFO').upper()
        log_to = config.get('Logging', 'log_to', fallback='Screen').lower()
        app_config.LOG_TO_FILE = (log_to == 'file')
        if app_config.LOG_TO_FILE:
            app_config.LOG_FILE = config.get('Logging', 'log_file', fallback=None)
            if not app_config.LOG_FILE:
                log.warning("LOG_TO is set to File, but no LOG_FILE was specified. Logging to screen instead.")
                app_config.LOG_TO_FILE = False
    
    # --- Validate and load Site sections ---
    seen_accounts = {}
    site_sections = [s for s in config.sections() if s not in ['SIA-Server', 'IP-Check', 'Logging', 'DEFAULT']]

    for site_name in site_sections:
        if not config.has_option(site_name, 'account'):
            log.warning("Site section [%s] is missing 'ACCOUNT' number. Skipping.", site_name)
            continue
            
        account = config.get(site_name, 'account')
        if account in seen_accounts:
            log.critical("Duplicate ACCOUNT number '%s' found in sections [%s] and [%s]. Please correct sia-server.conf.",
                         account, site_name, seen_accounts[account])
            sys.exit(1)
        seen_accounts[account] = site_name
        
        # Build ACCOUNT_SITES map
        app_config.ACCOUNT_SITES[account] = site_name
        
        # Build NTFY_TOPICS map
        if config.getboolean(site_name, 'ntfy_enabled', fallback=False):
            topic_config = {}
            topic_config['url'] = config.get(site_name, 'ntfy_topic', fallback=None)
            topic_config['title'] = config.get(site_name, 'ntfy_title', fallback='Galaxy Alarm')
            
            auth_method = config.get(site_name, 'ntfy_auth', fallback='None').lower()
            if auth_method == 'token':
                token = config.get(site_name, 'ntfy_token', fallback=None)
                if token:
                    topic_config['auth'] = {'method': 'token', 'token': token}
                else:
                    log.warning("In section [%s], auth is 'Token' but 'ntfy_token' is missing.", site_name)
            elif auth_method == 'userpass':
                user = config.get(site_name, 'ntfy_user', fallback=None)
                password = config.get(site_name, 'ntfy_pass', fallback=None)
                if user and password:
                    topic_config['auth'] = {'method': 'userpass', 'user': user, 'pass': password}
                else:
                    log.warning("In section [%s], auth is 'Userpass' but user/pass is incomplete.", site_name)
            
            app_config.NTFY_TOPICS[account] = topic_config

    # Handle the [Default] section for unknown accounts
    if config.has_section('Default'):
        if config.getboolean('Default', 'ntfy_enabled', fallback=False):
            app_config.NTFY_TOPICS['default'] = {
                'url': config.get('Default', 'ntfy_topic', fallback=None),
                'title': config.get('Default', 'ntfy_title', fallback='Galaxy Alarm'),
                'auth': None # Assuming default is always public
            }

    log.info("Configuration loaded and validated successfully.")
    return app_config
