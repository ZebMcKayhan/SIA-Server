"""
Galaxy SIA Notification Provider - Telegram

Sends notifications via the Telegram Bot API.
Supports standard Telegram and self-hosted Telegram Bot API servers.

Configuration keys in sia-server.conf account section:
  TELEGRAM_TOKEN   = 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ  (required)
  TELEGRAM_CHAT_ID = 987654321                              (required)
  TELEGRAM_TITLE   = Galaxy Alarm                           (optional, default: 'Galaxy Alarm')
  TELEGRAM_API_URL = https://api.telegram.org               (optional, default: standard Telegram API)
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

# Priority to emoji mapping
PRIORITY_EMOJI = {
    1: 'ℹ️',
    2: 'ℹ️',
    3: '🔔',
    4: '⚠️',
    5: '🚨',
}

DEFAULT_API_URL = 'https://api.telegram.org'


class TelegramProvider(NotificationProvider):
    """
    Notification provider for Telegram.
    Sends messages via the Telegram Bot API.
    """

    provider_name = 'telegram'

    def __init__(self, site_name: str, token: str, chat_id: str,
                 title: str, api_url: str):
        self._site_name = site_name
        self._token     = token
        self._chat_id   = chat_id
        self._title     = title
        self._api_url   = api_url.rstrip('/')

    @classmethod
    def from_config(cls, account_number: str, provider_config: dict) -> 'TelegramProvider':
        """
        Validate Telegram configuration and return a TelegramProvider instance.
        Raises ValueError if configuration is invalid or incomplete.
        """
        # --- Token ---
        token = provider_config.get('telegram_token')
        if not token:
            raise ValueError(f"[{account_number}] TELEGRAM_TOKEN is required but missing.")

        # --- Chat ID ---
        chat_id = provider_config.get('telegram_chat_id')
        if not chat_id:
            raise ValueError(f"[{account_number}] TELEGRAM_CHAT_ID is required but missing.")

        # --- Title ---
        title = provider_config.get('telegram_title', 'Galaxy Alarm')

        # --- API URL ---
        api_url = provider_config.get('telegram_api_url', DEFAULT_API_URL)

        # --- Site name ---
        # None if not configured - send() will use account number as fallback
        site_name = provider_config.get('site_name')

        log.debug("Telegram provider configured for account '%s' (chat_id=%s, api_url=%s)",
                  account_number, chat_id, api_url)

        return cls(site_name, token, chat_id, title, api_url)

    def send(self, account: str, message: str, priority: int) -> bool | None:
        """
        Send a notification via the Telegram Bot API.

        Returns:
            True  - sent successfully
            False - delivery failed, will be retried
            None  - should not happen for Telegram (config validated in from_config)
        """
        # Use configured site_name for display if available, otherwise account number
        display_name = self._site_name if self._site_name else account

        # Build title line and message with priority emoji
        emoji = PRIORITY_EMOJI.get(priority, '🔔')
        full_message = f"{self._title}: {display_name}\n{emoji} {message}"

        url = f"{self._api_url}/bot{self._token}/sendMessage"

        log.debug("Sending Telegram notification (priority %d) to chat %s: %s",
                  priority, self._chat_id, message)
        log.info("Sending Telegram notification (priority %d) for account %s: %s",
                 priority, account, message)

        try:
            response = requests.post(
                url,
                json={
                    'chat_id':    self._chat_id,
                    'text':       full_message,
                },
                timeout=10
            )
            response.raise_for_status()
            log.debug("Telegram dispatch successful for account %s.", account)
            return True

        except requests.exceptions.Timeout:
            log.error("Telegram notification failed for account %s: request timed out.", account)
            return False

        except requests.exceptions.RequestException as e:
            log.error("Telegram dispatch failed for account %s: %s", account, e)
            return False

    @property
    def name(self) -> str:
        return 'telegram'
