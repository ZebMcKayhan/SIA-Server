"""
Galaxy SIA Notification Handler

This module is responsible for:
  - Formatting notification text from SIA events
  - Managing the notification queue and retry logic
  - Discovering and loading provider plugins from providers/
  - Routing notifications to the correct provider per account

Provider plugins are auto-discovered from the providers/ directory.
Each plugin must subclass providers.base.NotificationProvider and define
a class attribute 'provider_name'.

Backwards compatibility:
  NTFY_ENABLED = Yes   is treated as PROVIDER = ntfy
  NTFY_ENABLED = No    is treated as PROVIDER = none (notifications disabled)
"""

import importlib
import logging
import pkgutil
import re
import sys
import time
from typing import Dict, Optional, Union
from queue import Queue, Full as QueueFull, Empty
from threading import Thread, Event as ThreadEvent

from configuration import AccountsConfig
from galaxy.parser import GalaxyEvent
from providers.base import NotificationProvider
from galaxy.constants import EVENT_CODE_DESCRIPTIONS

# --- Dependency and Logging Initialization ---
log = logging.getLogger(__name__)

# --- Force PyOpenSSL to be used by requests (if available) ---
try:
    import urllib3.contrib.pyopenssl
    urllib3.contrib.pyopenssl.inject_into_urllib3()
    log.info("Successfully injected PyOpenSSL into urllib3 for robust HTTPS.")
except ImportError:
    if sys.platform == "win32":
        log.warning("PyOpenSSL not found. HTTPS notifications may fail on Windows without it.")
        log.warning("If you get HTTPS SSL problems, please run: python -m pip install pyopenssl")
    else:
        log.info("PyOpenSSL not available; using default system SSL context.")


class MessageEvent:
    """
    Represents a generic notification message.
    Used when any part of the system wants to send a custom notification
    that is not tied to a specific SIA alarm event.
    Examples: watchdog heartbeat alerts, server status messages, etc.
    Priority is fixed by the caller rather than derived from event codes.
    """
    def __init__(self, account: str, site_name: str,
                 message: str, priority: int):
        self.account           = account
        self.site_name         = site_name
        self.action_text       = message
        self.priority          = priority
        self.event_code        = 'MSG'
        self.event_description = EVENT_CODE_DESCRIPTIONS.get('MSG', 'Server Message')
        self.time              = time.strftime('%H:%M')  # server local time
        self.zone              = None
        self.peripheral        = None
        self.user_id           = None


# ===================================================================
# Provider Discovery
# ===================================================================

def _get_all_subclasses(cls):
    """Recursively find all subclasses of a class."""
    result = {}
    for subclass in cls.__subclasses__():
        if hasattr(subclass, 'provider_name'):
            result[subclass.provider_name] = subclass
        result.update(_get_all_subclasses(subclass))
    return result


def _discover_providers() -> Dict[str, type]:
    """
    Auto-discover all provider plugins in the providers/ directory.
    Imports each module and collects all NotificationProvider subclasses.
    Returns a dict mapping provider_name -> provider class.
    """
    import providers

    for finder, name, ispkg in pkgutil.iter_modules(providers.__path__):
        if name == 'base':
            continue
        try:
            importlib.import_module(f'providers.{name}')
            log.debug("Loaded provider plugin: %s", name)
        except Exception as e:
            log.warning("Failed to load provider plugin '%s': %s", name, e)

    registry = {}
    for provider_name, cls in _get_all_subclasses(NotificationProvider).items():
        if provider_name in registry:
            log.warning("Provider name conflict: '%s' registered by both %s and %s. "
                        "Using %s.", provider_name, registry[provider_name], cls, cls)
        registry[provider_name] = cls
        log.info("Registered notification provider: '%s'", provider_name)

    return registry


# ===================================================================
# Provider instantiation per account
# ===================================================================

def _get_provider_name(provider_config: dict) -> Optional[str]:
    """
    Determine which provider to use for an account.

    Checks for PROVIDER key first, then falls back to
    NTFY_ENABLED for backwards compatibility.
    """
    # New style: explicit PROVIDER key
    provider = provider_config.get('provider', '').lower().strip()
    if provider and provider != 'none':
        return provider

    # Backwards compatibility: NTFY_ENABLED = Yes → ntfy
    ntfy_enabled = provider_config.get('ntfy_enabled', 'no').lower()
    if ntfy_enabled in ('yes', 'true'):
        log.debug("NTFY_ENABLED detected - using 'ntfy' provider. "
                  "Consider switching to PROVIDER = ntfy.")
        return 'ntfy'

    return None


def _build_provider_cache(accounts: AccountsConfig,
                           registry: Dict[str, type]) -> Dict[str, Optional[NotificationProvider]]:
    """
    Build a cache of provider instances per account.
    Called once at startup - validates all account configs early.
    Returns dict mapping account_number -> provider instance (or None if disabled).
    """
    cache = {}
    for account_number, account_config in accounts.accounts.items():
        provider_name = _get_provider_name(account_config.provider_config)

        if provider_name is None:
            log.debug("Account '%s': no notification provider configured.", account_number)
            cache[account_number] = None
            continue

        if provider_name not in registry:
            log.warning("Account '%s': unknown provider '%s'. "
                        "Notifications disabled for this account.",
                        account_number, provider_name)
            cache[account_number] = None
            continue

        try:
            provider = registry[provider_name].from_config(
                account_number, account_config.provider_config)
            log.info("Account '%s': using provider '%s'.", account_number, provider_name)
            cache[account_number] = provider
        except ValueError as e:
            log.warning("Account '%s': provider configuration error - %s. "
                        "Notifications disabled for this account.", account_number, e)
            cache[account_number] = None

    return cache
  
# ===================================================================
# Notification formatting
# ===================================================================
def has_value(event, field):
    return getattr(event, field, None) is not None
  
  
def get_event_priority(event_code: str, priority_map: Dict, default_priority: int) -> int:
    """Gets the notification priority for a given event code from the defaults map."""
    return priority_map.get(event_code, default_priority)


def format_notification_text(event: Union[GalaxyEvent, MessageEvent],
                             notification_format_ascii: str,
                             notification_format_data: str
                             ) -> str:
    r"""
    Formats the notification message according to the configured format.

    Format syntax:
      %field          Replaced with the corresponding GalaxyEvent attribute.
      [ ... ]         Optional section; omitted if any referenced field is missing.
      \n              Replaced with a newline character.

    For GalaxyEvent, the ASCII format is used when action_text is available,
    otherwise the data format is used.
    """
    if isinstance(event, MessageEvent):
        return event.action_text

    if event.action_text:
        template = notification_format_ascii
    else:
        template = notification_format_data

    # Process optional sections first.
    # A section is included only if all fields referenced within it have a value.
    def render_optional(match: re.Match) -> str:
        section = match.group(1)

        fields = re.findall(r"%([a-zA-Z_][a-zA-Z0-9_]*)", section)

        if any(not has_value(event, field) for field in fields):
            return ""

        return re.sub(
            r"%([a-zA-Z_][a-zA-Z0-9_]*)",
            lambda m: str(getattr(event, m.group(1), "")),
            section,
        )

    template = re.sub(r"\[([^\[\]]*)\]", render_optional, template)

    # Replace normal %field tokens.
    template = re.sub(
        r"%([a-zA-Z_][a-zA-Z0-9_]*)",
        lambda m: str(getattr(event, m.group(1))) if has_value(event, m.group(1)) else "",
        template,
    )

    # Replace escape sequences with real newlines.
    template = template.replace(r"\r\n", "\n").replace(r"\n", "\n")

    return template


# ===================================================================
# Dispatch
# ===================================================================

def _dispatch_notification(event: Union[GalaxyEvent, MessageEvent],
         provider_cache: Dict[str, Optional[NotificationProvider]],
         priority_map: Dict,
         default_priority: int,
         notification_format_ascii: str,
         notification_format_data: str,
) -> bool | None:
    """
    Dispatch a notification to the appropriate provider for this event's account.

    Returns:
        True  - sent successfully
        False - delivery failed, will be retried
        None  - no provider configured or config issue, skip silently
    """
    # Look up provider - try account first, then default
    # Note: we must distinguish between 'account not in cache' (fall back to default)
    # and 'account in cache but provider is None' (explicitly disabled, no fallback)
    if event.account in provider_cache:
        provider = provider_cache[event.account]
    else:
        provider = provider_cache.get('default')

    if provider is None:
        log.debug("No provider configured for account '%s'. Skipping.", event.account)
        return None

    # Determine priority
    if isinstance(event, MessageEvent):
        priority = event.priority
    else:
        if not event.event_code:
            log.warning("Event has no event_code, cannot determine priority. Skipping.")
            return None
        priority = get_event_priority(event.event_code, priority_map, default_priority)

    message = format_notification_text(event, notification_format_ascii,
                                      notification_format_data)

    # Build display name for logging - site_name if available, otherwise just account number
    site_name = getattr(event, 'site_name', None)
    if site_name and site_name != event.account:
        display = f"{site_name} ({event.account})"
    else:
        display = f"{event.account}"

    # Send via provider - raw event or formatted message depending on provider type
    if getattr(provider, 'raw_event', False):
        log.debug("Sending raw event (priority %d) via %s for %s: %s",
                  priority, provider.name, display, message)
        return provider.send(event.account, event, priority)
    else:
        log.debug("Sending notification (priority %d) via %s for %s: %s",
                  priority, provider.name, display, message)
        return provider.send(event.account, message, priority)


# ===================================================================
# Queue helpers
# ===================================================================

def _enqueue(event: Union[GalaxyEvent, MessageEvent], queue: Queue):
    """
    Internal helper to add any event type to the notification queue.
    If the queue is full, evicts the oldest item to make space.
    Retries up to 3 times to handle concurrent queue activity.
    """
    for _ in range(3):
        try:
            queue.put_nowait((event, 0, 0))
            log.debug("Event for account %s added to notification queue.", event.account)
            return
        except QueueFull:
            try:
                dropped, _, _ = queue.get_nowait()
                queue.task_done()
                log.warning("Notification queue full. Dropped oldest event (account %s) "
                            "to make room for new event (account %s).",
                            getattr(dropped, 'account', '?'), event.account)
            except Empty:
                pass
    log.error("Notification queue is still full! Event for %s was lost.", event.account)


# ===================================================================
# Dispatcher thread
# ===================================================================

class NotificationDispatcher(Thread):
    """
    A non-blocking background thread that processes a queue of notifications.
    It handles sending and retries with progressive backoff without blocking the queue.
    Supports both GalaxyEvent (SIA events) and MessageEvent (custom notifications).
    """
    def __init__(self, queue: Queue, accounts: AccountsConfig, priority_map: Dict,
                 default_priority: int, max_retries: int, max_retry_time: int,
                 notification_format_ascii: str, notification_format_data: str):
        super().__init__(daemon=True)
        self.name              = "NotificationDispatcher"
        self.queue             = queue
        self.accounts          = accounts
        self.priority_map      = priority_map
        self.default_priority  = default_priority
        self.max_retries       = max_retries
        self.max_retry_time_minutes = max_retry_time
        self.notification_format_ascii = notification_format_ascii
        self.notification_format_data  = notification_format_data                   
        self.shutdown_event    = ThreadEvent()
        self._provider_cache: Dict[str, Optional[NotificationProvider]] = {}

    def start(self):
        """Discover providers and build cache before starting the thread."""
        self._registry = _discover_providers()
        self._provider_cache = _build_provider_cache(self.accounts, self._registry)
        super().start()

    def get_retry_delay(self, retry_count: int) -> int:
        """
        Calculates the retry delay using progressive exponential backoff.
        The delay doubles with each retry, up to the configured maximum.
        """
        base_delay    = 1
        current_delay = base_delay * (2 ** (retry_count - 1))
        final_delay   = min(current_delay, self.max_retry_time_minutes)
        return final_delay * 60

    def reload_accounts(self, new_accounts: AccountsConfig):
        """
        Reload account configuration and rebuild the provider cache.
        Called on SIGHUP to pick up account changes without restarting.
        Providers are not re-discovered — only the per-account cache is rebuilt.
        """
        log.info("Reloading account configuration...")
        old_count = len(self.accounts.accounts)
        self.accounts = new_accounts
        self._provider_cache = _build_provider_cache(self.accounts, self._registry)
        new_count = len(self.accounts.accounts)
        log.info("Account configuration reloaded. Accounts: %d → %d.", old_count, new_count)
    
    def run(self):
        log.info("NotificationDispatcher thread started.")
        pending_retries = []  # items not yet due: list of (event, retry_count, next_attempt_time)
        while not self.shutdown_event.is_set():
            # Re-inject any retries that have become due. Keeping them in a
            # local list (instead of cycling them through the queue) avoids
            # a 1-second busy loop and never delays fresh events behind waiting retries.
            now = time.time()
            due = [item for item in pending_retries if item[2] <= now]
            for item in due:
                pending_retries.remove(item)
                try:
                    self.queue.put_nowait(item)
                except QueueFull:
                    log.error("Queue full. Dropping due retry for account %s.",
                              getattr(item[0], 'account', '?'))

            try:
                event, retry_count, next_attempt_time = self.queue.get(timeout=1.0)
            except Empty:
                continue

            if not event:  # Shutdown signal
                self.queue.task_done()
                break

            if time.time() < next_attempt_time:
                # Not due yet - park it locally and move on
                pending_retries.append((event, retry_count, next_attempt_time))
                self.queue.task_done()
                continue

            success = _dispatch_notification(event, self._provider_cache, self.priority_map,
                                 self.default_priority, self.notification_format_ascii,
                                self.notification_format_data)

            if success is None:
                log.debug("Notification skipped for account %s.", event.account)
            elif not success:
                retry_count += 1
                if self.max_retries == 0 or retry_count <= self.max_retries:
                    delay = self.get_retry_delay(retry_count)
                    new_next_attempt_time = time.time() + delay
                    log.warning("Dispatch failed for account %s. Re-queueing for retry in %d mins (attempt %d).",
                                event.account, delay // 60, retry_count)
                    pending_retries.append((event, retry_count, new_next_attempt_time))
                else:
                    log.error("Dispatch failed for account %s after %d retries. Giving up.",
                              event.account, self.max_retries)

            self.queue.task_done()
        log.info("NotificationDispatcher thread stopped.")

    def stop(self):
        log.info("Stopping NotificationDispatcher thread...")
        self.shutdown_event.set()
        self.queue.put((None, 0, 0))


# ===================================================================
# Public enqueue functions
# ===================================================================

def enqueue_notification(event: GalaxyEvent, queue: Queue):
    """
    Puts a SIA GalaxyEvent onto the notification queue.
    Called by sia-server.py for alarm events.
    """
    _enqueue(event, queue)


def enqueue_message_notification(account: str, site_name: str,
                                  message: str, priority: int,
                                  queue: Queue):
    """
    Puts a generic message notification onto the notification queue.
    Can be called by any part of the system to send a custom notification.
    Priority is explicitly set by the caller.

    Examples of use:
    - ip_check.py: heartbeat connection lost/restored
    - sia-server.py: server starting/stopping
    - Any future module needing custom notifications
    """
    _enqueue(MessageEvent(account, site_name, message, priority), queue)
