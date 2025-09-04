from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from medical_access.models import Appointment, Patient, Door
from controller.hik_client import HikClient

class Command(BaseCommand):
    help = "Bulk cleanup operations for temporary passes, appointments, and patients"

    def add_arguments(self, parser):
        parser.add_argument(
            '--operation',
            choices=['cleanup_appointments', 'cleanup_patients', 'all'],
            default='all',
            help='Operation to perform'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force deletion even with dependencies'
        )

    def handle(self, *args, **options):
        operation = options['operation']
        dry_run = options['dry_run']
        force = options['force']
        
        if dry_run:
            self.stdout.write("🔍 DRY RUN - No changes will be made")
        
        self.stdout.write("=" * 60)
        self.stdout.write(f"🧹 Bulk cleanup started at {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if operation in ['cleanup_appointments', 'all']:
            self.cleanup_appointments(dry_run, force)
        
        if operation in ['cleanup_patients', 'all']:
            self.cleanup_patients(dry_run, force)
        
        self.stdout.write("=" * 60)
        self.stdout.write("✨ Bulk cleanup completed")

    def cleanup_appointments(self, dry_run, force):
        """Clean up old appointments"""
        self.stdout.write("\n📅 Cleaning up appointments...")
        
        # Find old expired/used appointments
        now = timezone.now()
        old_appointments = Appointment.objects.filter(
            status__in=['expired', 'used'],
            valid_to__lt=now - timedelta(days=7)
        )
        
        self.stdout.write(f"📋 Found {old_appointments.count()} old appointments to clean up")
        
        if not dry_run:
            deleted_count = 0
            
            for appointment in old_appointments:
                self.stdout.write(f"   🗑️  Deleting appointment {appointment.id}")
                
                # Revoke from all doors first
                doors = list(Door.objects.all())
                for door in doors:
                    try:
                        client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
                        client.delete_user(appointment.card_no)
                        self.stdout.write(f"      ✅ {door.name}: User deleted")
                    except Exception as e:
                        self.stderr.write(f"      ❌ {door.name}: Failed - {e}")
                
                appointment.delete()
                deleted_count += 1
            
            self.stdout.write(f"   ✨ Cleaned up {deleted_count} appointments")
        else:
            for appointment in old_appointments:
                self.stdout.write(f"   🔍 Would delete: {appointment.id}")

    def cleanup_patients(self, dry_run, force):
        """Clean up patients without appointments"""
        self.stdout.write("\n👤 Cleaning up patients...")
        
        # Find patients without appointments
        patients_without_appointments = Patient.objects.filter(appointments__isnull=True)
        
        self.stdout.write(f"📋 Found {patients_without_appointments.count()} patients without appointments")
        
        if not dry_run:
            deleted_count = 0
            
            for patient in patients_without_appointments:
                self.stdout.write(f"   🗑️  Deleting patient {patient.full_name}")
                patient.delete()
                deleted_count += 1
            
            self.stdout.write(f"   ✨ Cleaned up {deleted_count} patients")
        else:
            for patient in patients_without_appointments:
                self.stdout.write(f"   🔍 Would delete: {patient.full_name}")
