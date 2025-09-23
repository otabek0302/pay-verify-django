import json
import logging
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import Appointment, Terminal, QRCode
from .services import open_door, extract_hik_events

logger = logging.getLogger("medical_access.events")


def _extract_qr_code(data):
    """Extract QR code from various data structures"""
    if isinstance(data, dict):
        # Look for common QR code field names
        for key in ['qrCode', 'qr_code', 'code', 'qr', 'cardNumber', 'card_number']:
            if key in data and data[key]:
                return data[key]
        # Recursively search nested objects
        for value in data.values():
            if isinstance(value, (dict, list)):
                result = _extract_qr_code(value)
                if result:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = _extract_qr_code(item)
            if result:
                return result
    return None


def _get_next_status(current_status, terminal_mode):
    """Get next status based on current status and terminal mode"""
    mode = (terminal_mode or "").lower()
    
    if mode == "entry":
        return QRCode.Status.ENTERED if current_status == QRCode.Status.ACTIVE else None
    elif mode == "exit":
        return QRCode.Status.LEFT if current_status == QRCode.Status.ENTERED else None
    else:  # both modes
        if current_status == QRCode.Status.ACTIVE:
            return QRCode.Status.ENTERED
        elif current_status == QRCode.Status.ENTERED:
            return QRCode.Status.LEFT
    return None


def _find_active_appointment_by_token(qr_token):
    """
    Find an active appointment by QR token.
    Returns the appointment if valid and active, None otherwise.
    """
    if not qr_token:
        return None
        
    now = timezone.now()
    try:
        appointment = (
            Appointment.objects
            .select_related("patient", "qr_code")
            .filter(
                qr_code__code=qr_token,
                qr_code__status__in=[QRCode.Status.ACTIVE, QRCode.Status.ENTERED, QRCode.Status.LEFT],
                qr_code__expires_at__gt=now,
            )
            .first()
        )
        return appointment
    except Exception as e:
        logger.error(f"HIK: Error finding appointment for token {qr_token}: {e}")
        return None




@csrf_exempt
@require_POST
def validate_qr_and_open_door(request, terminal_id: int):
    """
    Validate QR code for an appointment and open the door if allowed.
    Accepts JSON: {"qr_code": "..."} or {"qr_payload": "..."}
    """
    terminal = get_object_or_404(Terminal, pk=terminal_id)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON format"}, status=400)

    qr_code = data.get("qr_code") or data.get("qr_payload")
    if not qr_code:
        return JsonResponse({"ok": False, "error": "QR code required"}, status=400)

    # Find appointment with this QR code
    now = timezone.now()
    appointment = (
        Appointment.objects.select_related("patient", "qr_code")
        .filter(
            qr_code__code=qr_code,
            qr_code__status__in=[
                QRCode.Status.ACTIVE,
                QRCode.Status.ENTERED,
                QRCode.Status.LEFT,
            ],
            qr_code__expires_at__gt=now,
        )
        .first()
    )

    if not appointment:
        return JsonResponse(
            {"ok": False, "error": "Invalid or expired QR code", "appointment": None},
            status=400,
        )

    # Determine next status based on current status and terminal mode
    current_status = appointment.qr_code.status
    next_status = _get_next_status(current_status, terminal.mode)

    if not next_status:
        return JsonResponse(
            {
                "ok": False,
                "error": f"Access denied: Invalid status transition from {current_status} for {(terminal.mode or 'unknown').lower()} mode",
                "appointment": {
                    "id": appointment.id,
                    "patient": appointment.patient.full_name,
                    "patient_medical_card": appointment.patient.medical_card_number,
                    "status": current_status,
                },
            },
            status=403,
        )

    # Update QR status
    appointment.qr_code.status = next_status
    appointment.qr_code.save(update_fields=["status"])

    # Try to open the door
    result = open_door(terminal, door_no=1)
    if not result.get("ok"):
        # Rollback status change if door fails
        appointment.qr_code.status = current_status
        appointment.qr_code.save(update_fields=["status"])
        return JsonResponse(
            {
                "ok": False,
                "error": f"Failed to open door: {result.get('error', 'unknown')}",
                "appointment": {
                    "id": appointment.id,
                    "patient": appointment.patient.full_name,
                    "patient_medical_card": appointment.patient.medical_card_number,
                    "status": appointment.qr_code.status,
                },
            },
            status=502,
        )

    return JsonResponse(
        {
            "ok": True,
            "message": "Door opened successfully",
            "appointment": {
                "id": appointment.id,
                "patient": appointment.patient.full_name,
                "patient_medical_card": appointment.patient.medical_card_number,
                "status": appointment.qr_code.status,
            },
        }
    )


def _hik_xml_response(ok: bool, description: str = "OK"):
    # Simple Hikvision ResponseStatus format for AcsEvent
    if ok:
        body = """<?xml version="1.0" encoding="UTF-8"?>
<ResponseStatus version="1.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
    <requestURL>/ISAPI/AccessControl/AcsEvent</requestURL>
    <statusCode>1</statusCode>
    <statusString>OK</statusString>
    <subStatusCode>success</subStatusCode>
    <errorCode>200</errorCode>
    <description>Access granted</description>
</ResponseStatus>"""
    else:
        body = """<?xml version="1.0" encoding="UTF-8"?>
<ResponseStatus version="1.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
    <requestURL>/ISAPI/AccessControl/AcsEvent</requestURL>
    <statusCode>4</statusCode>
    <statusString>Invalid Operation</statusString>
    <subStatusCode>fail</subStatusCode>
    <errorCode>400</errorCode>
    <description>Access denied</description>
</ResponseStatus>"""
    return HttpResponse(body, content_type="application/xml; charset=UTF-8", status=200)


@csrf_exempt
def hik_event_receiver(request):
    """
    Accept Hikvision push events.
    - Identify terminal by JSON 'ipAddress' first, then fall back to request IPs
    - Ignore heartbeats / non-QR events fast (200 OK)
    - Process only when a QR payload is present
    - Perform the same status transition logic as /validate-qr/
    """
    try:
        # Parse ONLY JSON parts out of multipart or raw JSON body
        payloads = extract_hik_events(request) or []
        logger.info("HIK: extracted %d payloads from request", len(payloads))
        if not payloads:
            # Some firmwares send heartbeats with no JSON part; just 200 OK
            logger.info("HIK: no payloads found, returning OK")
            return HttpResponse("OK", status=200)

        # Iterate until we find a usable event
        for i, data in enumerate(payloads):
            logger.info("HIK: processing payload %d: %s", i, data)

            # Hikvision sends metadata (ip/mac/eventType) at the top-level and the actual event under AccessControllerEvent/AcsEvent.
            meta = data or {}
            ev = meta.get("AccessControllerEvent") or meta.get("AcsEvent") or meta

            # Filter out old events - handle timezone differences gracefully
            # Terminals may be on different timezones (UTC+08 vs UTC+05)
            event_time_str = ev.get("dateTime") or meta.get("dateTime") or ""
            if event_time_str:
                try:
                    from datetime import datetime
                    event_time = datetime.fromisoformat(event_time_str.replace('Z', '+00:00'))
                    now = timezone.now()
                    time_diff = (now - event_time).total_seconds()
                    
                    # More lenient filtering: skip only events older than 3 hours
                    # This handles timezone differences and network delays
                    if time_diff > 10800:  # 3 hours = 10800 seconds
                        logger.info("HIK: skipping old event from %s (age: %.0f seconds)", event_time_str, time_diff)
                        continue
                    elif abs(time_diff) > 1800:  # Log significant time differences (30+ minutes)
                        logger.info("HIK: timezone difference detected - event: %s, server: %s, diff: %.0f seconds", 
                                   event_time_str, now.isoformat(), time_diff)
                except Exception as e:
                    logger.warning("HIK: failed to parse event time %s: %s", event_time_str, e)

            # Read device identity from TOP-LEVEL meta (not from ev)
            embedded_ip = (meta.get("ipAddress") or "").strip()
            embedded_mac = (meta.get("macAddress") or "").strip().lower()

            # Determine event type from top-level, then normalize
            event_type = (meta.get("eventType") or ev.get("eventType") or "").strip().lower()

            # Extract QR / credential payload from event body
            qr = (
                ev.get("qrCode")
                or ev.get("credentialNo")
                or ev.get("cardNo")
                or ev.get("code")
            )
            # Some firmwares put QR under nested dicts; last-resort recursive search
            if not qr:
                qr = _extract_qr_code(ev)

            # Resolve terminal by MAC address first, then IP addresses
            term = None
            
            # Priority 1: MAC address (most reliable)
            if embedded_mac:
                term = Terminal.objects.filter(mac_address__iexact=embedded_mac, active=True).first()
                if term:
                    logger.info("HIK: terminal identified by MAC address: %s -> %s", embedded_mac, term.terminal_name)
                else:
                    logger.info("HIK: MAC address %s not found in database", embedded_mac)
            
            # Priority 2: Embedded IP address
            if not term and embedded_ip:
                term = Terminal.objects.filter(terminal_ip=embedded_ip, active=True).first()
                if term:
                    logger.info("HIK: terminal identified by embedded IP: %s -> %s", embedded_ip, term.terminal_name)
            
            # Priority 3: Request IP addresses (fallback)
            if not term:
                xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
                remote = request.META.get("REMOTE_ADDR")
                term = (
                    Terminal.objects.filter(terminal_ip=xff, active=True).first()
                    or Terminal.objects.filter(terminal_ip=remote, active=True).first()
                )
                if term:
                    logger.info("HIK: terminal identified by request IP: %s/%s -> %s", xff, remote, term.terminal_name)
            
            # Priority 4: If no terminal found and this is an AccessControllerEvent, 
            # use the most recently active terminal (fallback for events without MAC)
            if not term and event_type == "accesscontrollerevent":
                term = Terminal.objects.filter(active=True).order_by('-last_seen').first()
                if term:
                    logger.info("HIK: terminal identified by most recent activity: %s", term.terminal_name)

            if not term:
                # Unknown device → OK and move on to next payload (don't spam warnings)
                logger.info("HIK: unknown terminal (mac=%s, embedded_ip=%s, xff=%s, remote=%s, event_type=%s, qr=%s)",
                            embedded_mac, embedded_ip, request.META.get("HTTP_X_FORWARDED_FOR"),
                            request.META.get("REMOTE_ADDR"), event_type, qr)
                continue

            # Fast-ignore: heartbeats & events without QR/card payload
            if event_type in ("heartbeat", "heartbeat") or not qr:
                # Quiet success, terminal won't retry
                return HttpResponse("OK", status=200)

            # Process only access verify events (major==5 on many firmwares), but
            # we'll still accept if QR exists to be resilient across variants.
            mode = (term.mode or "").lower()
            logger.info("HIK: terminal mode: %s (original: %s)", mode, term.mode)

            logger.info("HIK: validating QR code '%s' for terminal %s", qr, term.terminal_name)
            
            # 1) Find active appointment by QR token
            appt = _find_active_appointment_by_token(qr)
            
            # 2) Process QR code validation
            logger.info("HIK: Processing QR code: %s", qr)
            
            if not appt:
                # Check if QR exists but is expired/invalid
                expired_appt = Appointment.objects.filter(qr_code__code=qr).first()
                if expired_appt:
                    logger.info("HIK: ❌ QR EXPIRED/INVALID from %s (%s) - QR exists but expired or wrong status. QR status: %s, expires: %s",
                               term.terminal_name, term.terminal_ip, 
                               expired_appt.qr_code.status, expired_appt.qr_code.expires_at)
                else:
                    logger.info("HIK: ❌ QR NOT FOUND from %s (%s) - QR code '%s' not in database",
                               term.terminal_name, term.terminal_ip, qr)
                return JsonResponse({
                    "code": 0,
                    "message": "success",
                    "data": {
                        "authResult": 1  # 0=pass, 1=fail
                    }
                })

            current = appt.qr_code.status
            next_status = None
            logger.info("HIK: status transition - current: %s, mode: %s", current, mode)
            
            if mode == "entry" and current == QRCode.Status.ACTIVE:
                next_status = QRCode.Status.ENTERED
                logger.info("HIK: entry mode transition: %s -> %s", current, next_status)
            elif mode == "exit" and current == QRCode.Status.ENTERED:
                next_status = QRCode.Status.LEFT
                logger.info("HIK: exit mode transition: %s -> %s", current, next_status)
            elif mode not in ("entry", "exit"):  # both
                if current == QRCode.Status.ACTIVE:
                    next_status = QRCode.Status.ENTERED
                    logger.info("HIK: both mode transition: %s -> %s", current, next_status)
                elif current == QRCode.Status.ENTERED:
                    next_status = QRCode.Status.LEFT
                    logger.info("HIK: both mode transition: %s -> %s", current, next_status)

            if not next_status:
                logger.info("HIK: deny at %s (%s) – invalid transition from %s in %s mode (qr=%s)",
                         term.terminal_name, term.terminal_ip, current, mode or "both", qr)
                return JsonResponse({
                    "code": 0,
                    "message": "success",
                    "data": {
                        "authResult": 1  # 0=pass, 1=fail
                    }
                })

            # 6) Update appointment status
            appt.qr_code.status = next_status
            appt.qr_code.save(update_fields=["status"])

            logger.info("HIK: access GRANTED at %s (%s) for %s -> %s",
                        term.terminal_name, term.terminal_ip, qr, next_status)

            # 7) Door opening is handled by the terminal's local verification
            logger.info("HIK: ✅ ACCESS GRANTED - terminal will handle door opening locally")

            # Return JSON response for Sync mode terminal
            return JsonResponse({
                "code": 0,
                "message": "success", 
                "data": {
                    "authResult": 0  # 0=pass, 1=fail
                }
            })

        # If we got here, nothing actionable; return OK to avoid device retries
        return HttpResponse("OK", status=200)

    except Exception as e:
        # Never bubble errors to device; log and still 200
        logger.error("HIK receiver error: %s", e, exc_info=True)
        return HttpResponse("OK", status=200)


@require_GET
def get_terminal_mode_api(request, terminal_ip: str):
    """Get the current mode of a terminal"""
    terminal = Terminal.objects.filter(terminal_ip=terminal_ip, active=True).first()
    mode = terminal.mode if terminal else "unknown"
    
    return JsonResponse({"ok": True, "terminal_ip": terminal_ip, "mode": mode})
