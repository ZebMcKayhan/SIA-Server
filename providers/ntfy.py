"""
Galaxy SIA Notification Provider - ntfy.sh

Sends notifications via ntfy.sh or a self-hosted ntfy server.
Supports public topics, token authentication and username/password authentication.

Configuration keys in sia-server.conf account section:
  NTFY_TOPIC   = https://ntfy.sh/your-topic    (required, but could be to a private server)
  NTFY_TITLE   = My Alarm                      (optional, default: 'Galaxy Alarm')
  NTFY_AUTH    = None | Token | Userpass       (optional, default: None)
  NTFY_TOKEN   = tk_yourtoken                  (required if NTFY_AUTH = Token)
  NTFY_USER    = username                      (required if NTFY_AUTH = Userpass)
  NTFY_PASS    = password                      (required if NTFY_AUTH = Userpass)
"""

import logging
import sys

from providers.base import NotificationProvider

log = logging.getLogger(__name__)

# --- CRITICAL: Check for 'requests' library ---
try:
    import requests
except ImportError:
    log.critical("="*60)
    log.critical("FATAL ERROR: The 'requests' library is not installed.")
    log.critical("This library is required to send notifications.")
    if sys.platform == "win32":
        log.critical("Please install it by running: python -m pip install requests")
    else:
        log.critical("Please install it by running: sudo apt install python3-requests")
    log.critical("="*60)
    raise


class NtfyProvider(NotificationProvider):
    """
    Notification provider for ntfy.sh.
    Sends HTTP POST requests to a ntfy topic URL.
    """

    provider_name = 'ntfy'

    def __init__(self, site_name: str, url: str, title: str,
                 auth_method: str, auth_details: dict):
        self._site_name      = site_name
        self._url            = url
        self._title          = title
        self._auth_method    = auth_method
        self._auth_details   = auth_details

    @classmethod
    def from_config(cls, account_number: str, provider_config: dict) -> 'NtfyProvider':
        """
        Validate ntfy configuration and return a NtfyProvider instance.
        Raises ValueError if configuration is invalid or incomplete.
        """
        # --- URL ---
        url = provider_config.get('ntfy_topic')
        if not url:
            raise ValueError(f"[{account_number}] NTFY_TOPIC is required but missing.")
        if 'your-topic-here' in url or 'your-public-topic' in url or 'your-private' in url:
            raise ValueError(f"[{account_number}] NTFY_TOPIC appears to be a placeholder value.")

        # --- Title ---
        title = provider_config.get('ntfy_title', 'Galaxy Alarm')

        # --- Site name ---
        # Site name - None if not configured, account number used as fallback in send()
        site_name = provider_config.get('site_name')

        # --- Authentication ---
        auth_method  = provider_config.get('ntfy_auth', 'none').lower()
        auth_details = {}

        if auth_method == 'token':
            token = provider_config.get('ntfy_token')
            if not token:
                raise ValueError(
                    f"[{account_number}] NTFY_AUTH = Token but NTFY_TOKEN is missing.")
            auth_details['token'] = token

        elif auth_method == 'userpass':
            user     = provider_config.get('ntfy_user')
            password = provider_config.get('ntfy_pass')
            if not user or not password:
                raise ValueError(
                    f"[{account_number}] NTFY_AUTH = Userpass but NTFY_USER or NTFY_PASS is missing.")
            auth_details['user']     = user
            auth_details['password'] = password

        elif auth_method not in ('none', 'no', ''):
            log.warning("[%s] Unknown NTFY_AUTH value '%s', treating as no auth.",
                        account_number, auth_method)
            auth_method = 'none'

        log.debug("ntfy provider configured for account '%s' (url=%s, auth=%s)",
                  account_number, url, auth_method)

        return cls(site_name, url, title, auth_method, auth_details)

    def send(self, account: str, message: str, priority: int) -> bool | None:
        """
        Send a notification via ntfy.sh HTTP POST.

        Returns:
            True  - sent successfully
            False - delivery failed, will be retried
            None  - should not happen for ntfy (config validated in from_config)
        """
        # Use configured site_name for display if available, otherwise account number
        display_name = self._site_name if self._site_name else account
        full_title = f"{self._title}: {display_name}"

        headers = {
            'Title':    full_title,
            'Priority': str(priority),
        }

        auth = None

        if self._auth_method == 'token':
            headers['Authorization'] = f"Bearer {self._auth_details['token']}"
            log.debug("Using Bearer token authentication.")

        elif self._auth_method == 'userpass':
            auth = (self._auth_details['user'], self._auth_details['password'])
            log.debug("Using username/password authentication.")

        display = f"{self._site_name} ({account})" if self._site_name else account
        log.debug("Sending ntfy notification (priority %d) to %s: %s",
                  priority, self._url, message)
        log.info("Sending ntfy notification (priority %d) for %s: %s",
                 priority, display, message)

        try:
            response = requests.post(
                self._url,
                data=message.encode('utf-8'),
                headers=headers,
                timeout=10,
                auth=auth
            )
            response.raise_for_status()
            log.debug("ntfy dispatch successful for account %s.", account)
            return True

        except requests.exceptions.Timeout:
            log.error("ntfy notification failed for account %s: request timed out.", account)
            return False

        except requests.exceptions.RequestException as e:
            log.error("ntfy dispatch failed for account %s: %s", account, e)
            return False

    @property
    def name(self) -> str:
        return 'ntfy'
