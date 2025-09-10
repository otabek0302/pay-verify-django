import json
import logging
import re
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import Appointment, Terminal, QRCode
from .services import open_door
from .utils.hik_multipart import extract_hik_events

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
        Appointment.objects.select_related("patient", "doctor", "qr_code")
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
                    "doctor": appointment.doctor.full_name,
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
                    "doctor": appointment.doctor.full_name,
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
                "doctor": appointment.doctor.full_name,
                "status": appointment.qr_code.status,
            },
        }
    )


@csrf_exempt
@require_POST
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
        if not payloads:
            # Some firmwares send heartbeats with no JSON part; just 200 OK
            return HttpResponse("OK", status=200)

        # Iterate until we find a usable event
        for data in payloads:
            ev = data.get("AccessControllerEvent") or data.get("AcsEvent") or {}
            embedded_ip = (ev.get("ipAddress") or "").strip()
            qr = ev.get("qrCode") or ev.get("credentialNo") or ev.get("cardNo")
            major = ev.get("major") or ev.get("majorEventType")
            event_type = (ev.get("eventType") or "").lower()

            # Resolve terminal:
            term = None
            if embedded_ip:
                term = Terminal.objects.filter(terminal_ip=embedded_ip, active=True).first()
            if not term:
                # fallbacks (unreliable on some firmwares, but harmless)
                xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
                remote = request.META.get("REMOTE_ADDR")
                term = (
                    Terminal.objects.filter(terminal_ip=xff, active=True).first()
                    or Terminal.objects.filter(terminal_ip=remote, active=True).first()
                )

            if not term:
                # Unknown device → OK and move on to next payload (don't spam warnings)
                logger.info("HIK: unknown terminal (embedded_ip=%s, xff=%s, remote=%s)",
                         embedded_ip, request.META.get("HTTP_X_FORWARDED_FOR"), request.META.get("REMOTE_ADDR"))
                continue

            # Fast-ignore: heartbeats & events without QR/card payload
            if event_type == "heartbeat" or not qr:
                # Quiet success, terminal won't retry
                return HttpResponse("OK", status=200)

            # Process only access verify events (major==5 on many firmwares), but
            # we'll still accept if QR exists to be resilient across variants.
            mode = (term.mode or "").lower()

            appt = (
                Appointment.objects
                .select_related("patient", "doctor", "qr_code")
                .filter(
                    qr_code__code=qr,
                    qr_code__status__in=[QRCode.Status.ACTIVE, QRCode.Status.ENTERED, QRCode.Status.LEFT],
                    qr_code__expires_at__gt=timezone.now(),
                )
                .first()
            )
            if not appt:
                # Return OK so device doesn't keep retrying; just no access
                logger.info("HIK: invalid/expired QR from %s (%s) payload=%s",
                         term.terminal_name, term.terminal_ip, qr)
                return HttpResponse("OK", status=200)

            current = appt.qr_code.status
            next_status = None
            if mode == "entry" and current == QRCode.Status.ACTIVE:
                next_status = QRCode.Status.ENTERED
            elif mode == "exit" and current == QRCode.Status.ENTERED:
                next_status = QRCode.Status.LEFT
            elif mode not in ("entry", "exit"):  # both
                if current == QRCode.Status.ACTIVE:
                    next_status = QRCode.Status.ENTERED
                elif current == QRCode.Status.ENTERED:
                    next_status = QRCode.Status.LEFT

            if not next_status:
                logger.info("HIK: deny at %s (%s) – invalid transition from %s in %s mode (qr=%s)",
                         term.terminal_name, term.terminal_ip, current, mode or "both", qr)
                return HttpResponse("OK", status=200)

            # Update status and try to open door
            appt.qr_code.status = next_status
            appt.qr_code.save(update_fields=["status"])

            res = open_door(term, door_no=1)
            if not res.get("ok"):
                # Roll back status if you prefer (optional)
                appt.qr_code.status = current
                appt.qr_code.save(update_fields=["status"])
                logger.warning("HIK: door open failed at %s (%s): %s",
                            term.terminal_name, term.terminal_ip, res.get("error"))

            logger.info("HIK: access %s at %s (%s) for %s -> %s",
                     "GRANTED" if res.get("ok") else "DENIED",
                     term.terminal_name, term.terminal_ip, qr, next_status)

            return HttpResponse("OK", status=200)

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