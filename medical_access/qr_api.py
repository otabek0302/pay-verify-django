from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
import json
from .models import Appointment, AccessEvent, Door
from .controller.hik_client import HikClient

def _get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

@csrf_exempt
@require_POST
def qr_verify_api(request):
    """
    QR Verification API
    POST /api/qr/verify
    Input: {"code": "card_number"}
    Output: {"result": "allow/deny", "reason": "...", "patient_name": "..."}
    """
    try:
        data = json.loads(request.body)
        card_no = data.get('code', '').strip()
        
        if not card_no:
            return JsonResponse({
                'result': 'deny',
                'reason': 'No QR code provided'
            }, status=400)
        
        # Get client info for audit
        ip_address = _get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Find the appointment
        try:
            appointment = Appointment.objects.select_related(
                'patient', 'procedure'
            ).get(card_no=card_no)
        except Appointment.DoesNotExist:
            # Log denied access
            AccessEvent.objects.create(
                card_no=card_no,
                source=AccessEvent.Source.KIOSK,
                result=AccessEvent.Result.DENY,
                reason='Invalid QR code - not found',
                ip_address=ip_address,
                user_agent=user_agent
            )
            return JsonResponse({
                'result': 'deny',
                'reason': 'Invalid QR code'
            })
        
        # Check if appointment is paid
        if not appointment.paid:
            AccessEvent.objects.create(
                card_no=card_no,
                source=AccessEvent.Source.KIOSK,
                result=AccessEvent.Result.DENY,
                reason='Appointment not paid',
                appointment=appointment,
                ip_address=ip_address,
                user_agent=user_agent
            )
            return JsonResponse({
                'result': 'deny',
                'reason': 'Payment required'
            })
        
        # Check if already used
        if appointment.status == Appointment.Status.USED:
            AccessEvent.objects.create(
                card_no=card_no,
                source=AccessEvent.Source.KIOSK,
                result=AccessEvent.Result.DENY,
                reason='QR code already used',
                appointment=appointment,
                ip_address=ip_address,
                user_agent=user_agent
            )
            return JsonResponse({
                'result': 'deny',
                'reason': 'QR code already used'
            })
        
        # Check if expired or revoked
        if appointment.status in [Appointment.Status.EXPIRED, Appointment.Status.REVOKED]:
            AccessEvent.objects.create(
                card_no=card_no,
                source=AccessEvent.Source.KIOSK,
                result=AccessEvent.Result.DENY,
                reason=f'QR code {appointment.status}',
                appointment=appointment,
                ip_address=ip_address,
                user_agent=user_agent
            )
            return JsonResponse({
                'result': 'deny',
                'reason': f'QR code {appointment.status}'
            })
        
        # Check validity window
        now = timezone.now()
        if not (appointment.valid_from <= now <= appointment.valid_to):
            reason = 'QR code expired' if now > appointment.valid_to else 'QR code not yet valid'
            AccessEvent.objects.create(
                card_no=card_no,
                source=AccessEvent.Source.KIOSK,
                result=AccessEvent.Result.DENY,
                reason=reason,
                appointment=appointment,
                ip_address=ip_address,
                user_agent=user_agent
            )
            return JsonResponse({
                'result': 'deny',
                'reason': reason
            })
        
        # All checks passed - ALLOW access and mark as used
        appointment.mark_as_used()
        
        # Delete user from all terminals so QR cannot work again
        emp = f"APT{appointment.id}"
        for door in Door.objects.all():
            try:
                HikClient(door.terminal_ip, door.terminal_username, door.terminal_password).delete_user(emp)
                # User deleted successfully
                pass
            except Exception as e:
                # Log error but continue
                pass
        
        # Log successful access
        AccessEvent.objects.create(
            card_no=card_no,
            source=AccessEvent.Source.KIOSK,
            result=AccessEvent.Result.ALLOW,
            reason='Valid QR code - access granted, user revoked',
            appointment=appointment,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        return JsonResponse({
            'result': 'allow',
            'reason': 'Access granted',
            'patient_name': appointment.patient.full_name,
            'procedure': appointment.procedure.title,
            'appointment_date': appointment.appointment_date.strftime('%Y-%m-%d'),
            'appointment_time': appointment.appointment_time.strftime('%H:%M')
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'result': 'deny',
            'reason': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        # Log system error
        AccessEvent.objects.create(
            card_no=card_no if 'card_no' in locals() else 'unknown',
            source=AccessEvent.Source.KIOSK,
            result=AccessEvent.Result.DENY,
            reason=f'System error: {str(e)}',
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        return JsonResponse({
            'result': 'deny',
            'reason': 'System error'
        }, status=500)

def kiosk_view(request):
    """Kiosk interface for QR scanning"""
    context = {
        'title': 'Medical Access Kiosk',
    }
    return render(request, 'medical_access/scanning_page.html', context)

@csrf_exempt
@require_POST
def remote_open_door_api(request):
    """
    Remote Door Open API (VIP/Emergency Access)
    POST /api/door/remote-open/
    Input: {"code": "card_number", "door_id": 1, "operator": "staff_name"}
    Output: {"result": "success/error", "message": "..."}
    """
    try:
        data = json.loads(request.body)
        card_no = data.get('code', '').strip()
        door_id = data.get('door_id')
        operator = data.get('operator', 'Unknown')
        
        if not card_no:
            return JsonResponse({
                'result': 'error',
                'message': 'No QR code provided'
            }, status=400)
        
        # Get client info for audit
        ip_address = _get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Verify the QR code first
        try:
            appointment = Appointment.objects.select_related(
                'patient'
            ).get(card_no=card_no)
        except Appointment.DoesNotExist:
            AccessEvent.objects.create(
                card_no=card_no,
                source=AccessEvent.Source.ADMIN,
                result=AccessEvent.Result.DENY,
                reason='Remote open failed - invalid QR code',
                operator=operator,
                ip_address=ip_address,
                user_agent=user_agent
            )
            return JsonResponse({
                'result': 'error',
                'message': 'Invalid QR code'
            })
        
        # Check if valid for remote open
        if not appointment.paid:
            AccessEvent.objects.create(
                card_no=card_no,
                source=AccessEvent.Source.ADMIN,
                result=AccessEvent.Result.DENY,
                reason='Remote open failed - appointment not paid',
                appointment=appointment,
                operator=operator,
                ip_address=ip_address,
                user_agent=user_agent
            )
            return JsonResponse({
                'result': 'error',
                'message': 'Payment required'
            })
        
        # Remote open all doors (or specific door)
        doors_to_open = [Door.objects.get(id=door_id)] if door_id else Door.objects.all()
        opened_count = 0
        
        for door in doors_to_open:
            try:
                client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
                client.remote_open_door()
                opened_count += 1
            except Exception as e:
                # Failed to open door - log error but continue
                pass
        
        # Mark as used if successful
        if opened_count > 0 and appointment.status == Appointment.Status.ACTIVE:
            appointment.mark_as_used()
        
        # Log the remote access event
        AccessEvent.objects.create(
            card_no=card_no,
            source=AccessEvent.Source.ADMIN,
            result=AccessEvent.Result.ALLOW if opened_count > 0 else AccessEvent.Result.DENY,
            reason=f'Remote open by {operator} - {opened_count} doors opened',
            appointment=appointment,
            operator=operator,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        return JsonResponse({
            'result': 'success' if opened_count > 0 else 'error',
            'message': f'Opened {opened_count} door(s)',
            'patient_name': appointment.patient.full_name,
            'doors_opened': opened_count
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'result': 'error',
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'result': 'error',
            'message': f'System error: {str(e)}'
        }, status=500)
