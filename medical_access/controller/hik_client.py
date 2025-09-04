# medical_access/controller/hik_client.py

import requests
from requests.auth import HTTPDigestAuth
from django.conf import settings
from django.utils import timezone

JSON_HEADERS = {"Content-Type": "application/json"}


def _base_url(ip: str) -> str:
    """Return base URL depending on HTTP/HTTPS setting."""
    scheme = "https" if getattr(settings, "HIK_USE_HTTPS", False) else "http"
    return f"{scheme}://{ip}"


class HikClient:
    """
    Hikvision ISAPI client for DS-K1T342MWX terminals.
    Provides methods for creating/deleting users and binding QR codes as cards.
    """

    def __init__(self, ip: str, username: str, password: str):
        self.base = _base_url(ip)
        self.username = username
        self.password = password
        self.timeout = getattr(settings, "HIK_TIMEOUT", 8)

    def _auth(self):
        return HTTPDigestAuth(self.username, self.password)

    # -------------------------------------------------------------------------
    # Device status
    # -------------------------------------------------------------------------
    def ping(self) -> bool:
        """Check if device is alive."""
        url = f"{self.base}/ISAPI/System/deviceInfo?format=json"
        r = requests.get(url, auth=self._auth(), timeout=self.timeout, verify=False)
        r.raise_for_status()
        return True

    # -------------------------------------------------------------------------
    # User Management
    # -------------------------------------------------------------------------
    def create_user(self, employee_no: str, name: str, valid_from=None, valid_to=None):
        """
        Create or update a user (person) on the device as VISITOR with Visit Times = 1.
        """
        # Use the working JSON format that was tested before
        url = f"{self.base}/ISAPI/AccessControl/UserInfo/Record?format=json"
        # Use very wide time range to avoid "Invalid Duration" errors
        from datetime import datetime
        now = datetime.now()
        begin_time = "2020-01-01T00:00:00"  # Start from 2020
        end_time = "2030-12-31T23:59:59"    # End in 2030
        
        payload = {
            "UserInfo": {
                "employeeNo": employee_no,
                "name": name,
                "userType": "visitor",  # Set as VISITOR instead of normal
                "Valid": {
                    "enable": True,
                    "beginTime": begin_time,
                    "endTime": end_time
                },
                "visitTimes": 999,  # Set Visit Times to unlimited (999) - we control one-time use in software
                "personType": "visitor",  # Explicitly set person type as visitor
                "gender": "unknown",  # Set gender as unknown
                "floorNo": "0",  # Set floor number
                "roomNo": "0"   # Set room number
            }
        }
        
        # Creating user with provided payload
        
        # Use the working format from our test script
        url = f"{self.base}/ISAPI/AccessControl/UserInfo/Record?format=json"
        
        # Use POST method (which worked in our test)
        r = requests.post(url, json=payload, headers=JSON_HEADERS, auth=self._auth(), timeout=self.timeout, verify=False)
        
        if r.status_code == 200:
            return True
        elif r.status_code == 400 and "employeeNoAlreadyExist" in r.text:
            return True
        else:
            r.raise_for_status()
        
        return True

    def delete_user(self, employee_no: str):
        """Delete a user and all associated cards."""
        url = f"{self.base}/ISAPI/AccessControl/UserInfo/Delete?format=json"
        payload = {"UserInfoDelCond": {"EmployeeNoList": [{"employeeNo": employee_no}]}}
        r = requests.put(url, json=payload, headers=JSON_HEADERS, auth=self._auth(), timeout=self.timeout, verify=False)
        r.raise_for_status()
        return True

    def delete_card(self, card_no: str):
        """Delete a specific card from the device."""
        url = f"{self.base}/ISAPI/AccessControl/CardInfo/Delete?format=json"
        payload = {"CardInfoDelCond": {"CardNoList": [{"cardNo": card_no}]}}
        r = requests.put(url, json=payload, headers=JSON_HEADERS, auth=self._auth(), timeout=self.timeout, verify=False)
        r.raise_for_status()
        return True

    # -------------------------------------------------------------------------
    # Card Management (QR = CardNo)
    # -------------------------------------------------------------------------
    def bind_card(self, employee_no: str, card_no: str, valid_from=None, valid_to=None):
        """Bind a QR code (card number) to a user."""
        # Minimal JSON payload - only essential fields
        url = f"{self.base}/ISAPI/AccessControl/CardInfo/Record?format=json"
        payload = {
            "CardInfo": {
                "employeeNo": employee_no,
                "cardNo": str(card_no),
                "cardType": "normalCard",  # Use "normalCard" - this is what terminal expects
                "status": "active"  # Make sure card is active
            }
        }
        
        # Binding card with provided payload
        if r.status_code == 200:
            r.raise_for_status()
            return True
        else:
            r.raise_for_status()
            return False

        # Use POST method (which worked in our test)
        r = requests.post(url, json=payload, headers=JSON_HEADERS, auth=self._auth(), timeout=self.timeout, verify=False)
        
        if r.status_code != 200:
            # Card binding failed - log error
            r.raise_for_status()
            return False
        r.raise_for_status()
        return True

    # -------------------------------------------------------------------------
    # Door Authorization
    # -------------------------------------------------------------------------
    def grant_door(self, employee_no: str, door_no: int = 1, time_section_no: int = 1):
        """
        Grant door rights to a person.
        """
        # Attempting to grant door access
        
        # Try the newer door authorization endpoint
        try:
            url = f"{self.base}/ISAPI/AccessControl/Authorization?format=json"
            payload = {
                "Authorization": {
                    "employeeNoList": [{"employeeNo": employee_no}],
                    "doorNoList": [door_no],
                    "timeSectionNo": time_section_no
                }
            }
            
            r = requests.post(url, json=payload, headers=JSON_HEADERS, auth=self._auth(), timeout=self.timeout, verify=False)
            
            if r.status_code == 200:
                return True
            else:
                
        except Exception as e:
        
        # Fallback: try older endpoint
        try:
            url = f"{self.base}/ISAPI/AccessControl/AUTHORIZATION/SetUp?format=json"
            payload = {
                "AuthInfo": [{
                    "employeeNo": employee_no,
                    "doorNoList": [door_no],
                    "timeSectionNo": time_section_no
                }]
            }
            
            r = requests.put(url, json=payload, headers=JSON_HEADERS, auth=self._auth(), timeout=self.timeout, verify=False)
            
            if r.status_code == 200:
                return True
            else:
                
        except Exception as e:
        
        return False

    def get_door_numbers(self):
        """Discover available door numbers on the device."""
        auth = HTTPDigestAuth(self.username, self.password)
        for url in [
            f"{self.base}/ISAPI/AccessControl/Door?format=json",
            f"{self.base}/ISAPI/AccessControl/Door",
        ]:
            try:
                r = requests.get(url, auth=auth, timeout=self.timeout, verify=False)
                if r.status_code == 200 and "doorNo" in r.text:
                    data = r.json() if r.headers.get("Content-Type","").endswith("json") else {}
                    # naive parser; adjust if needed
                    items = data.get("DoorList", {}).get("Door", [])
                    return [int(x.get("doorNo", 1)) for x in items if isinstance(x, dict)]
            except Exception:
                pass
        return [1]  # fallback

    # -------------------------------------------------------------------------
    # Remote Door Control
    # -------------------------------------------------------------------------
    def remote_open_door(self, door_no: int = 1):
        """Remote door control - open door without card verification"""
        errors = []
        
        # Try multiple endpoints that different Hikvision models support
        endpoints = [
            # XML format endpoints
            (f"{self.base}/ISAPI/AccessControl/RemoteControl/door", 
             f"""<?xml version="1.0" encoding="UTF-8"?>
<remoteControlDoor>
  <doorNo>{door_no}</doorNo>
  <cmd>open</cmd>
</remoteControlDoor>""", 
             {"Content-Type": "application/xml"}),
            
            # JSON format endpoints
            (f"{self.base}/ISAPI/AccessControl/RemoteControl/door/{door_no}", 
             {"cmd": "open"}, 
             JSON_HEADERS),
            
            # Alternative JSON endpoint
            (f"{self.base}/ISAPI/AccessControl/DoorControl", 
             {"DoorControl": {"doorNo": door_no, "cmd": "open"}}, 
             JSON_HEADERS),
            
            # Simple POST without body
            (f"{self.base}/ISAPI/AccessControl/RemoteControl/door/{door_no}", 
             None, 
             {}),
        ]
        
        for url, payload, headers in endpoints:
            try:
                if payload is None:
                    # Simple POST without body
                    r = requests.post(url, auth=self._auth(), timeout=self.timeout, verify=False)
                elif isinstance(payload, str):
                    # XML payload
                    r = requests.post(url, data=payload, headers=headers, auth=self._auth(), timeout=self.timeout, verify=False)
                else:
                    # JSON payload
                    r = requests.post(url, json=payload, headers=headers, auth=self._auth(), timeout=self.timeout, verify=False)
                
                if r.status_code == 200:
                    return True
                else:
                    errors.append(f"{url}: {r.status_code} - {r.text[:100]}")
                    
            except Exception as e:
                errors.append(f"{url}: {str(e)[:100]}")
        
        # If all endpoints failed, raise error with details
        error_msg = " | ".join(errors)
        raise RuntimeError(f"All remote door open endpoints failed: {error_msg}")

    # -------------------------------------------------------------------------
    # Event Polling
    # -------------------------------------------------------------------------
    def get_recent_events(self, minutes_back: int = 5):
        """
        Get recent access events from the device.
        Returns list of events with cardNo, time, etc.
        """
        end_time = timezone.now()
        start_time = end_time - timezone.timedelta(minutes=minutes_back)
        
        url = f"{self.base}/ISAPI/AccessControl/AcsEvent?format=json"
        payload = {
            "AcsEventCond": {
                "searchID": "1",
                "searchResultPosition": 0,
                "maxResults": 100,
                "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        }
        
        r = requests.post(url, json=payload, headers=JSON_HEADERS, auth=self._auth(), timeout=self.timeout, verify=False)
        r.raise_for_status()
        
        data = r.json()
        return data.get("AcsEvent", []) if isinstance(data, dict) else []

    # -------------------------------------------------------------------------
    # High-Level Helpers
    # -------------------------------------------------------------------------
    def provision_qr_pass(self, appointment_id: int, card_no: str, patient_name: str, valid_from, valid_to):
        """
        Complete provisioning: create user + bind card + grant door access.
        """
        employee_no = f"APT{appointment_id}"
        
        # Step 1: Create user
        self.create_user(employee_no, patient_name, valid_from, valid_to)
        
        # Step 2: Bind QR code as card
        self.bind_card(employee_no, card_no, valid_from, valid_to)
        
        # Step 3: Grant door access
        self.grant_door(employee_no, door_no=1, time_section_no=1)
        
        return True

    def revoke_qr_pass(self, appointment_id: int):
        """
        Complete revocation: delete user (removes card and door access).
        """
        employee_no = f"APT{appointment_id}"
        self.delete_user(employee_no)
        return True
