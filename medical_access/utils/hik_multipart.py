"""
Hikvision multipart event extraction utilities
"""
import json
import logging

logger = logging.getLogger(__name__)

def extract_hik_events(request):
    """
    Extract Hikvision events from multipart or JSON request body.
    Returns list of parsed JSON objects or None if no valid events found.
    """
    try:
        # Try JSON body first
        if request.content_type == 'application/json':
            raw = request.body.decode('utf-8', 'ignore')
            if raw and raw.strip().startswith('{'):
                data = json.loads(raw)
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
        raw = request.body.decode('utf-8', 'ignore')
        if '--MIME_boundary' in raw or 'Content-Disposition: form-data' in raw:
            events = []
            # Split by boundary markers
            parts = raw.split('--MIME_boundary')
            
            for part in parts:
                if 'Content-Type: application/json' in part:
                    # Extract JSON content
                    lines = part.split('\n')
                    json_lines = []
                    in_json = False
                    
                    for line in lines:
                        if 'Content-Type: application/json' in line:
                            in_json = True
                            continue
                        elif in_json and line.strip() and not line.startswith('Content-') and not line.startswith('--'):
                            json_lines.append(line)
                        elif in_json and line.strip() == '--MIME_boundary--':
                            # End of JSON block
                            break
                    
                    if json_lines:
                        try:
                            json_str = '\n'.join(json_lines).strip()
                            if json_str:
                                data = json.loads(json_str)
                                if data:
                                    events.append(data)
                        except (json.JSONDecodeError, TypeError):
                            continue
            
            return events if events else []
        
        return []
        
    except Exception as e:
        logger.error(f"Error extracting Hikvision events: {e}")
        return []
