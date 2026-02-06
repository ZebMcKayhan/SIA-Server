"""
Galaxy SIA Notification Handler

Sends formatted notifications to ntfy.sh based on alarm events.
"""

import logging
import requests
from typing import Optional
from .parser import GalaxyEvent

log = logging.getLogger(__name__)


def get_event_priority(event_code: str, priority_map: dict, default_priority: int = 5) -> int:
    """
    Get notification priority for event code.
    
    Args:
        event_code: The SIA event code (e.g., 'BA', 'CL', 'OP')
        priority_map: Dictionary mapping event codes to priorities
        default_priority: Priority to use if event code not in map
        
    Returns:
        Priority level (1-5)
    """
    return priority_map.get(event_code, default_priority)


def format_notification_text(event: GalaxyEvent) -> str:
    """
    Format notification text from event.
    
    For SIA Level 3 (with ASCII block): Uses the action_text
    For SIA Level 2 (no ASCII block): Builds from data block fields
    
    Args:
        event: GalaxyEvent object
        
    Returns:
        Formatted notification string
    """
    time = event.time or "??"
    site = event.site_name or "Unknown"
    
    # If we have ASCII block text, use it (SIA Level 3)
    if event.action_text:
        notification = f"{time} {site} {event.action_text}"
        
        # Add zone info if available and not already in action text
        if event.zone and event.zone not in str(event.action_text):
            notification += f" (Zone {event.zone})"
    
    # Otherwise build from data block (SIA Level 2)
    else:
        notification = f"{time} {site}"
        
        if event.user_id:
            notification += f" User: {event.user_id}"
        
        if event.event_code:
            notification += f" Event: {event.event_code}"
        
        if event.zone:
            notification += f" Zone: {event.zone}"
        
        if event.partition:
            notification += f" Partition: {event.partition}"
    
    return notification


def send_notification(event: GalaxyEvent, ntfy_url: str, priority_map: dict, 
                     default_priority: int = 5, enabled: bool = True, 
                     notification_title: str = 'Alarm') -> bool:
    """
    Send notification to ntfy.sh for a Galaxy event.
    
    Args:
        event: Parsed GalaxyEvent object
        ntfy_url: Full ntfy.sh URL (e.g., 'https://ntfy.sh/my-topic')
        priority_map: Dictionary mapping event codes to priorities
        default_priority: Default priority if event code not mapped
        enabled: Whether notifications are enabled
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    
    if not enabled:
        log.debug("Notifications disabled, skipping")
        return False
    
    if not ntfy_url:
        log.warning("No ntfy.sh URL configured, skipping notification")
        return False
    
    # Format the notification message
    message = format_notification_text(event)
    
    # Determine priority
    priority = get_event_priority(event.event_code, priority_map, default_priority)
    
    # Build notification title
    title = f"{notification_title}: {event.site_name or 'Unknown'}"
    
    # Prepare headers
    headers = {
        "Title": title,
        "Priority": str(priority),
    }
    
    # Log what we're sending
    log.info("Sending notification (priority %d): %s", priority, message)
    log.debug("ntfy.sh URL: %s", ntfy_url)
    log.debug("Headers: %s", headers)
    
    # Send to ntfy.sh
    try:
        response = requests.post(
            ntfy_url,
            data=message.encode('utf-8'),
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            log.info("Notification sent successfully")
            return True
        else:
            log.error("Failed to send notification: HTTP %d - %s", 
                     response.status_code, response.text)
            return False
            
    except requests.exceptions.Timeout:
        log.error("Notification failed: Request timeout")
        return False
    except requests.exceptions.ConnectionError as e:
        log.error("Notification failed: Connection error - %s", e)
        return False
    except Exception as e:
        log.error("Notification failed: %s", e)
        return False
