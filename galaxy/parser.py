"""
Galaxy SIA Protocol Parser

Parses Galaxy Flex alarm system SIA messages into structured events.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class GalaxyEvent:
    """Structured Galaxy SIA event data"""
    # Raw blocks as received
    account_raw: Optional[bytes] = None
    data_raw: Optional[bytes] = None
    ascii_raw: Optional[bytes] = None
    
    # Parsed from Account Block
    account_prefix: Optional[str] = None    # Prefix before '#'
    account: Optional[str] = None           # 6-digit account number
    site_name: Optional[str] = None         # Mapped from account
    
    # Parsed from Data Block
    message_type: Optional[str] = None      # Block prefix: VN, PN, QN, JN, NN
    time: Optional[str] = None              # ti: Time
    user_id: Optional[str] = None           # id: User ID
    partition: Optional[str] = None         # pi: Partition
    group: Optional[str] = None             # ri: Group
    value: Optional[str] = None             # va: Value
    event_code: Optional[str] = None        # EV: Event Code
    zone: Optional[str] = None              # z: Zone number
    
    # Parsed from ASCII Block
    ascii_prefix: Optional[str] = None      # Prefix before 'A' (Q, e, [, etc.)
    action_text: Optional[str] = None       # Everything after 'A', Unknown chars fixed


def decode_unknown_text(data, char_map):
    """
    Decode Galaxy Unknown characters with character fixes.
    Args:
        data: Raw bytes from ASCII block
        char_map: Dictionary mapping bad bytes to correct characters
    Returns:
        Decoded string with characters fixed
    """
    # First decode as ISO-8859-1 (preserves all bytes as characters)
    text = data.decode('iso-8859-1', errors='replace')
    
    # Then replace the known problem characters (now as string replacement)
    for bad_byte, good_char in char_map.items():
        bad_char = bad_byte.decode('iso-8859-1')
        text = text.replace(bad_char, good_char)
    
    return text.strip()


def parse_account_block(data, event):
    """
    Parse Account Block (Block 1)
    
    Format: <prefix>#<account><checksum>
    
    We extract:
    - Prefix: Everything before '#'
    - Account: All digits after '#' (typically 4 or 6 digits)
    
    Args:
        data: Raw bytes from account block
        event: GalaxyEvent object to populate
    """
    # Remove checksum byte at end
    data_without_checksum = data[:-1]
    
    # Find the '#' (0x23)
    try:
        hash_position = data_without_checksum.index(b'#')
    except ValueError:
        # No '#' found - can't parse account
        log.warning("No '#' found in account block: %r", data)
        event.account_prefix = 'UNKNOWN'
        return
    
    # Everything before '#' is the prefix
    if hash_position > 0:
        event.account_prefix = data_without_checksum[:hash_position].decode('utf-8', errors='ignore')
    else:
        event.account_prefix = ''
    
    # Everything after '#' is the account number (whatever length it is)
    account_start = hash_position + 1
    event.account = data_without_checksum[account_start:].decode('utf-8', errors='ignore')
    
    log.debug("Account prefix: '%s', account: '%s'", event.account_prefix, event.account)


def parse_data_block(data, event):
    """
    Parse DATA block (N block code)
    
    Structure: Prefix + sections delimited by /
    - All sections BEFORE the last have identifiers (ti, id, pi, ri, etc.)
    - The LAST section is ALWAYS the Event Code (may have zone attached)
    
    Examples:
    - VNti16:38/id001/pi010/CL       → sections: [ti16:38, id001, pi010] + last: CL
    - NNti16:38/BA1012                → sections: [ti16:38] + last: BA1012
    - QNti12:16/va1440/RP             → sections: [ti12:16, va1440] + last: RP
    
    Args:
        data: Raw bytes from data block
        event: GalaxyEvent object to populate
    """
    # Block prefix (first 2 characters)
    if len(data) >= 2:
        event.message_type = data[:2].decode('utf-8', errors='ignore')
    
    # Remove prefix and checksum, split by /
    # Find where actual data starts (after prefix like "VN", "NN", etc.)
    data_str = data[2:-1].decode('utf-8', errors='ignore')  # Remove prefix and checksum byte
    sections = data_str.split('/')
    
    if not sections:
        return
    
    # Process all sections EXCEPT the last one (they have identifiers)
    for section in sections[:-1]:
        if section.startswith('ti'):
            # Time: tiHH:MM
            event.time = section[2:]
            log.debug("Parsed time: %s", event.time)
        elif section.startswith('id'):
            # User ID: id###
            event.user_id = section[2:]
            log.debug("Parsed user_id: %s", event.user_id)
        elif section.startswith('pi'):
            # Partition: pi###
            event.partition = section[2:]
            log.debug("Parsed partition: %s", event.partition)
        elif section.startswith('ri'):
            # Group: ri###
            event.group = section[2:]
            log.debug("Parsed group: %s", event.group)
        elif section.startswith('va'):
            # Value field (seen in auto tests): va####
            event.value = section[2:]
            log.debug("Parsed value: %s", event.value)
        else:
            log.debug("Unknown section identifier: %s", section)
        # Add more identifiers as we discover them
    
    # The LAST section is always Event Code (possibly with zone)
    if sections:
        last_section = sections[-1]
        
        # Event code is 2-4 uppercase letters, followed by optional digits (zone)
        ec_match = re.match(r'([A-Z]{2,4})(\d{3,4})?', last_section)
        if ec_match:
            event.event_code = ec_match.group(1)
            log.debug("Parsed event_code: %s", event.event_code)
            if ec_match.group(2):
                event.zone = ec_match.group(2)
                log.debug("Parsed zone: %s", event.zone)


def parse_ascii_block(data, event, char_map):
    """
    Parse ASCII block - extract prefix and text
    
    Args:
        data: Raw bytes from ASCII block
        event: GalaxyEvent object to populate
        char_map: Unknown character mapping dictionary
    """
    # Remove checksum byte at end
    data_without_checksum = data[:-1]
    
    # Find the first 'A' (0x41)
    try:
        a_position = data_without_checksum.index(b'A')
    except ValueError:
        # No 'A' found - store as-is
        log.warning("No 'A' found in ASCII block: %r", data[:20])
        event.ascii_prefix = 'UNKNOWN'
        event.action_text = decode_unknown_text(data_without_checksum, char_map)
        return
    
    # Everything before 'A' is the prefix
    if a_position > 0:
        event.ascii_prefix = data_without_checksum[:a_position].decode('utf-8', errors='ignore')
    else:
        event.ascii_prefix = ''
    
    # Everything from 'A' onwards (excluding 'A' itself) is the ASCII block
    ascii_block = data_without_checksum[a_position+1:]  # Skip the 'A'
    
    # Decode with Unknown character fixes
    event.action_text = decode_unknown_text(ascii_block, char_map)
    
    log.debug("ASCII prefix: '%s', text: '%s'", event.ascii_prefix, event.action_text)


def parse_galaxy_event(messages, account_sites, default_site, char_map):
    """
    Parse Galaxy event from received message blocks
    
    Args:
        messages: List of raw message bytes (blocks)
        account_sites: Dict mapping account numbers to site names
        default_site: Default site name if account not found
        char_map: Swedish character mapping dictionary
        
    Returns:
        GalaxyEvent object with parsed data
    """
    event = GalaxyEvent()
    
    # Block 1: Account Block
    if len(messages) >= 1:
        event.account_raw = messages[0]
        parse_account_block(messages[0], event)
        
        # Map account to site name
        if event.account:
            event.site_name = account_sites.get(event.account, default_site)
    
    # Block 2: Data Block
    if len(messages) >= 2:
        event.data_raw = messages[1]
        parse_data_block(messages[1], event)
    
    # Block 3: ASCII Block (optional - SIA Level 2 may not have this)
    if len(messages) >= 3 and not messages[2].startswith(b'@0'):
        event.ascii_raw = messages[2]
        parse_ascii_block(messages[2], event, char_map)  # Pass char_map
    
    return event


def format_notification_text(event):
    """
    Format notification text for display
    
    Args:
        event: GalaxyEvent object
        
    Returns:
        Formatted notification string
    """
    time = event.time or "??"
    site = event.site_name or "Unknown"
    action = event.action_text or f"Event: {event.event_code}"
    
    notification = f"{time} {site} {action}"
    
    # Add zone info if available and not already in action text
    if event.zone and event.zone not in str(event.action_text):
        notification += f" (Zone {event.zone})"
    
    return notification
