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
        
        # Find appointment with any status
        now = timezone.now()
        
        # Find appointment by card number (any status)
        appointment = Appointment.objects.filter(card_no=card_no).first()
        
        if not appointment:
            logger.warning(f"[QR VERIFY] ❌ No appointment found for card {card_no}")
            return JsonResponse({
                'status': 'error',
                'message': 'Access denied - invalid pass',
                'cardNo': card_no
            }, status=403)
        
        # Check if appointment is valid (paid and within time range)
        if not appointment.paid:
            logger.warning(f"[QR VERIFY] ❌ Appointment {appointment.id} not paid")
            return JsonResponse({
                'status': 'error',
                'message': 'Access denied - appointment not paid',
                'cardNo': card_no
            }, status=403)
        
        # Check time validity
        if appointment.valid_from and appointment.valid_from > now:
            logger.warning(f"[QR VERIFY] ❌ Appointment {appointment.id} not yet valid")
            return JsonResponse({
                'status': 'error',
                'message': 'Access denied - pass not yet valid',
                'cardNo': card_no
            }, status=403)
        
        if appointment.valid_to and appointment.valid_to < now:
            logger.warning(f"[QR VERIFY] ❌ Appointment {appointment.id} expired")
            return JsonResponse({
                'status': 'error',
                'message': 'Access denied - pass expired',
                'cardNo': card_no
            }, status=403)
        
        # Implement enter/leave logic
        if appointment.status == 'active':
            # First scan: Enter
            appointment.status = 'enter'
            appointment.used_at = now
            appointment.save()
            
            # Create access event for entry
            AccessEvent.objects.create(
                appointment=appointment,
                door=None,  # Will be set by event listener
                result=AccessEvent.Result.ALLOW,
                reason='Entry - Valid QR code scanned',
                card_no=card_no
            )
            
            logger.info(f"[QR VERIFY] ✅ ENTRY granted for card {card_no}, appointment {appointment.id} marked as enter")
            return JsonResponse({
                'status': 'success',
                'message': 'Access granted - Entry',
                'cardNo': card_no,
                'employeeNo': f"APT{appointment.id}",
                'action': 'enter'
            })
            
        elif appointment.status == 'enter':
            # Second scan: Leave
            appointment.status = 'leave'
            appointment.save()
            
            # Create access event for exit
            AccessEvent.objects.create(
                appointment=appointment,
                door=None,  # Will be set by event listener
                result=AccessEvent.Result.ALLOW,
                reason='Exit - Valid QR code scanned',
                card_no=card_no
            )
            
            # TODO: Remove card from VISITOR user on terminals (when API is available)
            # For now, we'll just log this requirement
            logger.info(f"[QR VERIFY] ✅ EXIT granted for card {card_no}, appointment {appointment.id} marked as leave")
            logger.info(f"[QR VERIFY] TODO: Remove card {card_no} from VISITOR user on terminals")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Access granted - Exit',
                'cardNo': card_no,
                'employeeNo': f"APT{appointment.id}",
                'action': 'leave'
            })
            
        elif appointment.status == 'leave':
            # Already left - deny access
            logger.warning(f"[QR VERIFY] ❌ Appointment {appointment.id} already left")
            return JsonResponse({
                'status': 'error',
                'message': 'Access denied - already left',
                'cardNo': card_no
            }, status=403)
            
        else:
            # Other statuses (used, expired, revoked) - deny access
            logger.warning(f"[QR VERIFY] ❌ Appointment {appointment.id} status: {appointment.status}")
            return JsonResponse({
                'status': 'error',
                'message': f'Access denied - status: {appointment.status}',
                'cardNo': card_no
            }, status=403)
            
    except Exception as e:
        logger.error(f"[QR VERIFY] Error: {e}")
        return JsonResponse({
            'status': 'error',
            'message': 'Internal server error'
        }, status=500)
