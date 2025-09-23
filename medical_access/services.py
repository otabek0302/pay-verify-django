"""
Terminal service functions for Hikvision integration
"""

import json
import logging
from django.utils import timezone
from core.hikvision import HikTerminal
from .models import Terminal

logger = logging.getLogger(__name__)


def probe_terminal(term: Terminal) -> dict:
    """Test terminal connectivity and update health status"""
    cli = HikTerminal(term.terminal_ip, term.terminal_username, term.terminal_password)
    try:
        info = cli.device_info()
        term.reachable = True
        term.last_seen = timezone.now()
        term.last_error = ""
        term.save(update_fields=["reachable", "last_seen", "last_error"])
        return {"ok": True, "info": info}
    except Exception as e:
        term.reachable = False
        term.last_error = str(e)[:500]
        term.save(update_fields=["reachable", "last_error"])
        return {"ok": False, "error": str(e)}

def open_door(term: Terminal, door_no: int = 1) -> dict:
    """Open door on terminal"""
    cli = HikTerminal(term.terminal_ip, term.terminal_username, term.terminal_password)
    try:
        cli.open_door(door_no=door_no, cmd="open")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def extract_hik_events(request):
    """
    Extract Hikvision events from multipart or JSON request body.
    Returns list of parsed JSON objects or None if no valid events found.
    """
    try:
        # Get the raw body once
        raw_body = request.body.decode('utf-8', 'ignore')
        
        # Try JSON body first
        if request.content_type == 'application/json':
            if raw_body and raw_body.strip().startswith('{'):
                data = json.loads(raw_body)
                return [data] if data else []
        
        # Try multipart form data
        if 'multipart' in (request.content_type or '').lower():
            events = []
            for key in ['AccessControllerEvent', 'AcsEvent']:
                if key in request.POST:
                    try:
                        data = json.loads(request.POST.get(key))
                        if data:
                            events.append(data)
                    except (json.JSONDecodeError, TypeError):
                        continue
            if events:
                return events
        
        # Try raw body parsing for multipart
        if '--MIME_boundary' in raw_body or 'Content-Disposition: form-data' in raw_body:
            events = []
            # Split by boundary markers
            parts = raw_body.split('--MIME_boundary')
            
            for part in parts:
                if 'Content-Type: application/json' in part and 'AccessControllerEvent' in part:
                    # Extract JSON content - look for the JSON block after the headers
                    lines = part.split('\n')
                    json_lines = []
                    in_json = False
                    
                    for line in lines:
                        if 'Content-Type: application/json' in line:
                            in_json = True
                            continue
                        elif in_json and line.strip() and not line.startswith('Content-') and not line.startswith('--'):
                            # This is JSON content
                            json_lines.append(line)
                        elif in_json and (line.strip() == '--MIME_boundary--' or line.strip() == ''):
                            # End of JSON block
                            break
                    
                    if json_lines:
                        try:
                            json_str = '\n'.join(json_lines).strip()
                            if json_str and json_str.startswith('{'):
                                data = json.loads(json_str)
                                if data:
                                    events.append(data)
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.debug(f"JSON parse error: {e}, content: {json_str[:100]}")
                            continue
            
            return events if events else []
        
        return []
        
    except Exception as e:
        logger.error(f"Error extracting Hikvision events: {e}")
        return []