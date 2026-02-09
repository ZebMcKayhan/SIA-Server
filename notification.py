"""
Galaxy SIA Notification Handler

This module is responsible for formatting and sending notifications
to a service like ntfy.sh based on a parsed GalaxyEvent.
"""

import logging
import requests
from typing import Dict
from galaxy.parser import GalaxyEvent

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
        notification = f"{time} {site} {event.action_text}"
        # Add zone info if it was parsed separately and isn't already in the text
        if event.zone and event.zone not in str(event.action_text):
            notification += f" (Zone {event.zone})"
    # Otherwise, build a basic message from the Data block fields (SIA Level 2)
    else:
        notification = f"{time} {site}"
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
     
    # Determine the correct ntfy.sh URL to use for this event's account
    ntfy_url = ntfy_topics.get(event.account, ntfy_topics.get('default'))
                         
    if not ntfy_url or 'your-topic-here' in ntfy_url:
        log.warning("No valid ntfy.sh URL found for account '%s' or default. Skipping notification.", event.account)
        return False
    
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
    
    log.info("Sending notification (priority %d): %s", priority, message)
    log.debug("ntfy.sh URL: %s, Headers: %s", ntfy_url, headers)
    
    try:
        response = requests.post(
            ntfy_url,
            data=message.encode('utf-8'),
            headers=headers,
            timeout=10
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
