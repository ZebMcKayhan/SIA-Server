"""
Galaxy SIA Notification Provider - Pushover

Sends notifications via the Pushover notification service.
Requires a Pushover account with an application token and user key.

--- Setting up Pushover ---

1. Create an account at https://pushover.net
2. Note your User Key from the dashboard
3. Create a new Application at https://pushover.net/apps/build
4. Note the Application API Token
5. Install the Pushover app on your phone (Android/iOS)

For more information see: https://pushover.net/api

--- Priority Mapping ---

SIA priorities are mapped to Pushover priorities as follows:

  SIA 1 (lowest)  → Pushover -2 (no notification, stored only)
  SIA 2 (low)     → Pushover -1 (quiet, no sound/vibration)
  SIA 3 (normal)  → Pushover  0 (normal notification)
  SIA 4 (high)    → Pushover  1 (high priority, bypasses quiet hours)
  SIA 5 (urgent)  → Pushover  2 (emergency, repeats until acknowledged)

Note: Pushover Emergency priority (SIA 5) requires PUSHOVER_RETRY and
PUSHOVER_EXPIRE to be set. The notification will repeat every RETRY seconds
until acknowledged or EXPIRE seconds have passed.

--- Available sounds ---
pushover, bike, bugle, cashregister, classical, cosmic, falling, gamelan, 
incoming, intermission, magic, mechanical, pianobar, siren, spacealarm, tugboat, 
alien, climb, persistent, echo, updown, vibrate, none.

--- Configuration keys in sia-server.conf account section ---

  PUSHOVER_TOKEN   = your_app_token    (required)
  PUSHOVER_USER    = your_user_key     (required)
  PUSHOVER_TITLE   = Galaxy Alarm      (optional, default: 'Galaxy Alarm')
  PUSHOVER_SOUND   = siren             (optional, default: pushover default sound)
  PUSHOVER_RETRY   = 30                (optional, seconds between retries for SIA priority 5, min 30)
  PUSHOVER_EXPIRE  = 3600              (optional, seconds until emergency stops retrying, max 10800)
  PUSHOVER_DEVICE  =                   (optional, send to specific device only)
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

PUSHOVER_API_URL = 'https://api.pushover.net/1/messages.json'

# Map SIA priorities (1-5) to Pushover priorities (-2 to 2)
PRIORITY_MAP = {
    1: -2,
    2: -1,
    3:  0,
    4:  1,
    5:  2,
}

DEFAULT_RETRY  = 30    # seconds between emergency retries (minimum 30)
DEFAULT_EXPIRE = 3600  # seconds until emergency stops retrying (maximum 10800)


class PushoverProvider(NotificationProvider):
    """
    Notification provider for Pushover.
    Sends notifications via the Pushover HTTP API.
    """

    provider_name = 'pushover'

    def __init__(self, site_name: str, token: str, user: str,
                 title: str, sound: str, retry: int, expire: int,
                 device: str):
        self._site_name = site_name
        self._token     = token
        self._user      = user
        self._title     = title
        self._sound     = sound
        self._retry     = retry
        self._expire    = expire
        self._device    = device

    @classmethod
    def from_config(cls, account_number: str, provider_config: dict) -> 'PushoverProvider':
        """
        Validate Pushover configuration and return a PushoverProvider instance.
        Raises ValueError if configuration is invalid or incomplete.
        """
        # --- Token ---
        token = provider_config.get('pushover_token')
        if not token:
            raise ValueError(f"[{account_number}] PUSHOVER_TOKEN is required but missing.")

        # --- User key ---
        user = provider_config.get('pushover_user')
        if not user:
            raise ValueError(f"[{account_number}] PUSHOVER_USER is required but missing.")

        # --- Title ---
        title = provider_config.get('pushover_title', 'Galaxy Alarm')

        # --- Sound ---
        sound = provider_config.get('pushover_sound', '')

        # --- Retry (for emergency priority) ---
        try:
            retry = int(provider_config.get('pushover_retry', DEFAULT_RETRY))
            if retry < 30:
                log.warning("[%s] PUSHOVER_RETRY must be at least 30 seconds. Using 30.",
                            account_number)
                retry = 30
        except ValueError:
            log.warning("[%s] Invalid PUSHOVER_RETRY value. Using default %d.",
                        account_number, DEFAULT_RETRY)
            retry = DEFAULT_RETRY

        # --- Expire (for emergency priority) ---
        try:
            expire = int(provider_config.get('pushover_expire', DEFAULT_EXPIRE))
            if expire > 10800:
                log.warning("[%s] PUSHOVER_EXPIRE must be at most 10800 seconds. Using 10800.",
                            account_number)
                expire = 10800
        except ValueError:
            log.warning("[%s] Invalid PUSHOVER_EXPIRE value. Using default %d.",
                        account_number, DEFAULT_EXPIRE)
            expire = DEFAULT_EXPIRE

        # --- Device (optional) ---
        device = provider_config.get('pushover_device', '')

        # --- Site name ---
        site_name = provider_config.get('site_name')

        log.debug("Pushover provider configured for account '%s'.", account_number)

        return cls(site_name, token, user, title, sound, retry, expire, device)

    def send(self, account: str, message: str, priority: int) -> bool | None:
        """
        Send a notification via the Pushover API.

        Returns:
            True  - sent successfully
            False - delivery failed, will be retried
            None  - should not happen (config validated in from_config)
        """
        # Use configured site_name for display if available, otherwise account number
        display_name = self._site_name if self._site_name else account
        full_title   = f"{self._title}: {display_name}"

        # Map SIA priority to Pushover priority
        pushover_priority = PRIORITY_MAP.get(priority, 0)

        payload = {
            'token':    self._token,
            'user':     self._user,
            'message':  message,
            'title':    full_title,
            'priority': pushover_priority,
        }

        # Add sound if configured
        if self._sound:
            payload['sound'] = self._sound

        # Add device if configured
        if self._device:
            payload['device'] = self._device

        # Emergency priority requires retry and expire
        if pushover_priority == 2:
            payload['retry']  = self._retry
            payload['expire'] = self._expire

        log.debug("Sending Pushover notification (priority %d → Pushover %d) to user %s: %s",
                  priority, pushover_priority, self._user, message)
        log.info("Sending Pushover notification (priority %d) for account %s: %s",
                 priority, account, message)

        try:
            response = requests.post(
                PUSHOVER_API_URL,
                data=payload,
                timeout=10
            )
            response.raise_for_status()

            result = response.json()
            if result.get('status') != 1:
                log.error("Pushover API error for account %s: %s",
                          account, result.get('errors', 'Unknown error'))
                return False

            log.debug("Pushover dispatch successful for account %s.", account)
            return True

        except requests.exceptions.Timeout:
            log.error("Pushover notification failed for account %s: request timed out.", account)
            return False

        except requests.exceptions.RequestException as e:
            log.error("Pushover dispatch failed for account %s: %s", account, e)
            return False

    @property
    def name(self) -> str:
        return 'pushover'
