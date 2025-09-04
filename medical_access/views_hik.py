import logging, json, re
from datetime import timedelta
from django.http import HttpResponse, HttpRequest
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from email.parser import BytesParser
from email.policy import default as email_default

from .models import Appointment, Door, AccessEvent
from .controller.hik_client import HikClient

log = logging.getLogger("medical_access")


def _parse_bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "ok", "success", "succeed", "allowed"}


def _extract_from_dict(d):
    """
    Try many likely paths/field names used by different Hik firmwares.
    Return (card_no, employee_no, success)
    """
    card = None
    emp = None
    success = None

    # common spots
    acs = d.get("AcsEvent", {}) or d.get("AcsEventInfo", {}) or d.get("AccessControllerEvent", {}) or d
    info = acs.get("AcsEventInfo", {}) if isinstance(acs, dict) else {}
    # straight keys first
    cand_keys = [
        "cardNo", "swipeCardNo", "qrCode", "cardNumber", "credentialNo", "certCardNo"
    ]
    for k in cand_keys:
        v = (d.get(k) or acs.get(k) or info.get(k))
        if v:
            card = str(v).strip()
            break

    # employee / personnel id
    for k in ("employeeNoString", "employeeNo", "personId", "personID"):
        v = (d.get(k) or acs.get(k) or info.get(k))
        if v:
            emp = str(v).strip()
            break

    # status / result
    # Many payloads use statusValue==0 or statusString=="OK"
    status_value = (d.get("statusValue") or acs.get("statusValue") or info.get("statusValue"))
    if status_value is not None:
        try:
            success = int(status_value) == 0
        except Exception:
            success = _parse_bool(status_value)

    status_string = (d.get("statusString") or acs.get("statusString") or info.get("statusString"))
    if success is None and status_string:
        success = _parse_bool(status_string)

    # Sometimes result lives under "AccessControllerEvent"
    if success is None and "result" in d:
        success = _parse_bool(d["result"])

    return card, emp, bool(success)


def _parse_body(request: HttpRequest):
    """
    Returns list of dict events (some firmwares bundle multiple).
    Handles multipart, JSON, XML(minimal), and plain text.
    """
    ctype = request.META.get("CONTENT_TYPE", "")
    raw = request.body or b""

    # multipart/form-data from Hik (most common)
    if "multipart/form-data" in ctype and raw.startswith(b"--"):
        msg = BytesParser(policy=email_default).parsebytes(
            b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + raw
        )
        events = []
        for part in msg.iter_parts():
            payload = part.get_payload(decode=True) or b""
            # JSON first
            try:
                events.append(json.loads(payload.decode(errors="ignore")))
                continue
            except Exception:
                pass
            # very simple XML to dict attempt (only if contains cardNo etc.)
            text = payload.decode(errors="ignore")
            if "<" in text and ">" in text:
                # extract like <cardNo>123</cardNo>
                d = {}
                for tag in ("cardNo", "employeeNoString", "statusValue", "statusString",
                            "AcsEventInfo", "employeeNo"):
                    m = re.search(rf"<{tag}>(.*?)</{tag}>", text)
                    if m:
                        d[tag] = m.group(1)
                if d:
                    events.append(d)
                    continue
        if events:
            return events

    # JSON
    try:
        obj = json.loads(raw.decode(errors="ignore"))
        if isinstance(obj, list):
            return obj
        return [obj]
    except Exception:
        pass

    # minimal XML sniff
    text = raw.decode(errors="ignore")
    if "<AcsEvent" in text or "<cardNo>" in text:
        d = {}
        for tag in ("cardNo", "employeeNoString", "statusValue", "statusString"):
            m = re.search(rf"<{tag}>(.*?)</{tag}>", text)
            if m:
                d[tag] = m.group(1)
        return [d] if d else []

    # plain form (fallback)
    return [{"raw": text}]


@csrf_exempt
def hik_event_webhook(request: HttpRequest):
    if request.method != "POST":
        return HttpResponse("Method Not Allowed", status=405)

    src_ip = request.META.get("REMOTE_ADDR", "?")
    events = _parse_body(request)
    log.info(f"[HIK EVENT] from {src_ip} — parsed {len(events)} event(s)")

    now = timezone.now()
    acted = 0

    for ev in events:
        card, emp, success = _extract_from_dict(ev)
        log.info(f"[HIK PARSER] card={card} emp={emp} success={success} rawKeys={list(ev)[:6]}")

        # GUARD RAIL 1: Require cardNo - ignore face scans and other access without cards
        if not card:
            log.info(f"[HIK PARSER] Ignoring access without cardNo (face recognition, PIN, etc.) - emp={emp}")
            continue
        
        # GUARD RAIL 2: Only process VISITOR user - ignore ADMIN, other employees
        if emp != "VISITOR":
            log.info(f"[HIK PARSER] Ignoring non-VISITOR access: emp={emp}, card={card}")
            continue
        
        # GUARD RAIL 3: Only process if it's a valid VISITOR QR card in database
        appointment = (Appointment.objects
                      .filter(card_no=str(card), status="active",
                              valid_from__lte=now, valid_to__gte=now)
                      .order_by("-id").first())
        
        if not appointment:
            log.warning(f"[HIK PARSER] VISITOR QR card {card} not found in database - ignoring")
            continue
            
        log.info(f"[HIK PARSER] ✅ Processing VISITOR QR card {card} for appointment {appointment.id}")

        # If we found a valid appointment, treat it as a successful scan (even if device says success=False)
        # This enables server-assisted door opening for devices that don't support local door rights
        
        # 1) Open door remotely (works even if device denied locally)
        door = Door.objects.filter(terminal_ip=src_ip).first()
        if door:
            try:
                HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)\
                    .remote_open_door(door_no=1)
                log.info(f"[HIK ACTION] Remote door open issued for {door.name}")
            except Exception as e:
                log.warning(f"[HIK ACTION] Remote open failed: {e}")
        else:
            log.warning(f"[HIK ACTION] Door not found for IP {src_ip}; skipped remote open")

        # 2) Mark appointment USED and delete the card from all terminals (one-time use)
        appointment.status = "used"
        appointment.used_at = now
        appointment.save(update_fields=["status", "used_at"])

        # Delete the specific card from VISITOR user (not the entire user)
        for door in Door.objects.all():
            try:
                # Delete only the specific card, keep VISITOR user
                client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
                client.delete_card(appointment.card_no)
                log.info(f"[HIK REVOKE][{door.name}] Removed card {appointment.card_no} from VISITOR")
            except Exception as e:
                log.warning(f"[HIK REVOKE][{door.name}] delete_card({appointment.card_no}) failed: {e}")

        log.info(f"[HIK ACTION] Marked appointment {appointment.card_no} USED and removed card from VISITOR")
        acted += 1

    return HttpResponse("OK")
