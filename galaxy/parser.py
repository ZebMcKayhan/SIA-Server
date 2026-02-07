"""
Galaxy SIA Protocol Payload Parser

This module is responsible for parsing the *payloads* of valid Galaxy SIA
message blocks. It does not handle protocol framing (length, checksums).
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict

log = logging.getLogger(__name__)


@dataclass
class GalaxyEvent:
    """Structured data for a complete Galaxy SIA event."""
    # Raw Payloads
    account_payload: Optional[bytes] = None
    data_payload: Optional[bytes] = None
    ascii_payload: Optional[bytes] = None
    
    # Parsed from Account Payload
    account_prefix: Optional[str] = None
    account: Optional[str] = None
    site_name: Optional[str] = None
    
    # Parsed from Data Payload
    message_type: Optional[str] = None
    time: Optional[str] = None
    user_id: Optional[str] = None
    partition: Optional[str] = None
    group: Optional[str] = None
    value: Optional[str] = None
    event_code: Optional[str] = None
    zone: Optional[str] = None
    
    # Parsed from ASCII Payload
    ascii_prefix: Optional[str] = None
    action_text: Optional[str] = None


def decode_unknown_text(data: bytes, char_map: Dict[bytes, str]) -> str:
    """Decodes text from ASCII blocks using a custom character map."""
    text = data
    for bad_byte, good_char in char_map.items():
        text = text.replace(bad_byte, good_char.encode('utf-8'))
    try:
        return text.decode('utf-8', errors='replace').strip()
    except UnicodeDecodeError:
        return text.decode('iso-8859-1', errors='replace').strip()


def parse_account_payload(payload: bytes, event: GalaxyEvent):
    """Parses the payload of an ACCOUNT_ID block."""
    event.account_payload = payload
    
    # Payload format is: <prefix><account_number>
    # Example: b'F027978'
    
    # Find the start of the numeric account number
    match = re.search(rb'(\d{4,})', payload)
    if match:
        start_index = match.start()
        event.account_prefix = payload[:start_index].decode('utf-8', errors='ignore')
        event.account = match.group(0).decode('utf-8', errors='ignore')
    else:
        # Fallback if no digits found
        event.account_prefix = payload.decode('utf-8', errors='ignore')
    
    log.debug("Parsed account_prefix: '%s', account: '%s'", event.account_prefix, event.account)


def parse_data_payload(payload: bytes, event: GalaxyEvent):
    """Parses the payload of a NEW_EVENT block."""
    event.data_payload = payload
    
    data_str = payload.decode('utf-8', errors='ignore')
    sections = data_str.split('/')
    
    if not sections:
        return

    # First part is always the message type + time
    type_and_time = sections[0]
    event.message_type = type_and_time[:2]
    
    time_match = re.search(r'ti(\d{2}:\d{2})', type_and_time)
    if time_match:
        event.time = time_match.group(1)
        
    # Process all other sections (they have identifiers)
    for section in sections[1:-1]:
        if section.startswith('id'):
            event.user_id = section[2:]
        elif section.startswith('pi'):
            event.partition = section[2:]
        elif section.startswith('ri'):
            event.group = section[2:]
        elif section.startswith('va'):
            event.value = section[2:]
        else:
            log.debug("Unknown data section identifier: %s", section)
            
    # The last section is the Event Code (and optional Zone)
    last_section = sections[-1]
    ec_match = re.match(r'([A-Z]{2,4})(\d{3,4})?', last_section)
    if ec_match:
        event.event_code = ec_match.group(1)
        if ec_match.group(2):
            event.zone = ec_match.group(2)
    else:
        log.warning("Could not parse event code from: %s", last_section)


def parse_ascii_payload(payload: bytes, event: GalaxyEvent, char_map: Dict[bytes, str]):
    """Parses the payload of an ASCII block."""
    event.ascii_payload = payload
    
    # The payload is <prefix><text_content>
    # Example: b'Q PÅSLAG    Magnus'
    
    # Find the prefix (everything up to the first space)
    parts = payload.split(b' ', 1)
    if len(parts) > 0:
        event.ascii_prefix = parts[0].decode('utf-8', errors='ignore')
        if len(parts) > 1:
            raw_text = parts[1]
            event.action_text = decode_unknown_text(raw_text, char_map)
        else:
            event.action_text = ""
    else:
        event.action_text = decode_unknown_text(payload, char_map)

    log.debug("Parsed ascii_prefix: '%s', action_text: '%s'", event.ascii_prefix, event.action_text)


def parse_galaxy_event(blocks: List[Dict], account_sites: Dict, 
                      default_site: str, char_map: Dict) -> GalaxyEvent:
    """
    Parses a chunk of valid blocks into a single GalaxyEvent.
    
    Args:
        blocks: A list of dicts, each with 'command' and 'payload'.
        account_sites: Dict mapping account numbers to site names.
        default_site: Default site name if account not found.
        char_map: Custom character mapping dictionary.
        
    Returns:
        A populated GalaxyEvent object.
    """
    event = GalaxyEvent()
    
    for block in blocks:
        command = block['command']
        payload = block['payload']
        
        if command == 'ACCOUNT_ID':
            parse_account_payload(payload, event)
            if event.account:
                event.site_name = account_sites.get(event.account, default_site)
        
        elif command == 'NEW_EVENT':
            parse_data_payload(payload, event)
            
        elif command == 'ASCII':
            parse_ascii_payload(payload, event, char_map)
            
        else:
            log.warning("Unknown command '%s' passed to parser.", command)
            
    return event
