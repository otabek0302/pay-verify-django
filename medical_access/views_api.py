import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views import View
from .models import Appointment, AccessEvent
from django.utils import timezone
from django.db import models

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def qr_verify(request):
    """
    QR verification endpoint for Hikvision terminals.
    Returns success/failure response for card verification.
    """
    try:
        # Parse request data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            # Handle form data
            data = request.POST.dict()
        
        logger.info(f"[QR VERIFY] Request data: {data}")
        
        # Extract card number from request
        card_no = data.get('cardNo') or data.get('card_no') or data.get('card') or data.get('code')
        
        logger.info(f"[QR VERIFY] Extracted card_no: {card_no}")
        logger.info(f"[QR VERIFY] Available keys in data: {list(data.keys())}")
        
        if not card_no:
            logger.warning("[QR VERIFY] No card number provided")
            return JsonResponse({
                'status': 'error',
                'message': 'No card number provided'
            }, status=400)
        
        # Find appointment (active or used)
        now = timezone.now()
        try:
            # First try to find active appointment with valid time range
            appointment = Appointment.objects.filter(
                card_no=card_no,
                status='active'
            ).filter(
                models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=now),
                models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=now)
            ).first()
            
            if not appointment:
                # If no active appointment found with time range, try without time constraints
                appointment = Appointment.objects.filter(
                    card_no=card_no,
                    status='active'
                ).first()
            
            if not appointment:
                # If no active appointment found, check if there's a used appointment (already scanned)
                appointment = Appointment.objects.filter(
                    card_no=card_no,
                    status='used'
                ).first()
                
                if appointment:
                    # Return success for already used appointment (prevent multiple scans)
                    logger.info(f"[QR VERIFY] ✅ Access granted for already used card {card_no}")
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Access granted (already used)',
                        'cardNo': card_no,
                        'employeeNo': f"APT{appointment.id}"
                    })
                else:
                    # No appointment found at all
                    logger.warning(f"[QR VERIFY] ❌ No valid appointment found for card {card_no}")
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Access denied - invalid or expired pass',
                        'cardNo': card_no
                    }, status=403)
            
            # Only update status if appointment is active
            if appointment.status == 'active':
                appointment.status = 'used'
                appointment.used_at = now
                appointment.save()
                
                # Create access event
                AccessEvent.objects.create(
                    appointment=appointment,
                    door=None,  # Will be set by event listener
                    result=AccessEvent.Result.ALLOW,
                    reason='Valid QR code scanned',
                    card_no=card_no
                )
                
                logger.info(f"[QR VERIFY] ✅ Access granted for card {card_no}, appointment {appointment.id} marked as used")
            else:
                logger.info(f"[QR VERIFY] ✅ Access granted for already used card {card_no}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Access granted',
                'cardNo': card_no,
                'employeeNo': f"APT{appointment.id}"
            })
            
    except Exception as e:
        logger.error(f"[QR VERIFY] Error: {e}")
        return JsonResponse({
            'status': 'error',
            'message': 'Internal server error'
        }, status=500)
