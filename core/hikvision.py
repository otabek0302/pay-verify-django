import requests
from requests.auth import HTTPDigestAuth
from django.conf import settings

DEFAULT_TIMEOUT = getattr(settings, "PAYVERIFY_TERMINAL_TIMEOUT", 5)
JSON_HEADERS = {"Content-Type": "application/json"}
XML_HEADERS = {"Content-Type": "application/xml"}

class HikTerminal:
    """
    Minimal ISAPI client for Hikvision access terminals (DS-K1T342MFWX-E1).
    Uses HTTP Digest Auth with JSON format.
    """
    def __init__(self, host: str, username: str, password: str, timeout=None, port: int = 80, use_xml: bool = True):
        self.base = f"http://{host}" if port in (80, None) else f"http://{host}:{port}"
        self.auth = HTTPDigestAuth(username, password)
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.use_xml = use_xml  # Default to XML format
        self.h_xml = XML_HEADERS  # XML headers for door control

    # ---- Basic info / health
    def device_info(self) -> str:
        r = requests.get(f"{self.base}/ISAPI/System/deviceInfo", auth=self.auth, timeout=self.timeout)
        r.raise_for_status()
        return r.text

    def status(self) -> str:
        r = requests.get(f"{self.base}/ISAPI/System/status", auth=self.auth, timeout=self.timeout)
        r.raise_for_status()
        return r.text

    # ---- Door control
    def open_door(self, door_no: int = 1, cmd: str = "open") -> str:
        # cmd can be: open / close / stop
        xml = f"<RemoteControlDoor><cmd>{cmd}</cmd></RemoteControlDoor>"
        r = requests.put(
            f"{self.base}/ISAPI/AccessControl/RemoteControl/door/{door_no}",
            data=xml, headers=self.h_xml, auth=self.auth, timeout=self.timeout
        )
        r.raise_for_status()
        return r.text

    # ---- Event stream (QR/Card/Face/door events)
    def alert_stream(self):
        """
        Returns a streaming Response for /ISAPI/Event/notification/alertStream.
        Caller must iterate over r.iter_content(...) or r.iter_lines(...).
        """
        r = requests.get(
            f"{self.base}/ISAPI/Event/notification/alertStream",
            auth=self.auth, stream=True, timeout=(5, 60)
        )
        r.raise_for_status()
        return r

    # ---- VISITOR upsert (JSON format)
    def user_upsert_json(self, employee_no: str, name: str = "Visitor") -> requests.Response:
        """Create/update VISITOR user (wide validity; JSON; POST)."""
        url = f"{self.base}/ISAPI/AccessControl/UserInfo/Record?format=json"
        payload = {
            "UserInfo": {
                "employeeNo": employee_no,
                "name": name,
                "userType": "normal",
                "status": "active",
                # keep validity wide to avoid duration errors
                "Valid": {
                    "enable": True,
                    "beginTime": "2020-01-01T00:00:00",
                    "endTime":   "2030-12-31T23:59:59"
                },
                "doorRight": "1"
            }
        }
        r = requests.post(url, json=payload, headers=JSON_HEADERS,
                          auth=self.auth, timeout=self.timeout, verify=False)
        # Treat "already exists" as success
        if r.status_code == 400 and "employeeNoAlreadyExist" in r.text:
            return r
        r.raise_for_status()
        return r

    # ---- Card upsert for VISITOR (JSON format)
    def card_upsert_json(self, employee_no: str, card_no: str, valid_from: str = None, valid_to: str = None) -> requests.Response:
        """Bind card number to user (JSON; POST)."""
        url = f"{self.base}/ISAPI/AccessControl/CardInfo/Record?format=json"
        payload = {
            "CardInfo": {
                "employeeNo": employee_no,
                "cardNo": str(card_no),     # IMPORTANT: send as string
                "cardType": "normalCard",
                "status": "active",
            }
        }
        
        # Add validity window if provided (some firmwares require it)
        if valid_from and valid_to:
            payload["CardInfo"]["Valid"] = {
                "enable": True,
                "beginTime": valid_from,
                "endTime": valid_to
            }
        
        r = requests.post(url, json=payload, headers=JSON_HEADERS,
                          auth=self.auth, timeout=self.timeout, verify=False)
        # Treat "already exists" as success
        if r.status_code == 400 and "cardNoAlreadyExist" in r.text:
            return r
        r.raise_for_status()
        return r

    # ---- Card disable (soft-delete via status/validity update)
    def card_disable_json(self, employee_no: str, card_no: str, end_time_iso: str = None, status: str = "lost"):
        """
        Soft-delete: make the card completely unusable by status/validity update.
        Works on DS-K1T342* builds that reject CardInfo/Delete.
        """
        url = f"{self.base}/ISAPI/AccessControl/CardInfo/Record?format=json"
        payload = {
            "CardInfo": {
                "employeeNo": employee_no,
                "cardNo": str(card_no),
                "cardType": "normalCard",
                "status": status,  # "lost" is more restrictive than "inactive"
                "doorRight": "0"  # Remove all door rights
            }
        }
        if end_time_iso:
            payload["CardInfo"]["Valid"] = {
                "enable": True,
                "beginTime": "2020-01-01T00:00:00",
                "endTime": end_time_iso
            }
        r = requests.post(url, json=payload, headers=JSON_HEADERS,
                          auth=self.auth, timeout=self.timeout, verify=False)
        # Treat "already exists" as success (card gets updated)
        if r.status_code == 400 and ("cardNoAlreadyExist" in r.text or "checkEmployeeNo" in r.text):
            return r
        r.raise_for_status()
        return r

    # ---- Card re-enable (restore access)
    def card_enable_json(self, employee_no: str, card_no: str, begin_time_iso: str, end_time_iso: str, door_right: str = "1"):
        """
        Re-enable a card with fresh validity window.
        Useful for restoring access if needed.
        """
        url = f"{self.base}/ISAPI/AccessControl/CardInfo/Record?format=json"
        payload = {
            "CardInfo": {
                "employeeNo": employee_no,
                "cardNo": str(card_no),
                "cardType": "normalCard",
                "status": "normal",
                "doorRight": door_right,
                "Valid": {
                    "enable": True,
                    "beginTime": begin_time_iso,
                    "endTime": end_time_iso
                }
            }
        }
        r = requests.post(url, json=payload, headers=JSON_HEADERS,
                          auth=self.auth, timeout=self.timeout, verify=False)
        # Treat "already exists" as success (card gets updated)
        if r.status_code == 400 and ("cardNoAlreadyExist" in r.text or "checkEmployeeNo" in r.text):
            return r
        r.raise_for_status()
        return r

    # ---- VISITOR upsert (XML format)
    def user_upsert_xml(self, employee_no: str, name: str = "Visitor") -> requests.Response:
        """Create/update VISITOR user (wide validity; XML; POST)."""
        url = f"{self.base}/ISAPI/AccessControl/UserInfo/Record?format=xml"
        xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<UserInfo>
    <employeeNo>{employee_no}</employeeNo>
    <name>{name}</name>
    <userType>normal</userType>
    <status>active</status>
    <Valid>
        <enable>true</enable>
        <beginTime>2020-01-01T00:00:00</beginTime>
        <endTime>2030-12-31T23:59:59</endTime>
    </Valid>
    <doorRight>1</doorRight>
</UserInfo>"""
        r = requests.post(url, data=xml_payload, headers=XML_HEADERS,
                          auth=self.auth, timeout=self.timeout, verify=False)
        # Treat "already exists" as success
        if r.status_code == 400 and "employeeNoAlreadyExist" in r.text:
            return r
        r.raise_for_status()
        return r

    # ---- Card upsert for VISITOR (XML format)
    def card_upsert_xml(self, employee_no: str, card_no: str, valid_from: str = None, valid_to: str = None) -> requests.Response:
        """Bind card number to user (XML; POST)."""
        url = f"{self.base}/ISAPI/AccessControl/CardInfo/Record?format=xml"
        
        # Build validity XML if provided
        validity_xml = ""
        if valid_from and valid_to:
            validity_xml = f"""
    <Valid>
        <enable>true</enable>
        <beginTime>{valid_from}</beginTime>
        <endTime>{valid_to}</endTime>
    </Valid>"""
        
        xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<CardInfo>
    <employeeNo>{employee_no}</employeeNo>
    <cardNo>{card_no}</cardNo>
    <cardType>normalCard</cardType>
    <status>active</status>{validity_xml}
</CardInfo>"""
        
        r = requests.post(url, data=xml_payload, headers=XML_HEADERS,
                          auth=self.auth, timeout=self.timeout, verify=False)
        # Treat "already exists" as success
        if r.status_code == 400 and "cardNoAlreadyExist" in r.text:
            return r
        r.raise_for_status()
        return r

    # ---- Access Control Event Search
    def acs_event_search(self, start_iso: str, end_iso: str, max_results: int = 30):
        """
        Pull recent access events from the terminal (works on your firmware).
        Returns (status_code, json_text).
        """
        url = f"{self.base}/ISAPI/AccessControl/AcsEvent?format=json"
        payload = {
            "AcsEventCond": {
                "searchID": "1",
                "searchResultPosition": 0,
                "maxResults": max_results,
                "major": 0,  # all
                "minor": 0,  # all
                "startTime": start_iso,
                "endTime":   end_iso,
            }
        }
        r = requests.post(url, json=payload, auth=self.auth, timeout=8)
        return r.status_code, r.text


