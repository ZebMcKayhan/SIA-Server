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

def decode_unknown_text(data: bytes, char_map: Dict[str, str]) -> str:
    """
    Decodes text from ASCII blocks using a custom character map.
    This handles the proprietary character encoding used by the Galaxy panel.
    """
    try:
        # 1. Decode the raw bytes into a string using a "safe" single-byte encoding.
        # This correctly preserves all the proprietary characters like \x8e as single characters.
        text = data.decode('iso-8859-1')
    except Exception as e:
        log.warning("Could not decode text data: %s", e)
        return ""

    # 2. Now, perform a simple string-to-string replacement for each known character.
    for bad_char, good_char in char_map.items():
        text = text.replace(bad_char, good_char)
    
    return text.strip()

def parse_account_payload(payload: bytes, event: GalaxyEvent):
    """Parses the clean payload of an ACCOUNT_ID block."""
    event.account_payload = payload
    event.account = payload.decode('utf-8', errors='ignore')
    log.debug("Parsed account: '%s'", event.account)

def parse_data_payload(payload: bytes, event: GalaxyEvent, event_code_descriptions: Dict):
    """
    Parses the clean payload of a NEW_EVENT block (Command Byte 'N').

    The payload is a string of sections delimited by '/', for example:
      - 'ti11:45/id001/pi010/CL'
      - 'ti11:46/BA1011'
    """
    event.data_payload = payload
    data_str = payload.decode('utf-8', errors='ignore')

    # The payload consists of sections separated by '/', the last one is special (ECzzzz).
    sections = data_str.split('/')
    if not sections:
        return

    # Process all sections before the last one for identifiers, ti, id, pi, ri, va.
    # We loop through them one by one, but skip the last one.
    for section in sections[:-1]:
        if section.startswith('ti'): # ti11:45
            event.time = section[2:] # 11:45
            log.debug("Parsed time: '%s'", event.time)
        elif section.startswith('id'):  # id001
            event.user_id = section[2:] # 001
            log.debug("Parsed user_id: '%s'", event.user_id)
        elif section.startswith('pi'):    # pi010
            event.partition = section[2:] # 010
            log.debug("Parsed partition: '%s'", event.partition)
        elif section.startswith('ri'):
            event.group = section[2:]
            log.debug("Parsed group: '%s'", event.group)
        elif section.startswith('va'):
            event.value = section[2:]
            log.debug("Parsed value: '%s'", event.value)
        else:
            log.debug("Unknown data section identifier found: '%s'", section)
    
    # Process the last section ('CL' or 'BA1011')
    # It always contains the 2-character Event Code.
    # It may also have a 3-4 digit Zone Number appended directly to the code.
    last_section = sections[-1]

    # We use regex to extract the two parts:
    #   - Group 1: ([A-Z]{2})   -> Exactly two uppercase letters (the Event Code)
    #   - Group 2: (\d{3,4})?  -> An optional group of 3 or 4 digits (the Zone)
    ec_match = re.match(r'([A-Z]{2})(\d{3,4})?', last_section)
    if ec_match:
        event.event_code = ec_match.group(1)
        log.debug("Parsed event_code: '%s'", event.event_code)
        # Look up the human-readable description for this event code.
        event.event_description = event_code_descriptions.get(event.event_code, "Unknown")
        log.debug("Mapped event description: '%s'", event.event_description)
        # Check if the optional Zone group was found.
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
