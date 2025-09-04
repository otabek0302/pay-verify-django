from django.core.management.base import BaseCommand
from requests.auth import HTTPDigestAuth
import requests
from medical_access.models import Door

class Command(BaseCommand):
    help = "Comprehensive discovery of available ISAPI endpoints on Hikvision devices."

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

        self.stdout.write(f"🔍 Comprehensive endpoint discovery for: {door.name} ({door.terminal_ip})")
        self.stdout.write(f"Model: DS-K1T342MWX (Firmware V3.16.1)")
        self.stdout.write("=" * 70)

        # Comprehensive list of possible Hikvision ISAPI endpoints
        endpoints = [
            # System endpoints
            "/ISAPI/System/status",
            "/ISAPI/System/deviceInfo",
            "/ISAPI/System/deviceInfo?format=json",
            "/ISAPI/System/capabilities",
            "/ISAPI/System/capabilities?format=json",
            "/ISAPI/System/time",
            "/ISAPI/System/time?format=json",
            
            # Access Control - Standard
            "/ISAPI/AccessControl/UserInfo/Record",
            "/ISAPI/AccessControl/UserInfo/Record?format=json",
            "/ISAPI/AccessControl/UserInfo/SetUp",
            "/ISAPI/AccessControl/UserInfo/SetUp?format=json",
            "/ISAPI/AccessControl/UserInfo",
            "/ISAPI/AccessControl/UserInfo?format=json",
            
            # Access Control - Cards
            "/ISAPI/AccessControl/CardInfo/Record",
            "/ISAPI/AccessControl/CardInfo/Record?format=json",
            "/ISAPI/AccessControl/CardInfo/SetUp",
            "/ISAPI/AccessControl/CardInfo/SetUp?format=json",
            "/ISAPI/AccessControl/CardInfo",
            "/ISAPI/AccessControl/CardInfo?format=json",
            
            # Access Control - Authorization
            "/ISAPI/AccessControl/Authorization",
            "/ISAPI/AccessControl/Authorization?format=json",
            "/ISAPI/AccessControl/AUTHORIZATION/SetUp",
            "/ISAPI/AccessControl/AUTHORIZATION/SetUp?format=json",
            
            # Access Control - Events
            "/ISAPI/AccessControl/AcsEvent",
            "/ISAPI/AccessControl/AcsEvent?format=json",
            "/ISAPI/AccessControl/Event",
            "/ISAPI/AccessControl/Event?format=json",
            
            # Access Control - Alternative paths
            "/ISAPI/AccessControl/UserManage/UserInfo/Record",
            "/ISAPI/AccessControl/UserManage/UserInfo/Record?format=json",
            "/ISAPI/AccessControl/CardManage/CardInfo/Record",
            "/ISAPI/AccessControl/CardManage/CardInfo/Record?format=json",
            
            # Door Control
            "/ISAPI/AccessControl/DoorControl",
            "/ISAPI/AccessControl/DoorControl?format=json",
            "/ISAPI/AccessControl/Door",
            "/ISAPI/AccessControl/Door?format=json",
            
            # Configuration
            "/ISAPI/AccessControl/Configuration",
            "/ISAPI/AccessControl/Configuration?format=json",
        ]

        working_endpoints = []
        get_endpoints = []
        post_endpoints = []
        put_endpoints = []

        for endpoint in endpoints:
            url = base + endpoint
            
            # Test GET
            try:
                r = requests.get(url, auth=auth, timeout=8, verify=False)
                if r.status_code == 200:
                    self.stdout.write(self.style.SUCCESS(f"✅ GET  {endpoint} -> 200 OK"))
                    working_endpoints.append(endpoint)
                    get_endpoints.append(endpoint)
                elif r.status_code == 405:
                    self.stdout.write(f"⚠️  GET  {endpoint} -> 405 Method Not Allowed")
                elif r.status_code == 404:
                    self.stdout.write(f"🔍 GET  {endpoint} -> 404 Not Found")
                elif r.status_code == 401:
                    self.stdout.write(self.style.ERROR(f"❌ GET  {endpoint} -> 401 UNAUTHORIZED"))
                else:
                    self.stdout.write(f"❓ GET  {endpoint} -> {r.status_code}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"💥 GET  {endpoint} -> ERROR: {e}"))

            # Test POST for specific endpoints
            if "Record" in endpoint or "SetUp" in endpoint:
                try:
                    test_payload = {"test": "data"}
                    r = requests.post(url, json=test_payload, auth=auth, timeout=8, verify=False)
                    if r.status_code in [200, 201]:
                        self.stdout.write(self.style.SUCCESS(f"✅ POST {endpoint} -> {r.status_code} OK"))
                        post_endpoints.append(endpoint)
                    elif r.status_code == 405:
                        self.stdout.write(f"⚠️  POST {endpoint} -> 405 Method Not Allowed")
                    elif r.status_code == 400:
                        self.stdout.write(f"📝 POST {endpoint} -> 400 Bad Request (expects different payload)")
                    elif r.status_code == 404:
                        pass  # Already logged from GET
                    else:
                        self.stdout.write(f"❓ POST {endpoint} -> {r.status_code}")
                except Exception:
                    pass

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"📊 SUMMARY:")
        self.stdout.write(f"   Working GET endpoints: {len(get_endpoints)}")
        self.stdout.write(f"   Working POST endpoints: {len(post_endpoints)}")
        
        if working_endpoints:
            self.stdout.write(f"\n📋 ALL WORKING ENDPOINTS:")
            for ep in working_endpoints:
                self.stdout.write(f"   • {ep}")
        else:
            self.stdout.write(self.style.WARNING("\n⚠️  No access control endpoints found!"))
            self.stdout.write("💡 This device may need:")
            self.stdout.write("   • Access Control mode enabled in web UI")
            self.stdout.write("   • Firmware update")
            self.stdout.write("   • Different API version")
