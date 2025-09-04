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
    print(f"🔔 [TEST] Signal fired! Appointment {instance.id}, paid={instance.paid}, created={created}")

@receiver(post_save, sender=Appointment)
def provision_on_paid_appointment(sender, instance: Appointment, created, **kwargs):
    """Simple signal - when appointment is created, provision to terminals"""
    print(f"[SIGNAL] Appointment {instance.id} saved, paid={instance.paid}, created={created}")
    
    # Only act when appointment is paid and has valid_from/valid_to
    if not instance.paid or not instance.valid_from or not instance.valid_to:
        print(f"[SIGNAL] Appointment {instance.id} not ready for provisioning, skipping")
        return

    print(f"[SIGNAL] Appointment {instance.id} is ready, provisioning to terminals...")

    # Provision to all terminals using single VISITOR user
    emp = getattr(settings, 'HIK_VISITOR_EMPLOYEE_NO', 'VISITOR')  # Use VISITOR instead of APT{id}
    name = "Visitor"  # Simple name for visitor

    print(f"[SIGNAL] Binding card {instance.card_no} to VISITOR user for appointment {instance.id}")

    for door in Door.objects.all():
        try:
            print(f"[SIGNAL] Trying to provision to {door.name} ({door.terminal_ip})")
            client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
            
            # Test connection first
            client.ping()
            print(f"[SIGNAL] ✅ Connected to {door.name}")
            
            # Create VISITOR user (safe no-op if already exists)
            client.create_user(emp, name)
            print(f"[SIGNAL] ✅ VISITOR user ensured on {door.name}")
            
            # Bind card to VISITOR
            client.bind_card(emp, instance.card_no)
            print(f"[SIGNAL] ✅ Card {instance.card_no} bound to VISITOR on {door.name}")
            
            print(f"[SIGNAL] 🎉 SUCCESS: Card {instance.card_no} bound to VISITOR on {door.name}")
            print(f"[SIGNAL] 📋 Details: User=VISITOR, Card={instance.card_no}, Appointment={instance.id}")
            
        except Exception as e:
            print(f"[SIGNAL] ❌ FAILED on {door.name}: {e}")
            import traceback
            traceback.print_exc()

print("[SIGNALS] Simple working signals loaded - will create users in terminals!")
print("[SIGNALS] Test signal added - should see 🔔 [TEST] messages!")
