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
    peripheral: Optional[str] = None
    group: Optional[str] = None
    value: Optional[str] = None
    event_code: Optional[str] = None
    event_description: Optional[str] = None 
    zone: Optional[str] = None
    
    # Parsed from ASCII Payload
    action_text: Optional[str] = None

def decode_unknown_text(data: bytes, char_map: dict) -> str:
    """
    Decodes panel text using CP437 with overrides for characters that differ
    from standard CP437 on this panel.
    char_map keys are raw byte values (int), values are Unicode replacements.
    """
    try:
        # Build a string-to-string replacement map by decoding each key byte through CP437
        str_map = {
            bytes([k]).decode("cp437"): v
            for k, v in char_map.items()
        }
        # Decode the full data using CP437
        text = data.decode("cp437", errors="replace")

        # Replace CP437 results with correct characters
        for cp437_char, correct_char in str_map.items():
            text = text.replace(cp437_char, correct_char)

        return text.strip()

    except Exception as e:
        log.warning("Could not decode text data: %s", e)
        return ""

def parse_account_payload(payload: bytes, event: GalaxyEvent):
    """Parses the clean payload of an ACCOUNT_ID block."""
    event.account_payload = payload
    event.account = payload.decode('utf-8', errors='ignore').lstrip('0') or '0'
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

    # The payload consists of sections separated by '/', lowercase is data modifier, uppercase is Event Code (ECzzzz).
    sections = data_str.split('/')
    if not sections:
        return

    # Process all sections for lowercase identifiers, ti, id, pi, ri, va or uppercase Event Code.
    for section in sections:
        if section[:2].islower():
            if section.startswith('ti'): # ti11:45
                event.time = section[2:] # 11:45
                log.debug("Parsed time: '%s'", event.time)
            elif section.startswith('id'):  # id001
                event.user_id = section[2:].lstrip('0') or '0' # 001 -> 1 (strip leading zeroes)
                log.debug("Parsed user_id: '%s'", event.user_id)
            elif section.startswith('pi'):
                event.peripheral = section[2:].lstrip('0') or '0'
                log.debug("Parsed peripheral: '%s'", event.peripheral)
            elif section.startswith('ri'):
                event.group = section[2:].lstrip('0') or '0'
                log.debug("Parsed group: '%s'", event.group)
            elif section.startswith('va'): # Observed in auto-test as interval in minutes (va1440 = 24h)
                event.value = section[2:].lstrip('0') or '0'
                log.debug("Parsed value: '%s'", event.value)
            # Other possible modifiers according to SIA standard, but never observed:
            # da = Date
            # ai = Automated ID
            # ph = Telephone ID
            # lv = Level
            # pt = Path
            # rg = Route Group
            # ss = Sub-Subscriber
            # We let a warning message catch them in the log if they appear:
            else:
                log.warning("Unknown data section modifier '%s' in payload: %r", section, payload)
        elif section[:2].isupper():
            # Process Event Code section ('CL' or 'BA1011')
            # It always contains the 2-character Event Code.
            # It may also have a 3-4 digit Zone Number appended directly to the code.
            # We use regex to extract the two parts:
            #   - Group 1: ([A-Z]{2})  -> Exactly two uppercase letters (the Event Code)
            #   - Group 2: (\d{3,4})?  -> An optional group of 3 or 4 digits (the Zone)
            ec_match = re.match(r'([A-Z]{2})(\d{3,4})?', section)
            if ec_match:
                event.event_code = ec_match.group(1)
                log.debug("Parsed event_code: '%s'", event.event_code)
                # Look up the human-readable description for this event code.
                event.event_description = event_code_descriptions.get(event.event_code, "Unknown")
                log.debug("Mapped event description: '%s'", event.event_description)
                # Check if the optional Zone group was found.
                if ec_match.group(2):
                    event.zone = ec_match.group(2).lstrip('0') or '0'
                    log.debug("Parsed zone: '%s'", event.zone)
            else:
                log.warning("Could not parse event code from section: %s", section)
        else:
            log.warning("Unknown data section '%s' in payload: %r", section, payload)

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

        # "OLD_EVENT" have never been observed but according to SIA documentation it exist and is identical to NEW_EVENT. Adding it just in case:
        elif command in ('NEW_EVENT', 'OLD_EVENT'):
            parse_data_payload(payload, event, event_code_descriptions)
            
        elif command == 'ASCII':
            parse_ascii_payload(payload, event, char_map)
            
        else:
            log.warning("Unknown command '%s' passed to parser. Payload: %r", command, payload)
            
    return event
