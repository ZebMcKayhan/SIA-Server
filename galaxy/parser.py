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
    event_description: Optional[str] = None 
    zone: Optional[str] = None
    
    # Parsed from ASCII Payload
    action_text: Optional[str] = None

def decode_unknown_text(data: bytes, char_map: Dict[bytes, str]) -> str:
    """Decodes text from ASCII blocks using a custom character map."""
    try:
        text = data.decode('iso-8859-1')
    except Exception:
        return ""
    for bad_byte, good_char in char_map.items():
        bad_char = bad_byte.decode('iso-8859-1')
        text = text.replace(bad_char, good_char)
    return text.strip()

def parse_account_payload(payload: bytes, event: GalaxyEvent):
    """Parses the clean payload of an ACCOUNT_ID block."""
    event.account_payload = payload
    event.account = payload.decode('utf-8', errors='ignore')
    log.debug("Parsed account: '%s'", event.account)

def parse_data_payload(payload: bytes, event: GalaxyEvent, event_code_descriptions: Dict):
    """Parses the clean payload of a NEW_EVENT block."""
    event.data_payload = payload
    data_str = payload.decode('utf-8', errors='ignore')
    
    sections = data_str.split('/')
    if not sections:
        return
        
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
            
    last_section = sections[-1]
    ec_match = re.match(r'([A-Z]{2})(\d{3,4})?', last_section)
    if ec_match:
        event.event_code = ec_match.group(1)
        log.debug("Parsed event_code: '%s'", event.event_code)
        event.event_description = event_code_descriptions.get(event.event_code, "Unknown")
        log.debug("Mapped event description: '%s'", event.event_description)
        
        if ec_match.group(2):
            event.zone = ec_match.group(2)
            log.debug("Parsed zone: '%s'", event.zone)
    else:
        log.warning("Could not parse event code from last section: %s", last_section)

def parse_ascii_payload(payload: bytes, event: GalaxyEvent, char_map: Dict[bytes, str]):
    """Parses the clean payload of an ASCII block."""
    event.ascii_payload = payload
    event.action_text = decode_unknown_text(payload, char_map)
    log.debug("Parsed action_text: '%s'", event.action_text)

def parse_galaxy_event(blocks: List[Dict], account_sites: Dict, 
                      char_map: Dict, event_code_descriptions: Dict) -> GalaxyEvent:
    """
    Parses a chunk of valid blocks into a GalaxyEvent object.
    
    Args:
        blocks: A list of dicts, each with 'command' and a clean 'payload'.
        account_sites: Dict mapping account numbers to site names.
        char_map: Custom character mapping dictionary.
        event_code_descriptions: Dict mapping event codes to descriptions.
        
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
                # Use the mapped site name if it exists, otherwise fall back to the account number itself.
                event.site_name = account_sites.get(event.account, event.account)
        
        elif command == 'NEW_EVENT':
           parse_data_payload(payload, event, event_code_descriptions)
            
        elif command == 'ASCII':
            parse_ascii_payload(payload, event, char_map)
            
        else:
            log.warning("Unknown command '%s' passed to parser. Payload: %r", command, payload)
            
    return event
