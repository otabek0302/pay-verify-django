from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.conf import settings
from django.shortcuts import get_object_or_404
import json
import re
import logging
import requests
import hmac
import hashlib
from datetime import datetime, timedelta
from medical_access.models import Terminal, Appointment, Patient, Doctor
from medical_access.services import open_door, verify_simple_qr_code, generate_simple_qr_code

BOUNDARY_RE = re.compile(r'^--(?P<b>[-A-Za-z0-9_]+)$')


def verify_appointment_access(qr_code, terminal_mode):
    """
    Verify if a QR code has valid access based on appointment status (Remote-Only Mode).
    Returns (is_valid, appointment, message)
    """
    try:
        # First verify the QR code format
        is_valid_qr, qr_data, qr_error = verify_simple_qr_code(qr_code)
        if not is_valid_qr:
            return False, None, f"❌ ACCESS DENIED: {qr_error}"
        
        # Find appointment with this QR code (active, enter, or leave status)
        now = timezone.now()
        appointment = Appointment.objects.filter(
            qr_code=qr_code,
            status__in=['active', 'enter', 'leave'],
            valid_from__lte=now,
            valid_till__gte=now
        ).first()
        
        if not appointment:
            return False, None, "❌ ACCESS DENIED: No valid appointment found for QR code"
        
        # Check if appointment is valid for this terminal mode
        if terminal_mode.lower() == "entry":
            if appointment.status == 'active':
                # Mark as used and allow entry
                appointment.status = 'enter'
                appointment.used_at = now
                appointment.save()
                return True, appointment, f"✅ ACCESS GRANTED: Entry allowed for {appointment.patient.full_name}"
            else:
                return False, appointment, "❌ ACCESS DENIED: Appointment already used for entry"
                
        elif terminal_mode.lower() == "exit":
            if appointment.status == 'enter':
                # Mark as left and allow exit
                appointment.status = 'leave'
                appointment.save()
                return True, appointment, f"✅ ACCESS GRANTED: Exit allowed for {appointment.patient.full_name}"
            elif appointment.status == 'leave':
                return False, appointment, "❌ ACCESS DENIED: Already exited"
            else:
                return False, appointment, "❌ ACCESS DENIED: Must enter before exiting"
        else:
            # For 'both' mode, check current status
            if appointment.status == 'active':
                appointment.status = 'enter'
                appointment.used_at = now
                appointment.save()
                return True, appointment, f"✅ ACCESS GRANTED: Entry allowed for {appointment.patient.full_name}"
            elif appointment.status == 'enter':
                appointment.status = 'leave'
                appointment.save()
                return True, appointment, f"✅ ACCESS GRANTED: Exit allowed for {appointment.patient.full_name}"
            else:
                return False, appointment, "❌ ACCESS DENIED: Appointment already completed"
                
    except Exception as e:
        return False, None, f"Verification error: {str(e)}"

def remote_only_verify(qr_code, terminal_mode, terminal_ip):
    """
    Remote-Only verification: Check appointment validity using simple QR code.
    No card provisioning or expiration - pure remote verification.
    """
    # Verify the appointment against database using QR code
    is_valid, appointment, message = verify_appointment_access(qr_code, terminal_mode)
    
    if is_valid and appointment:
        # Update the message to indicate remote-only mode
        message = f"{message} (Simple QR Code Remote Verification)"
    
    return is_valid, appointment, message

@csrf_exempt
def hik_event_receiver(request):
    """
    Remote verification receiver for Hikvision terminals.
    Implements proper remote verification flow:
    1. Receives scan events from terminals
    2. Verifies against Django appointment logic
    3. Returns allow/deny decision to terminal
    4. Opens door if access granted
    """
    try:
        body = request.body.decode("utf-8", errors="ignore")
        
        # Get terminal IP from request
        terminal_ip = request.META.get("REMOTE_ADDR")
        
        # Look up terminal by IP
        term = Terminal.objects.filter(terminal_ip=terminal_ip, active=True).first()
        if not term:
            return HttpResponse("OK", status=200)
        
        mode = term.mode
        terminal_name = term.terminal_name
        
        # Parse multipart body to find verification events
        events = []
        for part in body.split("\n--"):
            if "{" in part:
                js = part[part.find("{"):]
                try:
                    data = json.loads(js)
                except Exception:
                    continue
                    
                ev = data.get("AccessControllerEvent") or data.get("AcsEvent") or {}
                
                # Debug: Log all available fields to see what the terminal is sending
                logger = logging.getLogger(__name__)
                logger.info(f"Terminal event data: {ev}")
                
                # Try multiple possible field names for QR code data
                card = (ev.get("cardNo") or 
                       ev.get("credentialNo") or 
                       ev.get("qrCode") or
                       ev.get("qrData") or
                       ev.get("qr_code") or
                       ev.get("qrCodeData") or
                       ev.get("qrContent") or
                       ev.get("data") or
                       ev.get("content"))
                
                verify = (ev.get("verifyMode") or ev.get("currentVerifyMode") or "").lower()
                major = ev.get("major") or ev.get("majorEventType")
                time_str = ev.get("time") or ev.get("dateTime")
                
                # Process access verification events (major=5)
                if major == 5 and card:
                    # Remote-Only verification: Check appointment validity using QR code
                    is_valid, appointment, message = remote_only_verify(card, mode, terminal_ip)
                    
                    if is_valid:
                        # Open door on the terminal
                        try:
                            open_door(term, door_no=1)
                        except Exception:
                            pass  # Door open errors are logged elsewhere
                    
                    events.append({
                        "ip": terminal_ip,
                        "name": terminal_name,
                        "mode": mode,
                        "card": card,
                        "verify": verify,
                        "result": "granted" if is_valid else "denied",
                        "message": message,
                        "appointment_id": appointment.id if appointment else None,
                        "time": time_str
                    })
        
        if not events:
            # No verification events found, return OK
            return HttpResponse("OK (no verification events)", status=200)
        
        # Return verification results
        return JsonResponse({
            "ok": True, 
            "count": len(events), 
            "events": events,
            "terminal": {
                "name": terminal_name,
                "ip": terminal_ip,
                "mode": mode
            }
        })
        
    except Exception as e:
        # Log error to Django logging system instead of print
        logger = logging.getLogger(__name__)
        logger.error(f"Remote verification error: {e}")
        # Always return 200 to keep terminal happy
        return HttpResponse("OK", status=200)


# =============================================================================
# DMED PLATFORM INTEGRATION - EVENT HANDLERS
# =============================================================================

# DMED API Configuration
DMED_API_TOKEN = getattr(settings, 'DMED_API_TOKEN', 'your-dmed-api-token')
DMED_API_URL = getattr(settings, 'DMED_API_URL', 'https://api.dmed.com')
DMED_SHARED_SECRET = getattr(settings, 'DMED_SHARED_SECRET', 'your-shared-secret')

def verify_dmed_signature(request):
    """
    Verify DMED API signature for security
    """
    signature = request.headers.get('X-Signature', '')
    if not signature:
        return False, "Missing X-Signature header"
    
    # Extract hash from signature
    if not signature.startswith('sha256='):
        return False, "Invalid signature format"
    
    expected_hash = signature[7:]  # Remove 'sha256=' prefix
    
    # Calculate HMAC of request body
    body = request.body
    calculated_hash = hmac.new(
        DMED_SHARED_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_hash, calculated_hash):
        return False, "Invalid signature"
    
    return True, "Valid signature"

@csrf_exempt
@require_POST
def dmed_create_appointment(request):
    """
    DMED → PayVerify: Receive new appointment data from DMED
    Creates appointment in our database and generates QR token
    """
    try:
        # Verify authentication
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return JsonResponse({
                'success': False,
                'error': 'Missing or invalid Authorization header'
            }, status=401)
        
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        if token != DMED_API_TOKEN:
            return JsonResponse({
                'success': False,
                'error': 'Invalid API token'
            }, status=401)
        
        # Verify signature (optional but recommended)
        is_valid_sig, sig_error = verify_dmed_signature(request)
        if not is_valid_sig:
            logger = logging.getLogger(__name__)
            logger.warning(f"DMED signature verification failed: {sig_error}")
            # Continue anyway for now, but log the warning
        
        # Parse request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data'
            }, status=400)
        
        # Extract required fields from DMED data
        dmed_appointment_id = data.get('appointment_id')
        
        # Patient information
        patient_data = data.get('patient', {})
        first_name = patient_data.get('first_name')
        last_name = patient_data.get('last_name')
        phone = patient_data.get('phone', '')
        passport_series = patient_data.get('passport_series', '')
        passport_number = patient_data.get('passport_number', '')
        
        # Doctor information
        doctor_data = data.get('doctor', {})
        doctor_name = doctor_data.get('name')
        doctor_specialty = doctor_data.get('specialty', '')
        
        # Appointment timing
        appointment_datetime = data.get('appointment_datetime')
        
        # Validate required fields
        if not all([dmed_appointment_id, first_name, last_name, doctor_name]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields: appointment_id, patient name, doctor name'
            }, status=400)
        
        # Check if appointment already exists
        if Appointment.objects.filter(qr_code__contains=dmed_appointment_id).exists():
            return JsonResponse({
                'success': False,
                'error': 'Appointment already exists'
            }, status=409)
        
        # Get or create patient
        if phone:
            patient, created = Patient.objects.get_or_create(
                phone=phone,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'passport_series': passport_series,
                    'passport_number': passport_number
                }
            )
            if not created:
                # Update existing patient info
                patient.first_name = first_name
                patient.last_name = last_name
                patient.passport_series = passport_series
                patient.passport_number = passport_number
                patient.save()
        else:
            # Create new patient without phone
            patient = Patient.objects.create(
                first_name=first_name,
                last_name=last_name,
                passport_series=passport_series,
                passport_number=passport_number
            )
        
        # Get or create doctor
        doctor, created = Doctor.objects.get_or_create(
            name=doctor_name,
            defaults={
                'specialty': doctor_specialty,
                'phone': '',
                'email': ''
            }
        )
        
        # Parse appointment datetime
        if appointment_datetime:
            try:
                if isinstance(appointment_datetime, str):
                    appointment_dt = datetime.fromisoformat(appointment_datetime.replace('Z', '+00:00'))
                else:
                    appointment_dt = appointment_datetime
            except (ValueError, TypeError):
                appointment_dt = timezone.now()
        else:
            appointment_dt = timezone.now()
        
        # Set validity period (24 hours from appointment time)
        valid_from = appointment_dt - timedelta(hours=1)  # 1 hour before appointment
        valid_till = appointment_dt + timedelta(hours=25)  # 1 hour after appointment
        
        # Generate simple QR code
        qr_code = generate_simple_qr_code()
        
        # Create appointment
        appointment = Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            status='active',
            valid_from=valid_from,
            valid_till=valid_till,
            qr_code=qr_code
        )
        
        # Send QR code back to DMED
        qr_sent = send_qr_to_dmed(dmed_appointment_id, qr_code, appointment.id)
        
        logger = logging.getLogger(__name__)
        logger.info(f"DMED appointment created: {appointment.id} for patient {patient.full_name}")
        
        return JsonResponse({
            'success': True,
            'message': 'Appointment created successfully',
            'appointment_id': appointment.id,
            'qr_token': token,
            'qr_sent_to_dmed': qr_sent
        })
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"DMED appointment creation failed: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)

def send_qr_to_dmed(dmed_appointment_id, qr_code, appointment_id):
    """
    PayVerify → DMED: Send QR code back to DMED
    """
    try:
        url = f"{DMED_API_URL}/appointments/{dmed_appointment_id}/qr"
        
        headers = {
            'Authorization': f'Bearer {DMED_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'appointment_id': dmed_appointment_id,
            'qr_code': qr_code,
            'payverify_appointment_id': appointment_id,
            'qr_expires_at': timezone.now() + timedelta(hours=24).isoformat(),
            'status': 'active'
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            logger = logging.getLogger(__name__)
            logger.info(f"QR code sent to DMED successfully for appointment {appointment_id}")
            return True
        else:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send QR to DMED: {response.status_code} - {response.text}")
            return False
            
    except requests.RequestException as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error sending QR to DMED: {str(e)}")
        return False
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error sending QR to DMED: {str(e)}")
        return False

@csrf_exempt
@require_POST
def dmed_appointment_status(request, appointment_id):
    """
    DMED → PayVerify: Update appointment status (optional webhook)
    """
    try:
        # Verify authentication
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Invalid authorization'}, status=401)
        
        token = auth_header[7:]
        if token != DMED_API_TOKEN:
            return JsonResponse({'error': 'Invalid token'}, status=401)
        
        data = json.loads(request.body)
        new_status = data.get('status')
        
        if not new_status:
            return JsonResponse({'error': 'Status required'}, status=400)
        
        appointment = get_object_or_404(Appointment, id=appointment_id)
        appointment.status = new_status
        appointment.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Appointment {appointment_id} status updated to {new_status}'
        })
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"DMED status update failed: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)
