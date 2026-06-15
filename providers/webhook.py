"""
Galaxy SIA Notification Provider - Webhook

Sends the full alarm event as a JSON payload to a configurable webhook URL.
Useful for integrations with Home Assistant, Node-RED, Zapier, or any custom
service that accepts HTTP webhooks.

The complete parsed event is sent as JSON - the receiver decides which fields
to use. Raw protocol bytes are excluded as they are not useful for integrations.

--- Setting up a Webhook ---

Configure your receiving endpoint to accept HTTP POST (or PUT) requests
with a JSON body. The following fields are included in the payload:

  account          - Account number received from the panel
  site_name        - Configured site name (null if not configured)
  time             - Event time (hh:mm)
  user_id          - User ID if present
  peripheral       - Peripheral ID if present
  group            - Group/Area ID if present
  value            - Value if present (e.g. test interval in minutes)
  event_code       - Two-character SIA event code (e.g. 'BA', 'CL')
  event_description - Human-readable event description
  zone             - Zone number if present
  action_text      - Full ASCII block text if present (SIA Level 3)

--- Configuration keys in sia-server.conf account section ---

  WEBHOOK_URL      = https://your-server.com/alarm-hook  (required)
  WEBHOOK_METHOD   = POST | PUT                          (optional, default: POST)
  WEBHOOK_AUTH     = None | Token | Userpass             (optional, default: None)
  WEBHOOK_TOKEN    = ABCDEF123456                        (required if WEBHOOK_AUTH = Token)
  WEBHOOK_USER     = username                            (required if WEBHOOK_AUTH = Userpass)
  WEBHOOK_PASS     = password                            (required if WEBHOOK_AUTH = Userpass)

--- Example payload ---

  {
      "account": "597263",
      "site_name": "My Home",
      "time": "08:00",
      "user_id": null,
      "peripheral": null,
      "group": "1",
      "value": null,
      "event_code": "BA",
      "event_description": "Burglary Alarm",
      "zone": "1011",
      "action_text": "+BURGLARY IR Hallway"
  }
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


class WebhookProvider(NotificationProvider):
    """
    Notification provider that sends the full alarm event as JSON to a webhook URL.
    Supports POST and PUT methods with optional token or userpass authentication.
    """

    provider_name = 'webhook'
    raw_event     = True  # tells notification.py to pass GalaxyEvent instead of formatted text

    def __init__(self, url: str, method: str,
                 auth_method: str, auth_details: dict):
        self._url         = url
        self._method      = method.upper()
        self._auth_method = auth_method
        self._auth_details = auth_details

    @classmethod
    def from_config(cls, account_number: str, provider_config: dict) -> 'WebhookProvider':
        """
        Validate webhook configuration and return a WebhookProvider instance.
        Raises ValueError if configuration is invalid or incomplete.
        """
        # --- URL ---
        url = provider_config.get('webhook_url')
        if not url:
            raise ValueError(f"[{account_number}] WEBHOOK_URL is required but missing.")

        # --- Method ---
        method = provider_config.get('webhook_method', 'POST').upper()
        if method not in ('POST', 'PUT'):
            log.warning("[%s] Unknown WEBHOOK_METHOD '%s', using POST.", account_number, method)
            method = 'POST'

        # --- Authentication ---
        auth_method  = provider_config.get('webhook_auth', 'none').lower()
        auth_details = {}

        if auth_method == 'token':
            token = provider_config.get('webhook_token')
            if not token:
                raise ValueError(
                    f"[{account_number}] WEBHOOK_AUTH = Token but WEBHOOK_TOKEN is missing.")
            auth_details['token'] = token

        elif auth_method == 'userpass':
            user     = provider_config.get('webhook_user')
            password = provider_config.get('webhook_pass')
            if not user or not password:
                raise ValueError(
                    f"[{account_number}] WEBHOOK_AUTH = Userpass but WEBHOOK_USER or WEBHOOK_PASS is missing.")
            auth_details['user']     = user
            auth_details['password'] = password

        elif auth_method not in ('none', 'no', ''):
            log.warning("[%s] Unknown WEBHOOK_AUTH value '%s', treating as no auth.",
                        account_number, auth_method)
            auth_method = 'none'

        log.debug("Webhook provider configured for account '%s' (url=%s, method=%s, auth=%s)",
                  account_number, url, method, auth_method)

        return cls(url, method, auth_method, auth_details)

    def _event_to_dict(self, account: str, event) -> dict:
        """Serialize event to JSON-safe dict, excluding raw payload bytes."""
        return {
            'account':           account,
            'site_name':         event.site_name,
            'time':              event.time,
            'user_id':           event.user_id,
            'peripheral':        event.peripheral,
            'group':             event.group,
            'value':             event.value,
            'event_code':        event.event_code,
            'event_description': event.event_description,
            'zone':              event.zone,
            'action_text':       event.action_text,
        }

    def send(self, account: str, event, priority: int) -> bool | None:
        """
        Send the full alarm event as JSON to the configured webhook URL.

        Args:
            account:  The account number received from the panel.
            event:    The GalaxyEvent or MessageEvent object.
            priority: Integer priority 1-5.

        Returns:
            True  - sent successfully
            False - delivery failed, will be retried
            None  - should not happen (config validated in from_config)
        """
        payload = self._event_to_dict(account, event)
        payload['priority'] = priority

        headers = {
            'Content-Type': 'application/json',
        }

        auth = None

        if self._auth_method == 'token':
            headers['Authorization'] = f"Bearer {self._auth_details['token']}"
            log.debug("Using Bearer token authentication.")

        elif self._auth_method == 'userpass':
            auth = (self._auth_details['user'], self._auth_details['password'])
            log.debug("Using username/password authentication.")

        log.debug("Sending webhook (priority %d) to %s: %s",
                  priority, self._url, payload)
        log.info("Sending webhook notification (priority %d) for account %s.",
                 priority, account)

        try:
            response = requests.request(
                self._method,
                self._url,
                json=payload,
                headers=headers,
                timeout=10,
                auth=auth
            )
            response.raise_for_status()
            log.debug("Webhook dispatch successful for account %s.", account)
            return True

        except requests.exceptions.Timeout:
            log.error("Webhook notification failed for account %s: request timed out.", account)
            return False

        except requests.exceptions.RequestException as e:
            log.error("Webhook dispatch failed for account %s: %s", account, e)
            return False

    @property
    def name(self) -> str:
        return 'webhook'
