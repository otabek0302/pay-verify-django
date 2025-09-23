"""
Hikvision ISAPI Client for Access Control Terminals
"""

import requests
from requests.auth import HTTPDigestAuth

DEFAULT_TIMEOUT = 5
JSON_HEADERS = {"Content-Type": "application/json"}
XML_HEADERS = {"Content-Type": "application/xml"}


class HikTerminal:
    """ISAPI client for Hikvision access terminals (DS-K1T342MFWX-E1)"""
    
    def __init__(self, host: str, username: str, password: str, timeout=None, port: int = 80, use_xml: bool = True):
        self.base = f"http://{host}" if port in (80, None) else f"http://{host}:{port}"
        self.auth = HTTPDigestAuth(username, password)
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.use_xml = use_xml
        self.h_xml = XML_HEADERS

    def device_info(self) -> str:
        """Get device information from terminal"""
        r = requests.get(f"{self.base}/ISAPI/System/deviceInfo", auth=self.auth, timeout=self.timeout)
        r.raise_for_status()
        return r.text

    def status(self) -> str:
        """Get terminal operational status"""
        r = requests.get(f"{self.base}/ISAPI/System/status", auth=self.auth, timeout=self.timeout)
        r.raise_for_status()
        return r.text

    def open_door(self, door_no: int = 1, cmd: str = "open") -> str:
        """Control door relay on terminal"""
        xml = f"<RemoteControlDoor><cmd>{cmd}</cmd></RemoteControlDoor>"
        r = requests.put(
            f"{self.base}/ISAPI/AccessControl/RemoteControl/door/{door_no}",
            data=xml, headers=self.h_xml, auth=self.auth, timeout=self.timeout,
            verify=False
        )
        r.raise_for_status()
        return r.text

    def alert_stream(self):
        """Get real-time event stream from terminal"""
        r = requests.get(
            f"{self.base}/ISAPI/Event/notification/alertStream",
            auth=self.auth, stream=True, timeout=(5, 60)
        )
        r.raise_for_status()
        return r

    def acs_event_search(self, start_iso: str, end_iso: str, max_results: int = 30):
        """Search historical access control events from terminal"""
        url = f"{self.base}/ISAPI/AccessControl/AcsEvent?format=json"
        payload = {
            "AcsEventCond": {
                "searchID": "1",
                "searchResultPosition": 0,
                "maxResults": max_results,
                "major": 0,
                "minor": 0,
                "startTime": start_iso,
                "endTime": end_iso,
            }
        }
        r = requests.post(url, json=payload, auth=self.auth, timeout=8)
        return r.status_code, r.text