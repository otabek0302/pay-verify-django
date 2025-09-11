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
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Integration, Patient, Doctor, Appointment, QRCode

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
    API endpoint for external platforms to create appointments.
    
    Expected JSON payload:
    {
        "token": "your_integration_token",
        "patient": {
            "first_name": "John",
            "last_name": "Doe", 
            "phone": "+1234567890",
            "passport_series": "AB",
            "passport_number": "1234567"
        },
        "doctor": {
            "first_name": "Dr. Jane",
            "last_name": "Smith",
            "procedure": "General Consultation",
            "price": 100.00
        },
        "appointment_duration_hours": 24  # Optional, defaults to 24
    }
    
    Returns:
    {
        "success": true,
        "appointment_id": 123,
        "qr_code": "ABC123XYZ789",
        "expires_at": "2025-09-11T18:32:15Z",
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
        
        if not data.get("doctor"):
            return JsonResponse({
                "success": False,
                "error": "Doctor information is required"
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
        required_patient_fields = ["first_name", "last_name"]
        for field in required_patient_fields:
            if not patient_data.get(field):
                return JsonResponse({
                    "success": False,
                    "error": f"Patient {field} is required"
                }, status=400)
        
        # Extract doctor data
        doctor_data = data["doctor"]
        required_doctor_fields = ["first_name", "last_name", "procedure", "price"]
        for field in required_doctor_fields:
            if not doctor_data.get(field):
                return JsonResponse({
                    "success": False,
                    "error": f"Doctor {field} is required"
                }, status=400)
        
        # Validate price
        try:
            price = float(doctor_data["price"])
            if price <= 0:
                raise ValueError("Price must be greater than 0")
        except (ValueError, TypeError):
            return JsonResponse({
                "success": False,
                "error": "Doctor price must be a positive number"
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
                first_name=patient_data["first_name"],
                last_name=patient_data["last_name"],
                defaults={
                    "phone": patient_data.get("phone", ""),
                    "passport_series": patient_data.get("passport_series", ""),
                    "passport_number": patient_data.get("passport_number", ""),
                }
            )
            
            if created:
                logger.info(f"API: Created new patient: {patient.full_name}")
            else:
                logger.info(f"API: Using existing patient: {patient.full_name}")
            
            # Create or get doctor
            doctor, created = Doctor.objects.get_or_create(
                first_name=doctor_data["first_name"],
                last_name=doctor_data["last_name"],
                defaults={
                    "procedure": doctor_data["procedure"],
                    "price": price,
                }
            )
            
            if created:
                logger.info(f"API: Created new doctor: {doctor.full_name}")
            else:
                logger.info(f"API: Using existing doctor: {doctor.full_name}")
            
            # Create appointment
            appointment = Appointment.objects.create(
                patient=patient,
                doctor=doctor
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
                "doctor_name": doctor.full_name,
                "procedure": doctor.procedure,
                "price": float(doctor.price),
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
    
    Expected JSON payload:
    {
        "token": "your_integration_token",
        "qr_code": "ABC123XYZ789"
    }
    
    Returns:
    {
        "success": true,
        "valid": true,
        "appointment": {
            "id": 123,
            "patient_name": "John Doe",
            "doctor_name": "Dr. Jane Smith",
            "procedure": "General Consultation",
            "status": "active",
            "expires_at": "2025-09-11T18:32:15Z"
        }
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
            qr_code = QRCode.objects.select_related('appointment__patient', 'appointment__doctor').get(
                code=data["qr_code"]
            )
        except QRCode.DoesNotExist:
            return JsonResponse({
                "success": True,
                "valid": False,
                "message": "QR code not found"
            })
        
        # Check if QR code is valid
        is_valid = qr_code.is_valid
        
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
                "doctor_name": qr_code.appointment.doctor.full_name,
                "procedure": qr_code.appointment.doctor.procedure,
                "price": float(qr_code.appointment.doctor.price),
                "created_at": qr_code.appointment.created_at.isoformat()
            }
            response_data["message"] = "QR code is valid"
        else:
            response_data["message"] = "QR code is expired or revoked"
        
        return JsonResponse(response_data)
    
    except Exception as e:
        logger.error(f"API: Error validating QR code: {e}", exc_info=True)
        return JsonResponse({
            "success": False,
            "error": "Internal server error"
        }, status=500)
