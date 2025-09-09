from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Appointment

@receiver(post_save, sender=Appointment)
def on_appt_created(sender, instance: Appointment, created, **kwargs):
    """Remote-Only Mode: No card provisioning - verification happens remotely"""
    if not created or not instance.qr_code:
        return
    
    # Remote-Only Mode: Cards are not stored on terminals
    # Verification happens via remote API calls only
    import logging
    logger = logging.getLogger(__name__)
