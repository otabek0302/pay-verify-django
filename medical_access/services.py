import string
from datetime import datetime
from django.utils import timezone
from core.hikvision import HikTerminal
from .models import Terminal


# Simple QR Code Verification
def verify_simple_token(qr_code: str):
    """  Verify a simple QR code format. Args: qr_code: The QR code to verify Returns: (is_valid, qr_data, error_message) """
    if not qr_code:
        return False, {}, "Empty QR code"
    
    if len(qr_code) != 12:
        return False, {}, "Invalid QR code length"
    
    # Check if QR code contains only valid characters (uppercase letters and numbers)
    valid_chars = set(string.ascii_uppercase + string.digits)
    if not all(char in valid_chars for char in qr_code):
        return False, {}, "Invalid QR code characters"
    
    return True, {'qr_code': qr_code}, ""

# Probe terminal via ISAPI and update status fields.
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

# Helper function to convert datetime to ISO format for terminal
def _iso(dt_obj: datetime) -> str:
    """Convert datetime to ISO format for terminal"""
    return dt_obj.strftime("%Y-%m-%dT%H:%M:%S")

def to_iso(dt):
    """ISO format the device accepts, e.g. "2025-09-06T07:00:00" """
    return dt.strftime("%Y-%m-%dT%H:%M:%S")