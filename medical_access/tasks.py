# medical_access/tasks.py
from .models import Appointment, Door
from django.utils import timezone
from .controller.hik_client import HikClient

def expire_old_appointments():
    """Expire old appointments and revoke from all doors"""
    now = timezone.now()
    expired_appointments = Appointment.objects.filter(status="active", valid_to__lt=now)
    
    for appointment in expired_appointments:
        appointment.status = "expired"
        appointment.save()
        
        # Revoke from all doors
        for door in Door.objects.all():
            try:
                client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
                client.delete_user(appointment.card_no)
            except Exception:
                pass  # Continue with other doors even if one fails