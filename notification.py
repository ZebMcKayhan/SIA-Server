"""
Galaxy SIA Notification Handler

This module is responsible for formatting and sending notifications
to a service like ntfy.sh based on a parsed GalaxyEvent.
"""

import logging
import sys
import time
from typing import Dict
from queue import Queue, Full as QueueFull, Empty
from threading import Thread, Event as ThreadEvent
from galaxy.parser import GalaxyEvent

# --- Dependency and Logging Initialization ---

# Apply a basic config immediately so startup messages are always captured.
# This will be overridden by the main server's full logging setup later.
logging.basicConfig()
log_pyopenssl = logging.getLogger(__name__)

# --- CRITICAL: Check for 'requests' library ---
try:
    import requests
except ImportError:
    log_pyopenssl.critical("="*60)
    log_pyopenssl.critical("FATAL ERROR: The 'requests' library is not installed.")
    log_pyopenssl.critical("This library is required to send notifications.")
    if sys.platform == "win32":
        log_pyopenssl.critical("Please install it by running: python -m pip install requests pyopenssl cryptography ndg-httpsclient")
    else: # Assume Linux/macOS
        log_pyopenssl.critical("Please install it by running: sudo apt install python3-requests")
    log_pyopenssl.critical("="*60)
    sys.exit(1) # Exit the entire application immediately.

# --- Force PyOpenSSL to be used by requests (if available) ---
try:
    import urllib3.contrib.pyopenssl
    urllib3.contrib.pyopenssl.inject_into_urllib3()
    log_pyopenssl.info("Successfully injected PyOpenSSL into urllib3 for robust HTTPS.")
except ImportError:
    # On Windows, this may be a problem:
    if sys.platform == "win32":
        log_pyopenssl.warning("PyOpenSSL not found. HTTPS notifications may fail on Windows without it.")
        log_pyopenssl.warning("Please run: python -m pip install pyopenssl cryptography ndg-httpsclient")
    # On Linux, it's normal:
    else:
        log_pyopenssl.info("PyOpenSSL not available; using default system SSL context.")

log = logging.getLogger(__name__)


def get_event_priority(event_code: str, priority_map: Dict, default_priority: int) -> int:
    """Gets the notification priority for a given event code from the defaults map."""
    return priority_map.get(event_code, default_priority)


def format_notification_text(event: GalaxyEvent) -> str:
    """
    Formats the notification message text.
    It intelligently chooses between the rich ASCII block text (if available)
    or constructs a message from the Data block fields.
    """
    time = event.time or "??"
    
    # The site name is now part of the notification title, so it is omitted from the body.
    if event.action_text:
        notification = f"{time} {event.action_text}"
        if event.zone and event.zone not in str(event.action_text):
            notification += f" (Zone {event.zone})"
    else:
        notification = f"{time}"
        if event.event_code:
            notification += f" Event: {event.event_code} ({event.event_description})"
        if event.user_id:
            notification += f" User: {event.user_id}"
        if event.zone:
            notification += f" Zone: {event.zone}"
        if event.partition:
            notification += f" Partition: {event.partition}"
    
    return notification.strip()


def _dispatch_http_notification(event: GalaxyEvent, ntfy_topics: Dict, priority_map: Dict, 
                               default_priority: int) -> bool:
    """Sends a formatted notification using topic-specific configuration."""
    
    # 1. Find the correct topic configuration for this event's account.
    topic_config = ntfy_topics.get(event.account, ntfy_topics.get('default'))
    
    # 2. Check if notifications are enabled for this specific topic.
    if not topic_config or not topic_config.get('enabled', False):
        log.debug("Notifications disabled for account '%s' or default topic. Skipping.", event.account)
        return False
        
    ntfy_url = topic_config.get('url')
    if not ntfy_url or 'your-topic-here' in ntfy_url:
        log.warning("No valid ntfy.sh URL found for account '%s' or default. Skipping.", event.account)
        return False
    
    if not event.event_code:
        log.warning("Event has no event_code, cannot determine priority. Skipping notification.")
        return False

    message = format_notification_text(event)
    priority = get_event_priority(event.event_code, priority_map, default_priority)
    
    # 3. Get the title from the topic's specific configuration.
    notification_title = topic_config.get('title', 'Galaxy Alarm')
    title = f"{notification_title}: {event.site_name or event.account}"
    
    headers = {
        "Title": title,
        "Priority": str(priority),
    }
    
    auth_config = topic_config.get('auth')
    auth_details = None
    if auth_config:
        log.debug("ntfy.sh authentication is configured for this topic.")
        method = auth_config.get('method')
        if method == 'token':
            token = auth_config.get('token')
            if token:
                headers['Authorization'] = f"Bearer {token}"
                log.debug("Using Bearer token authentication.")
        elif method == 'userpass':
            user = auth_config.get('user')
            password = auth_config.get('pass')
            if user and password:
                auth_details = (user, password)
                log.debug("Using username/password authentication.")
                         
    log.info("Sending notification (priority %d) to %s: %s", priority, ntfy_url, message)
    
    try:
        response = requests.post(
            ntfy_url,
            data=message.encode('utf-8'),
            headers=headers,
            timeout=10,
            auth=auth_details
        )
        response.raise_for_status()
        log.info("Dispatch successful for account %s.", event.account)
        return True
            
    except requests.exceptions.Timeout:
        log.error("Notification failed: Request to ntfy.sh timed out.")
        return False
    except requests.exceptions.RequestException as e:
        log.error("Dispatch failed for account %s: %s", event.account, e)
        return False

class NotificationDispatcher(Thread):
    """
    A non-blocking background thread that processes a queue of notifications.
    It handles sending and retries with progressive backoff without blocking the queue.
    """
    def __init__(self, queue: Queue, ntfy_topics: Dict, priority_map: Dict, 
                 default_priority: int, max_retries: int, max_retry_time: int):
        super().__init__(daemon=True)
        self.name = "NotificationDispatcher"
        self.queue = queue
        self.ntfy_topics = ntfy_topics
        self.priority_map = priority_map
        self.default_priority = default_priority
        self.max_retries = max_retries
        self.max_retry_time_minutes = max_retry_time
        self.shutdown_event = ThreadEvent()

    def get_retry_delay(self, retry_count: int) -> int:
        """
        Calculates the retry delay using a progressive backoff strategy (exponential backoff).
        The delay doubles with each retry, up to the configured maximum.
        """
        # Start with a 1-minute base delay
        base_delay = 1 # in minutes

        # Double the delay for each previous attempt (2^0, 2^1, 2^2, ...)
        # The 'retry_count' starts at 1 for the first retry.
        current_delay = base_delay * (2 ** (retry_count - 1))

        # Ensure the delay does not exceed the user-configured maximum
        final_delay = min(current_delay, self.max_retry_time_minutes)
        
        return final_delay * 60 # Convert minutes to seconds

    def run(self):
        log.info("NotificationDispatcher thread started.")
        while not self.shutdown_event.is_set():
            event, retry_count, next_attempt_time = self.queue.get()
            if not event: # This is the shutdown signal
                self.queue.task_done()
                break

            current_time = time.time()

            if current_time < next_attempt_time:
                # It's not time to retry this item yet.
                # Put it back at the end of the queue and immediately process the next item.
                self.queue.put((event, retry_count, next_attempt_time))
                self.queue.task_done()
                # Sleep for a short time to prevent a tight loop if all items are in a wait state.
                time.sleep(1.0) 
                continue
            
            success = _dispatch_http_notification(event, self.ntfy_topics, self.priority_map, self.default_priority)
            
            if not success:
                # The notification failed. Schedule it for a future retry.
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
        self.queue.put((None, 0, 0)) # Unblock the .get() call


# --- This is the NEW function that sia-server will call ---
def enqueue_notification(event: GalaxyEvent, queue: Queue):
    """
    Puts a new event onto the notification queue.
    If the queue is full, it removes the oldest item to make space.
    """
    if queue.full():
        try:
            oldest_event, _, _ = queue.get_nowait()
            log.warning("Notification queue is full. Dropping the oldest event to make space for the new one.")
            queue.task_done()
        except Empty:
            pass
            
    try:
        # A new event is always ready to be sent immediately (next_attempt_time = 0)
        queue.put_nowait((event, 0, 0)) # event, retry_count, next_attempt_time
        log.debug("Event for account %s added to notification queue.", event.account)
    except QueueFull:
        log.error("Notification queue is still full! Event for %s was lost.", event.account)

