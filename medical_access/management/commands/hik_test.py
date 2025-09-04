from django.core.management.base import BaseCommand
from requests.auth import HTTPDigestAuth
import requests
from medical_access.models import Door

class Command(BaseCommand):
    help = "Test ISAPI auth for a specific door (reads IP/user/pass from DB)."

    def add_arguments(self, parser):
        parser.add_argument("--door-id", type=int, required=True)

    def handle(self, *args, **opts):
        try:
            d = Door.objects.get(id=opts["door_id"])
        except Door.DoesNotExist:
            self.stderr.write(f"Door with id {opts['door_id']} not found.")
            return

        base = f"http://{d.terminal_ip}"
        auth = HTTPDigestAuth(d.terminal_username, d.terminal_password)

        self.stdout.write(f"Testing door: {d.name} ({d.terminal_ip})")
        self.stdout.write(f"Username: {d.terminal_username}")
        self.stdout.write("=" * 50)

        for path in ["/ISAPI/System/status", "/ISAPI/AccessControl/AcsEvent?format=json"]:
            url = base + path
            try:
                r = requests.get(url, auth=auth, timeout=8, verify=False)
                self.stdout.write(f"{d.name}: {path} -> {r.status_code}")
                
                if r.status_code == 200:
                    self.stdout.write(self.style.SUCCESS(f"✅ SUCCESS: {path}"))
                elif r.status_code == 401:
                    self.stdout.write(self.style.ERROR(f"❌ UNAUTHORIZED: {path} - Check credentials or account lockout"))
                else:
                    self.stdout.write(self.style.WARNING(f"⚠️  UNEXPECTED: {path} - Status {r.status_code}"))
                    
            except Exception as e:
                self.stderr.write(f"{d.name}: {path} -> ERROR {e}")
                self.stdout.write(self.style.ERROR(f"❌ NETWORK ERROR: {path} - {e}"))

        self.stdout.write("=" * 50)
        self.stdout.write("Test completed!")
