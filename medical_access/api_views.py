"""
API views for external integrations
"""
import json
import logging
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction

from .models import Integration, Patient, Appointment, QRCode

logger = logging.getLogger("medical_access.api")


def validate_integration_token(token):
    """Validate integration token and return integration object"""
    try:
        integration = Integration.objects.get(api_token=token, is_active=True)
        return integration, None
    except Integration.DoesNotExist:
        return None, "Invalid or inactive integration token"
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return None, "Token validation failed"


@csrf_exempt
@require_POST
def create_appointment_api(request):
    """
    API endpoint for external partners to create appointments.
    
    Workflow:
    1. Partner sends patient data with their integration token
    2. PayVerify creates appointment and returns QR code
    3. Partner generates QR code on their side using the returned code
    4. QR code validation happens when scanned at terminal
    
    Expected JSON payload:
    {
        "token": "your_integration_token",
        "patient": {
            "first_name": "John",
            "last_name": "Doe", 
            "medical_card_number": "MC1234567"
        },
        "appointment_duration_hours": 24  # Optional, defaults to 24
    }
    
    Returns:
    {
        "success": true,
        "appointment_id": 123,
        "qr_code": "ABC123XYZ789",  # Use this to generate QR code on your side
        "expires_at": "2025-09-11T18:32:15Z",
        "patient_name": "John Doe",
        "patient_medical_card": "MC1234567",
        "message": "Appointment created successfully"
    }
    """
    try:
        # Parse JSON payload
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                "success": False,
                "error": "Invalid JSON format"
            }, status=400)
        
        # Validate required fields
        if not data.get("token"):
            return JsonResponse({
                "success": False,
                "error": "Integration token is required"
            }, status=400)
        
        if not data.get("patient"):
            return JsonResponse({
                "success": False,
                "error": "Patient information is required"
            }, status=400)
        
        # Validate integration token
        integration, token_error = validate_integration_token(data["token"])
        if not integration:
            return JsonResponse({
                "success": False,
                "error": token_error
            }, status=401)
        
        logger.info(f"API: Creating appointment for integration: {integration.name}")
        
        # Extract patient data
        patient_data = data["patient"]
        required_patient_fields = ["first_name", "last_name", "medical_card_number"]
        for field in required_patient_fields:
            if not patient_data.get(field):
                return JsonResponse({
                    "success": False,
                    "error": f"Patient {field} is required"
                }, status=400)
        
        # Get appointment duration (default 24 hours)
        duration_hours = data.get("appointment_duration_hours", 24)
        try:
            duration_hours = int(duration_hours)
            if duration_hours <= 0:
                raise ValueError("Duration must be positive")
        except (ValueError, TypeError):
            return JsonResponse({
                "success": False,
                "error": "Appointment duration must be a positive integer"
            }, status=400)
        
        # Create or get patient
        with transaction.atomic():
            patient, created = Patient.objects.get_or_create(
                medical_card_number=patient_data["medical_card_number"],
                defaults={
                    "first_name": patient_data["first_name"],
                    "last_name": patient_data["last_name"],
                }
            )
            
            if created:
                logger.info(f"API: Created new patient: {patient.full_name}")
            else:
                logger.info(f"API: Using existing patient: {patient.full_name}")
            
            # Create appointment
            appointment = Appointment.objects.create(
                patient=patient
            )
            
            # Create QR code
            expires_at = timezone.now() + timedelta(hours=duration_hours)
            qr_code = QRCode.objects.create(
                appointment=appointment,
                expires_at=expires_at
            )
            
            logger.info(f"API: Created appointment {appointment.id} with QR code {qr_code.code}")
            
            return JsonResponse({
                "success": True,
                "appointment_id": appointment.id,
                "qr_code": qr_code.code,
                "expires_at": qr_code.expires_at.isoformat(),
                "patient_name": patient.full_name,
                "patient_medical_card": patient.medical_card_number,
                "message": "Appointment created successfully"
            })
    
    except Exception as e:
        logger.error(f"API: Error creating appointment: {e}", exc_info=True)
        return JsonResponse({
            "success": False,
            "error": "Internal server error"
        }, status=500)


@csrf_exempt
@require_POST
def validate_qr_code_api(request):
    """
    API endpoint to validate QR codes and get appointment details.
    
    This endpoint validates QR codes that were generated by partners
    using the qr_code returned from create_appointment_api.
    
    Expected JSON payload:
    {
        "token": "your_integration_token",
        "qr_code": "ABC123XYZ789"
    }
    
    Returns:
    {
        "success": true,
        "valid": true,
        "qr_code": "ABC123XYZ789",
        "status": "active",
        "expires_at": "2025-09-11T18:32:15Z",
        "revoked": false,
        "appointment": {
            "id": 123,
            "patient_name": "John Doe",
            "patient_medical_card": "MC1234567",
            "created_at": "2025-09-10T10:30:00Z"
        },
        "message": "QR code is valid"
    }
    """
    try:
        # Parse JSON payload
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                "success": False,
                "error": "Invalid JSON format"
            }, status=400)
        
        # Validate required fields
        if not data.get("token"):
            return JsonResponse({
                "success": False,
                "error": "Integration token is required"
            }, status=400)
        
        if not data.get("qr_code"):
            return JsonResponse({
                "success": False,
                "error": "QR code is required"
            }, status=400)
        
        # Validate integration token
        integration, token_error = validate_integration_token(data["token"])
        if not integration:
            return JsonResponse({
                "success": False,
                "error": token_error
            }, status=401)
        
        # Find QR code
        try:
            qr_code = QRCode.objects.select_related('appointment__patient').get(
                code=data["qr_code"]
            )
        except QRCode.DoesNotExist:
            return JsonResponse({
                "success": True,
                "valid": False,
                "message": "QR code not found"
            })
        
        # Check if QR code is valid (not expired or revoked)
        is_valid = qr_code.is_valid
        
        # Get terminal mode from request (if provided)
        terminal_mode = data.get("terminal_mode", "").lower()
        
        # Update status based on terminal mode and current status
        status_changed = False
        if is_valid:
            if terminal_mode:
                # Physical terminal mode - explicit enter/exit commands
                if terminal_mode == "enter":
                    if qr_code.status == QRCode.Status.ACTIVE:
                        qr_code.status = QRCode.Status.ENTERED
                        qr_code.save()
                        status_changed = True
                elif terminal_mode == "exit" or terminal_mode == "leave":
                    if qr_code.status == QRCode.Status.ENTERED:
                        qr_code.status = QRCode.Status.LEFT
                        qr_code.save()
                        status_changed = True
            else:
                # PC/Mobile browser mode - automatic status progression
                if qr_code.status == QRCode.Status.ACTIVE:
                    qr_code.status = QRCode.Status.ENTERED
                    qr_code.save()
                    status_changed = True
                elif qr_code.status == QRCode.Status.ENTERED:
                    qr_code.status = QRCode.Status.LEFT
                    qr_code.save()
                    status_changed = True
                # If already LEFT, don't change status
        
        response_data = {
            "success": True,
            "valid": is_valid,
            "qr_code": qr_code.code,
            "status": qr_code.status,
            "expires_at": qr_code.expires_at.isoformat(),
            "revoked": qr_code.revoked
        }
        
        if is_valid:
            response_data["appointment"] = {
                "id": qr_code.appointment.id,
                "patient_name": qr_code.appointment.patient.full_name,
                "patient_medical_card": qr_code.appointment.patient.medical_card_number,
                "created_at": qr_code.appointment.created_at.isoformat()
            }
            
            # Set appropriate message based on status and terminal mode
            if terminal_mode:
                # Physical terminal mode - show status changes
                if qr_code.status == QRCode.Status.ENTERED and status_changed:
                    response_data["message"] = "SUCCESS: Patient ENTERED"
                elif qr_code.status == QRCode.Status.LEFT and status_changed:
                    response_data["message"] = "SUCCESS: Patient LEFT"
                elif qr_code.status == QRCode.Status.ENTERED:
                    response_data["message"] = "Patient already ENTERED"
                elif qr_code.status == QRCode.Status.LEFT:
                    response_data["message"] = "Patient already LEFT"
                else:
                    response_data["message"] = "QR code is valid"
            else:
                # PC/Mobile browser mode - simple validation
                if qr_code.status == QRCode.Status.ACTIVE:
                    response_data["message"] = "QR Code Valid - Ready for Entry"
                elif qr_code.status == QRCode.Status.ENTERED:
                    response_data["message"] = "QR Code Valid - Patient Entered"
                elif qr_code.status == QRCode.Status.LEFT:
                    response_data["message"] = "QR Code Valid - Patient Left"
                else:
                    response_data["message"] = "QR code is valid"
        else:
            response_data["message"] = "INVALID: QR code is expired or revoked"
        
        return JsonResponse(response_data)
    
    except Exception as e:
        logger.error(f"API: Error validating QR code: {e}", exc_info=True)
        return JsonResponse({
            "success": False,
            "error": "Internal server error"
        }, status=500)
