"""
Galaxy SIA Protocol Payload Parser

This module is responsible for parsing the *payloads* of valid Galaxy SIA
message blocks. It does not handle protocol framing (length, command, checksums).
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict

log = logging.getLogger(__name__)


@dataclass
class GalaxyEvent:
    """Structured data for a complete Galaxy SIA event."""
    # Raw Payloads for debugging
    account_payload: Optional[bytes] = None
    data_payload: Optional[bytes] = None
    ascii_payload: Optional[bytes] = None
    
    # Parsed from Account Payload
    account: Optional[str] = None
    site_name: Optional[str] = None
    
    # Parsed from Data Payload
    time: Optional[str] = None
    user_id: Optional[str] = None
    partition: Optional[str] = None
    group: Optional[str] = None
    value: Optional[str] = None
    event_code: Optional[str] = None
    zone: Optional[str] = None
    
    # Parsed from ASCII Payload
    action_text: Optional[str] = None


def decode_unknown_text(data: bytes, char_map: Dict[bytes, str]) -> str:
    """
    Decodes text from ASCII blocks using a custom character map.
    This handles the proprietary character encoding used by the Galaxy panel.
    """
    # First, decode using a forgiving single-byte encoding like 'iso-8859-1'
    # This preserves all byte values as characters without error.
    try:
        text = data.decode('iso-8859-1')
    except Exception:
        return "" # Should not happen, but as a fallback

    # Then, replace the known proprietary characters with their correct Unicode equivalents.
    # This is a string-to-string replacement.
    for bad_byte, good_char in char_map.items():
        # The bad byte needs to be decoded the same way to become a character to replace.
        bad_char = bad_byte.decode('iso-8859-1')
        text = text.replace(bad_char, good_char)
    
    return text.strip()


def parse_account_payload(payload: bytes, event: GalaxyEvent):
    """Parses the clean payload of an ACCOUNT_ID block. The payload IS the account number."""
    event.account_payload = payload
    event.account = payload.decode('utf-8', errors='ignore')
    log.debug("Parsed account: '%s'", event.account)


def parse_data_payload(payload: bytes, event: GalaxyEvent):
    """Parses the clean payload of a NEW_EVENT block."""
    event.data_payload = payload
    data_str = payload.decode('utf-8', errors='ignore')
    
    # The entire payload is composed of sections.
    sections = data_str.split('/')
    
    if not sections:
        return

    # Process all sections before the last one, as they have identifiers
    for section in sections[:-1]:
        if section.startswith('ti'):
            event.time = section[2:]
            log.debug("Parsed time: '%s'", event.time)
        elif section.startswith('id'):
            event.user_id = section[2:]
            log.debug("Parsed user_id: '%s'", event.user_id)
        elif section.startswith('pi'):
            event.partition = section[2:]
            log.debug("Parsed partition: '%s'", event.partition)
        elif section.startswith('ri'):
            event.group = section[2:]
            log.debug("Parsed group: '%s'", event.group)
        elif section.startswith('va'):
            event.value = section[2:]
            log.debug("Parsed value: '%s'", event.value)
        else:
            log.debug("Unknown data section identifier found: '%s'", section)
            
    # The last section is always the Event Code, with an optional Zone number appended
    last_section = sections[-1]
    ec_match = re.match(r'([A-Z]{2})(\d{3,4})?', last_section)
    if ec_match:
        event.event_code = ec_match.group(1)
        log.debug("Parsed event_code: '%s'", event.event_code)
        if ec_match.group(2):
            event.zone = ec_match.group(2)
            log.debug("Parsed zone: '%s'", event.zone)
    else:
        log.warning("Could not parse event code from last section: %s", last_section)


def parse_ascii_payload(payload: bytes, event: GalaxyEvent, char_map: Dict[bytes, str]):
    """
    Parses the clean payload of an ASCII block.
    The payload IS the full human-readable text.
    
    Args:
        payload: The raw payload bytes from the ASCII block.
        event: The GalaxyEvent object to populate.
        char_map: The custom character mapping dictionary.
    """
    event.ascii_payload = payload
    
    # The entire payload is the text we want. We just need to decode it correctly.
    event.action_text = decode_unknown_text(payload, char_map)
    
    log.debug("Parsed action_text: '%s'", event.action_text)


def parse_galaxy_event(blocks: List[Dict], account_sites: Dict, 
                      default_site: str, char_map: Dict) -> GalaxyEvent:
    """
    Parses a chunk of valid blocks (from a single event sequence) into a GalaxyEvent object.
    
    Args:
        blocks: A list of dicts, each with 'command' and a clean 'payload'.
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
            log.warning("Unknown command '%s' passed to parser. Payload: %r", command, payload)
            
    return event
