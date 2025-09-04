from django.core.management.base import BaseCommand
from requests.auth import HTTPDigestAuth
import requests
from medical_access.models import Door

class Command(BaseCommand):
    help = "Discover available ISAPI endpoints on Hikvision devices."

    def add_arguments(self, parser):
        parser.add_argument("--door-id", type=int, required=True)

    def handle(self, *args, **opts):
        try:
            door = Door.objects.get(id=opts["door_id"])
        except Door.DoesNotExist:
            self.stderr.write(f"Door with id {opts['door_id']} not found.")
            return

        base = f"http://{door.terminal_ip}"
        auth = HTTPDigestAuth(door.terminal_username, door.terminal_password)

        self.stdout.write(f"🔍 Discovering endpoints for: {door.name} ({door.terminal_ip})")
        self.stdout.write(f"Username: {door.terminal_username}")
        self.stdout.write("=" * 60)

        # Common Hikvision ISAPI endpoints to test
        endpoints = [
            "/ISAPI/System/status",
            "/ISAPI/System/deviceInfo",
            "/ISAPI/System/deviceInfo?format=json",
            "/ISAPI/System/version",
            "/ISAPI/System/version?format=json",
            "/ISAPI/AccessControl/UserInfo/Record?format=json",
            "/ISAPI/AccessControl/CardInfo/Record?format=json",
            "/ISAPI/AccessControl/AcsEvent?format=json",
            "/ISAPI/AccessControl/AcsEvent",
            "/ISAPI/AccessControl/AUTHORIZATION/SetUp?format=json",
            "/ISAPI/AccessControl/Authorization?format=json",
            "/ISAPI/System/network",
            "/ISAPI/System/network?format=json"
        ]

        working_endpoints = []
        auth_working = False

        for endpoint in endpoints:
            url = base + endpoint
            try:
                r = requests.get(url, auth=auth, timeout=8, verify=False)
                
                if r.status_code == 200:
                    self.stdout.write(self.style.SUCCESS(f"✅ {endpoint} -> 200 OK"))
                    working_endpoints.append(endpoint)
                    auth_working = True
                elif r.status_code == 401:
                    self.stdout.write(self.style.ERROR(f"❌ {endpoint} -> 401 UNAUTHORIZED"))
                elif r.status_code == 404:
                    self.stdout.write(f"🔍 {endpoint} -> 404 Not Found")
                elif r.status_code == 405:
                    self.stdout.write(f"⚠️  {endpoint} -> 405 Method Not Allowed")
                else:
                    self.stdout.write(f"❓ {endpoint} -> {r.status_code}")
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"💥 {endpoint} -> ERROR: {e}"))

        self.stdout.write("\n" + "=" * 60)
        
        if auth_working:
            self.stdout.write(self.style.SUCCESS("🎉 Authentication is working!"))
            if working_endpoints:
                self.stdout.write(f"📋 Working endpoints ({len(working_endpoints)}):")
                for ep in working_endpoints:
                    self.stdout.write(f"   • {ep}")
            else:
                self.stdout.write("⚠️  No endpoints returned 200, but auth is working")
        else:
            self.stdout.write(self.style.ERROR("❌ Authentication failed - check credentials"))
        
        self.stdout.write("\n💡 Next steps:")
        if auth_working:
            self.stdout.write("   • Your credentials are correct")
            self.stdout.write("   • Update HikClient to use working endpoints")
        else:
            self.stdout.write("   • Check username/password in Django Admin")
            self.stdout.write("   • Verify device isn't locked out")
            self.stdout.write("   • Try HTTPS instead of HTTP")
