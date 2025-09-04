from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from medical_access.models import Appointment, Door, AccessEvent
from controller.hik_client import HikClient

class Command(BaseCommand):
    help = "Cleanup expired temporary passes and revoke from all doors via ISAPI."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without making changes'
        )
        parser.add_argument(
            '--force-all',
            action='store_true',
            help='Also clean up USED passes older than 7 days'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force_all = options['force_all']
        
        now = timezone.now()
        
        if dry_run:
            self.stdout.write("🔍 DRY RUN - No changes will be made")
        
        self.stdout.write("=" * 60)
        self.stdout.write(f"🧹 Cleanup started at {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. Find expired ACTIVE appointments
        expired_appointments = Appointment.objects.filter(
            status=Appointment.Status.ACTIVE,
            valid_to__lt=now
        )
        
        self.stdout.write(f"📋 Found {expired_appointments.count()} expired ACTIVE appointments")
        
        # 2. Find old USED appointments (if force_all)
        old_used_appointments = []
        if force_all:
            week_ago = now - timedelta(days=7)
            old_used_appointments = Appointment.objects.filter(
                status=Appointment.Status.USED,
                used_at__lt=week_ago
            )
            self.stdout.write(f"📋 Found {old_used_appointments.count()} old USED appointments (>7 days)")
        
        all_appointments_to_clean = list(expired_appointments) + list(old_used_appointments)
        
        if not all_appointments_to_clean:
            self.stdout.write("✨ No appointments need cleanup")
            return
        
        # 3. Get all doors for revocation
        doors = list(Door.objects.all())
        
        if not doors:
            self.stdout.write("⚠️  No doors configured - skipping ISAPI revocation")
        
        cleaned_count = 0
        revoked_count = 0
        
        for appointment in all_appointments_to_clean:
            card_no = appointment.card_no
            patient_name = appointment.patient.full_name if appointment.patient else "Unknown"
            
            self.stdout.write(f"🔄 Processing: {card_no} ({patient_name})")
            
            if not dry_run:
                # Mark as expired/revoked
                if appointment.status == Appointment.Status.ACTIVE:
                    appointment.status = Appointment.Status.EXPIRED
                    appointment.save()
                
                # Revoke from all doors via ISAPI
                door_success = 0
                for door in doors:
                    try:
                        client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
                        client.delete_user(card_no)
                        door_success += 1
                        self.stdout.write(f"   ✅ {door.name}: User deleted")
                    except Exception as e:
                        self.stderr.write(f"   ❌ {door.name}: Failed to delete user - {e}")
                
                if door_success > 0:
                    revoked_count += 1
                
                # Log cleanup event
                AccessEvent.objects.create(
                    card_no=card_no,
                    source=AccessEvent.Source.API,
                    result=AccessEvent.Result.DENY,
                    reason=f'Cleanup: expired appointment revoked from {door_success} doors',
                    appointment=appointment,
                    operator='System Cleanup'
                )
                
                cleaned_count += 1
            else:
                self.stdout.write(f"   🔍 Would clean: {card_no}")
        
        self.stdout.write("=" * 60)
        
        if dry_run:
            self.stdout.write(f"📊 DRY RUN SUMMARY:")
            self.stdout.write(f"   • Would clean {len(all_appointments_to_clean)} appointments")
            self.stdout.write(f"   • Would revoke from {len(doors)} doors")
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ CLEANUP COMPLETE:"))
            self.stdout.write(f"   • Cleaned {cleaned_count} appointments")
            self.stdout.write(f"   • Revoked {revoked_count} from doors")
            
        self.stdout.write(f"\n💡 Schedule this command to run hourly:")
        self.stdout.write(f"   crontab: 0 * * * * cd {self.get_project_root()} && python manage.py cleanup_expired_passes")
        
    def get_project_root(self):
        """Get the project root directory"""
        import os
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
