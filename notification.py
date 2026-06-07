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
import sys
import time
from typing import Dict, Optional, Union
from queue import Queue, Full as QueueFull, Empty
from threading import Thread, Event as ThreadEvent

from configuration import AccountsConfig
from galaxy.parser import GalaxyEvent
from providers.base import NotificationProvider

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
        self.event_description = message
        self.time              = None
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

def get_event_priority(event_code: str, priority_map: Dict, default_priority: int) -> int:
    """Gets the notification priority for a given event code from the defaults map."""
    return priority_map.get(event_code, default_priority)


def format_notification_text(event: Union[GalaxyEvent, MessageEvent]) -> str:
    """
    Formats the notification message text.
    For MessageEvent, uses action_text directly.
    For GalaxyEvent, intelligently chooses between the rich ASCII block text
    or constructs a message from the Data block fields.
    """
    if isinstance(event, MessageEvent):
        return event.action_text

    event_time = event.time or "??"

    if event.action_text:
        notification = f"{event_time} {event.action_text}"
        # The Zone address is the RIO address, which name is already in the ASCII block.
        # This was not what I intended, commenting this until I figure out what to do:
        #if event.zone and event.zone not in str(event.action_text):
        #    notification += f" (Zone {event.zone})"
    else:
        notification = f"{event_time}"
        if event.event_code:
            notification += f" Event: {event.event_code} ({event.event_description})"
        if event.user_id:
            notification += f" User: {event.user_id}"
        if event.zone:
            notification += f" Zone: {event.zone}"
        if event.group:
            notification += f" Group: {event.group}"
        if event.peripheral:
            notification += f" Peripheral: {event.peripheral}"
        if event.value:
            notification += f" Value: {event.value}"

    return notification.strip()


# ===================================================================
# Dispatch
# ===================================================================

def _dispatch_notification(event: Union[GalaxyEvent, MessageEvent],
                            provider_cache: Dict[str, Optional[NotificationProvider]],
                            priority_map: Dict,
                            default_priority: int) -> bool | None:
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

    message = format_notification_text(event)

    # Build display name for logging - site_name if available, otherwise just account number
    site_name = getattr(event, 'site_name', None)
    if site_name and site_name != event.account:
        display = f"{site_name} ({event.account})"
    else:
        display = f"{event.account}"

    log.info("Sending notification (priority %d) via %s for %s: %s",
             priority, provider.name, display, message)

    return provider.send(event.account, message, priority)


# ===================================================================
# Queue helpers
# ===================================================================

def _enqueue(event: Union[GalaxyEvent, MessageEvent], queue: Queue):
    """
    Internal helper to add any event type to the notification queue.
    If the queue is full, removes the oldest item to make space.
    """
    if queue.full():
        try:
            oldest_event, _, _ = queue.get_nowait()
            log.warning("Notification queue is full. Dropping the oldest event to make space.")
            queue.task_done()
        except Empty:
            pass

    try:
        queue.put_nowait((event, 0, 0))
        log.debug("Event for account %s added to notification queue.", event.account)
    except QueueFull:
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
                 default_priority: int, max_retries: int, max_retry_time: int):
        super().__init__(daemon=True)
        self.name              = "NotificationDispatcher"
        self.queue             = queue
        self.accounts          = accounts
        self.priority_map      = priority_map
        self.default_priority  = default_priority
        self.max_retries       = max_retries
        self.max_retry_time_minutes = max_retry_time
        self.shutdown_event    = ThreadEvent()
        self._provider_cache: Dict[str, Optional[NotificationProvider]] = {}

    def start(self):
        """Discover providers and build cache before starting the thread."""
        registry = _discover_providers()
        self._provider_cache = _build_provider_cache(self.accounts, registry)
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

    def run(self):
        log.info("NotificationDispatcher thread started.")
        while not self.shutdown_event.is_set():
            event, retry_count, next_attempt_time = self.queue.get()
            if not event:
                self.queue.task_done()
                break

            current_time = time.time()

            if current_time < next_attempt_time:
                self.queue.put((event, retry_count, next_attempt_time))
                self.queue.task_done()
                time.sleep(1.0)
                continue

            success = _dispatch_notification(
                event, self._provider_cache, self.priority_map, self.default_priority
            )

            if success is None:
                log.debug("Notification skipped for account %s.", event.account)
            elif not success:
                retry_count += 1
                if self.max_retries == 0 or retry_count <= self.max_retries:
                    delay = self.get_retry_delay(retry_count)
                    new_next_attempt_time = time.time() + delay
                    log.warning("Dispatch failed for account %s. Re-queueing for retry in %d mins (attempt %d).",
                                event.account, delay // 60, retry_count)
                    try:
                        self.queue.put_nowait((event, retry_count, new_next_attempt_time))
                    except QueueFull:
                        log.error("Queue is full. Cannot re-queue failed notification for %s.", event.account)
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
