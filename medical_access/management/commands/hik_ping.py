from django.core.management.base import BaseCommand
from requests.auth import HTTPDigestAuth
import requests
from medical_access.models import Door

class Command(BaseCommand):
    help = "Test ISAPI auth for all doors (quick fleet status check)."

    def handle(self, *args, **opts):
        doors = Door.objects.all()
        
        if not doors:
            self.stdout.write("No doors configured.")
            return

        self.stdout.write(f"Testing {doors.count()} door(s)...")
        self.stdout.write("=" * 60)

        for door in doors:
            self.stdout.write(f"\n🔍 Testing: {door.name} ({door.terminal_ip})")
            self.stdout.write(f"   Username: {door.terminal_username}")
            
            base = f"http://{door.terminal_ip}"
            auth = HTTPDigestAuth(door.terminal_username, door.terminal_password)

            # Test system status
            try:
                r = requests.get(f"{base}/ISAPI/System/status", auth=auth, timeout=8, verify=False)
                if r.status_code == 200:
                    self.stdout.write(self.style.SUCCESS(f"   ✅ System Status: OK"))
                elif r.status_code == 401:
                    self.stdout.write(self.style.ERROR(f"   ❌ System Status: UNAUTHORIZED"))
                else:
                    self.stdout.write(self.style.WARNING(f"   ⚠️  System Status: {r.status_code}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ System Status: ERROR - {e}"))

            # Test events endpoint
            try:
                r = requests.get(f"{base}/ISAPI/AccessControl/AcsEvent?format=json", auth=auth, timeout=8, verify=False)
                if r.status_code == 200:
                    self.stdout.write(self.style.SUCCESS(f"   ✅ Events Endpoint: OK"))
                elif r.status_code == 401:
                    self.stdout.write(self.style.ERROR(f"   ❌ Events Endpoint: UNAUTHORIZED"))
                else:
                    self.stdout.write(self.style.WARNING(f"   ⚠️  Events Endpoint: {r.status_code}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ Events Endpoint: ERROR - {e}"))

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("Fleet test completed!")
