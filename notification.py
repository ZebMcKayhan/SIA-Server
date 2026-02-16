"""
Galaxy SIA Notification Handler

This module is responsible for formatting and sending notifications
to a service like ntfy.sh based on a parsed GalaxyEvent.
"""

import logging
import requests
from typing import Dict
from galaxy.parser import GalaxyEvent

# --- Force PyOpenSSL to be used by requests ---
# This is a robust way to ensure the more compatible OpenSSL backend is used,
# especially on Windows, to prevent intermittent SSLErrors in difficult
# network environments.
try:
    import urllib3.contrib.pyopenssl
    urllib3.contrib.pyopenssl.inject_into_urllib3()
    logging.getLogger(__name__).info("Successfully injected PyOpenSSL into urllib3.")
except ImportError:
    logging.getLogger(__name__).warning("PyOpenSSL not available; using default SSL context.")

log = logging.getLogger(__name__)


def get_event_priority(event_code: str, priority_map: Dict, default_priority: int) -> int:
    """Gets the notification priority for a given event code from the config map."""
    return priority_map.get(event_code, default_priority)


def format_notification_text(event: GalaxyEvent) -> str:
    """
    Formats the notification message text.
    It intelligently chooses between the rich ASCII block text (if available)
    or constructs a message from the Data block fields.
    """
    time = event.time or "??"
    site = event.site_name or "Unknown"    
    
    # If we have the rich text from the ASCII block, use it (SIA Level 3+)
    if event.action_text:
        # site name is already in the header, so there is no need to have it in the body as well, it will make cleaner output without it.
        #notification = f"{time} {site} {event.action_text}"
        notification = f"{time} {event.action_text}"
        # Add zone info if it was parsed separately and isn't already in the text
        if event.zone and event.zone not in str(event.action_text):
            notification += f" (Zone {event.zone})"
    # Otherwise, build a basic message from the Data block fields (SIA Level 2)
    else:
        # site name is already in the header, so there is no need to have it in the body as well, it will make cleaner output without it.
        #notification = f"{time} {site}"
        notification = f"{time}"
        if event.event_code:
            notification += f" Event: {event.event_code} ({event.event_description})"
        if event.user_id:
            notification += f" User: {event.user_id}"
        if event.zone:
            notification += f" Zone: {event.zone}"
        if event.partition:
            notification += f" Partition: {event.partition}"
    
    return notification

def send_notification(event: GalaxyEvent, ntfy_topics: Dict, priority_map: Dict, 
                     default_priority: int, enabled: bool, notification_title: str) -> bool:
    """Sends a formatted notification for a Galaxy event to ntfy.sh."""
    
    if not enabled:
        log.debug("Notifications are disabled in config, skipping.")
        return False
        
    topic_config = ntfy_topics.get(event.account, ntfy_topics.get('default'))
    
    if not topic_config or not topic_config.get('url') or 'your-topic-here' in topic_config.get('url'):
        log.warning("No valid ntfy.sh URL found for account '%s' or default. Skipping.", event.account)
        return False
    
    ntfy_url = topic_config['url']
    auth_config = topic_config.get('auth') # This will be the auth dict or None
    
    if not event.event_code:
        log.warning("Event has no event_code, cannot determine priority. Skipping notification.")
        return False

    message = format_notification_text(event)
    priority = get_event_priority(event.event_code, priority_map, default_priority)
    title = f"{notification_title}: {event.site_name or 'Unknown'}"
    
    headers = {
        "Title": title,
        "Priority": str(priority),
    }
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
                         
    log.info("Sending notification (priority %d): %s", priority, message)
    log.debug("ntfy.sh URL: %s, Headers: %s", ntfy_url, headers)
    
    try:
        response = requests.post(
            ntfy_url,
            data=message.encode('utf-8'),
            headers=headers,
            timeout=10,
            auth=auth_details
        )
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        log.info("Notification sent successfully.")
        return True
            
    except requests.exceptions.Timeout:
        log.error("Notification failed: Request to ntfy.sh timed out.")
        return False
    except requests.exceptions.RequestException as e:
        log.error("Notification failed: %s", e)
        return False
