from django.core.management.base import BaseCommand
from requests.auth import HTTPDigestAuth
import requests

class Command(BaseCommand):
    help = "Debug Hikvision device endpoints and capabilities"

    def add_arguments(self, parser):
        parser.add_argument("--ip", type=str, required=True)
        parser.add_argument("--username", type=str, required=True)
        parser.add_argument("--password", type=str, required=True)

    def handle(self, *args, **options):
        ip = options["ip"]
        username = options["username"]
        password = options["password"]
        
        base_url = f"http://{ip}"
        auth = HTTPDigestAuth(username, password)
        
        self.stdout.write(f"Testing device at {base_url}")
        self.stdout.write("=" * 50)
        
        # Test basic connectivity
        test_endpoints = [
            "/ISAPI/System/deviceInfo",
            "/ISAPI/System/status",
            "/ISAPI/System/version",
            "/ISAPI/AccessControl/UserInfo/Record",
            "/ISAPI/AccessControl/UserInfo/Record?format=json",
            "/ISAPI/AccessControl/CardInfo/Record",
            "/ISAPI/AccessControl/CardInfo/Record?format=json",
            "/ISAPI/AccessControl/Authorization",
            "/ISAPI/AccessControl/Authorization?format=json",
            "/ISAPI/AccessControl/AcsEvent",
            "/ISAPI/AccessControl/AcsEvent?format=json",
        ]
        
        for endpoint in test_endpoints:
            try:
                url = base_url + endpoint
                r = requests.get(url, auth=auth, timeout=10, verify=False)
                self.stdout.write(f"{endpoint:<50} {r.status_code}")
                
                if r.status_code == 200:
                    # Try to get some content info
                    content = r.text[:100]
                    if "xml" in content.lower():
                        self.stdout.write(f"  -> XML response")
                    elif "json" in content.lower():
                        self.stdout.write(f"  -> JSON response")
                    else:
                        self.stdout.write(f"  -> Text response")
                        
            except Exception as e:
                self.stdout.write(f"{endpoint:<50} ERROR: {e}")
        
        self.stdout.write("=" * 50)
        self.stdout.write("Testing POST operations...")
        
        # Test POST operations
        post_tests = [
            ("/ISAPI/AccessControl/UserInfo/Record", {"UserInfo": {"employeeNo": "TEST123", "name": "Test User"}}),
            ("/ISAPI/AccessControl/UserInfo/Record?format=json", {"UserInfo": {"employeeNo": "TEST123", "name": "Test User"}}),
        ]
        
        for endpoint, payload in post_tests:
            try:
                url = base_url + endpoint
                if "json" in endpoint:
                    r = requests.post(url, json=payload, auth=auth, timeout=10, verify=False)
                else:
                    r = requests.post(url, data=str(payload), auth=auth, timeout=10, verify=False)
                
                self.stdout.write(f"POST {endpoint:<40} {r.status_code}")
                if r.status_code != 200:
                    self.stdout.write(f"  -> Response: {r.text[:200]}")
                    
            except Exception as e:
                self.stdout.write(f"POST {endpoint:<40} ERROR: {e}")
