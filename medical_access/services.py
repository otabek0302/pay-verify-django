import re
import hashlib
import json
import random
import string
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from .models import Terminal
from core.hikvision import HikTerminal
# REMOVED: VISITOR constants - Not needed for Remote-Only Mode

# Very naive XML credential extractor; adjust once you see real payloads.
CREDENTIAL_RE = re.compile(rb"<credentialNo>([^<]+)</credentialNo>", re.IGNORECASE)

# Simple QR Code Generation

def generate_simple_qr_code() -> str:
    """
    Generate a simple 12-character QR code for appointment verification.
    
    Returns:
        12-character alphanumeric string (uppercase letters and numbers)
    """
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(12))

def verify_simple_qr_code(qr_code: str) -> tuple[bool, dict, str]:
    """
    Verify a simple QR code format.
    
    Args:
        qr_code: The QR code to verify
        
    Returns:
        (is_valid, qr_data, error_message)
    """
    if not qr_code:
        return False, {}, "Empty QR code"
    
    if len(qr_code) != 12:
        return False, {}, "Invalid QR code length"
    
    # Check if QR code contains only valid characters (uppercase letters and numbers)
    valid_chars = set(string.ascii_uppercase + string.digits)
    if not all(char in valid_chars for char in qr_code):
        return False, {}, "Invalid QR code characters"
    
    return True, {'qr_code': qr_code}, ""

def encode_qr_to_numeric(qr_payload: str) -> str:
    """
    Convert alphanumeric QR payload to numeric-only card number.
    Some Hikvision terminals only accept numeric cardNo.
    
    Uses SHA-1 hash and takes first 18 digits for stability.
    """
    if qr_payload.isdigit():
        # Already numeric, return as-is (but limit length)
        return qr_payload[:18]
    
    # Convert to numeric using SHA-1 hash
    hash_obj = hashlib.sha1(qr_payload.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    
    # Convert hex to decimal and take first 18 digits
    hash_decimal = str(int(hash_hex, 16))
    return hash_decimal[:18]

def probe_terminal(term: Terminal) -> dict:
    """Ping terminal via ISAPI and update status fields."""
    cli = HikTerminal(term.terminal_ip, term.terminal_username, term.terminal_password)
    try:
        info = cli.device_info()  # simple GET
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
    cli = HikTerminal(term.terminal_ip, term.terminal_username, term.terminal_password)
    try:
        cli.open_door(door_no=door_no, cmd="open")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# REMOVED: ensure_visitor - Not needed for Remote-Only Mode
# REMOVED: push_card - Not needed for Remote-Only Mode

def _iso(dt_obj: datetime) -> str:
    """Convert datetime to ISO format for terminal"""
    return dt_obj.strftime("%Y-%m-%dT%H:%M:%S")

# REMOVED: disable_card_on_terminal - Not needed for Remote-Only Mode

# REMOVED: expire_card_on_all_terminals - Not needed for Remote-Only Mode

# REMOVED: provision_card_for_appointment - Not needed for Remote-Only Mode

def update_appointment_status(qr_code: str, terminal_mode: str):
    """Update appointment status based on scan and terminal mode."""
    from .models import Appointment
    
    # Find appointment by QR code
    try:
        appointment = Appointment.objects.get(qr_code=qr_code)
        
        if terminal_mode.lower() == "entry":
            if appointment.status == Appointment.Status.ACTIVE:
                appointment.status = Appointment.Status.ENTER
                appointment.used_at = timezone.now()
                appointment.save()
        elif terminal_mode.lower() == "exit":
            if appointment.status == Appointment.Status.ENTER:
                appointment.status = Appointment.Status.LEAVE
                appointment.save()
                
    except Appointment.DoesNotExist:
        pass  # No appointment found - this is handled by the calling function
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating appointment: {e}")

# REMOVED: disable_card_on_mode - Not needed for Remote-Only Mode

def fetch_recent_scans(term: Terminal, seconds: int = 120):
    """
    Get recent access events from this terminal and return:
    - raw json (as dict)
    - simplified list of scans (cardNo/credential, verifyMode, time, door/reader)
    """
    end = datetime.now()
    start = end - timedelta(seconds=seconds)

    cli = HikTerminal(term.terminal_ip, term.terminal_username, term.terminal_password)
    status, body = cli.acs_event_search(_iso(start), _iso(end))

    if status != 200:
        return {"ok": False, "status": status, "body": body[:300]}

    data = json.loads(body) if body else {}
    # Different firmwares wrap results differently – handle both
    events = []
    if isinstance(data, dict):
        if "AcsEvent" in data:
            acs_event = data["AcsEvent"]
            if isinstance(acs_event, list):
                events = acs_event
            elif isinstance(acs_event, dict) and "InfoList" in acs_event:
                events = acs_event["InfoList"]
        elif "AcsEventList" in data and "AcsEvent" in data["AcsEventList"]:
            events = data["AcsEventList"]["AcsEvent"]

    simplified = []
    for ev in events:
        # Determine event type
        event_type = "unknown"
        if ev.get("major") == 5:
            event_type = "access_scan"
        elif ev.get("major") == 3:
            event_type = "admin_action"
        elif ev.get("major") == 2:
            event_type = "system_event"
        
        simplified.append({
            "time":       ev.get("time") or ev.get("dateTime"),
            "event_type": event_type,
            "cardNo":     ev.get("cardNo") or ev.get("credentialNo") or ev.get("qrCode") or "N/A",
            "employeeNo": ev.get("employeeNo") or "N/A",
            "verifyMode": (ev.get("currentVerifyMode") or ev.get("verifyMode") or "").lower(),
            "readerNo":   ev.get("cardReaderNo") or ev.get("readerNo") or "N/A",
            "doorNo":     ev.get("doorNo") or "N/A",
            "major":      ev.get("major") or ev.get("majorEventType"),
            "minor":      ev.get("minor") or ev.get("subEventType"),
            "serialNo":   ev.get("serialNo") or ev.get("serialNumber"),
            "cardType":   ev.get("cardType"),
            "mask":       ev.get("mask"),
            "pictureURL": ev.get("pictureURL"),
        })

    return {"ok": True, "raw": data, "events": simplified}
