import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from .models import Appointment, Door
from .controller.hik_client import HikClient

log = logging.getLogger("medical_access")

def _emp(appt_id: int) -> str:
    return f"APT{appt_id}"

def _generate_card_no() -> str:
    """Generate 8-digit numeric card number"""
    import random
    return str(random.randint(10000000, 99999999))

# Simple test signal - this should fire for ANY appointment save
@receiver(post_save, sender=Appointment)
def test_signal_working(sender, instance: Appointment, created, **kwargs):
    """Test signal to verify signals are working"""
    # Signal fired for appointment

@receiver(post_save, sender=Appointment)
def provision_on_paid_appointment(sender, instance: Appointment, created, **kwargs):
    """Simple signal - when appointment is created, provision to terminals"""
    # Only act when appointment is paid and has valid_from/valid_to
    if not instance.paid or not instance.valid_from or not instance.valid_to:
        return

    # Provision to all terminals using single VISITOR user
    emp = getattr(settings, 'HIK_VISITOR_EMPLOYEE_NO', 'VISITOR')  # Use VISITOR instead of APT{id}
    name = "Visitor"  # Simple name for visitor

    for door in Door.objects.all():
        try:
            client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
            
            # Test connection first
            client.ping()
            
            # Create VISITOR user (safe no-op if already exists)
            client.create_user(emp, name)
            
            # Bind card to VISITOR
            client.bind_card(emp, instance.card_no)
            
        except Exception as e:
            # Log error but continue with other doors
            log.error(f"Failed to provision to {door.name}: {e}")
