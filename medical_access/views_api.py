import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views import View
from .models import Appointment, AccessEvent
from django.utils import timezone

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
        card_no = data.get('cardNo') or data.get('card_no') or data.get('card')
        
        if not card_no:
            logger.warning("[QR VERIFY] No card number provided")
            return JsonResponse({
                'status': 'error',
                'message': 'No card number provided'
            }, status=400)
        
        # Find active appointment
        now = timezone.now()
        try:
            appointment = Appointment.objects.get(
                card_no=card_no,
                status='active',
                valid_from__lte=now,
                valid_to__gte=now
            )
            
            # Create access event
            AccessEvent.objects.create(
                appointment=appointment,
                door=None,  # Will be set by event listener
                result=AccessEvent.Result.ALLOW,
                reason='Valid QR code scanned',
                card_no=card_no
            )
            
            logger.info(f"[QR VERIFY] ✅ Access granted for card {card_no}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Access granted',
                'cardNo': card_no,
                'employeeNo': f"APT{appointment.id}"
            })
            
        except Appointment.DoesNotExist:
            logger.warning(f"[QR VERIFY] ❌ No valid appointment found for card {card_no}")
            
            return JsonResponse({
                'status': 'error',
                'message': 'Access denied - invalid or expired pass',
                'cardNo': card_no
            }, status=403)
            
    except Exception as e:
        logger.error(f"[QR VERIFY] Error: {e}")
        return JsonResponse({
            'status': 'error',
            'message': 'Internal server error'
        }, status=500)
