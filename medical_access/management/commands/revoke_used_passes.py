from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import requests, json
from requests.auth import HTTPDigestAuth
from medical_access.models import Appointment, Door
from medical_access.controller.hik_client import HikClient

class Command(BaseCommand):
    help = "Poll recent access events on all doors; on first use, mark USED and revoke on every door."

    def handle(self, *args, **kwargs):
        doors = list(Door.objects.all())
        if not doors:
            self.stdout.write("No doors configured.")
            return

        # poll last 3 minutes; adjust as you like
        end = timezone.now()
        start = end - timedelta(minutes=3)

        def _fetch_events(door: Door):
            base = f"http://{door.terminal_ip}"
            auth = HTTPDigestAuth(door.terminal_username, door.terminal_password)
            body = {
                "AcsEventCond": {
                    "searchID": "1",
                    "searchResultPosition": 0,
                    "maxResults": 100,
                    "startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "endTime": end.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
            }
            r = requests.post(f"{base}/ISAPI/AccessControl/AcsEvent?format=json",
                              data=json.dumps(body),
                              headers={"Content-Type":"application/json"},
                              auth=auth, timeout=10, verify=False)
            r.raise_for_status()
            data = r.json()
            return data.get("AcsEvent", []) if isinstance(data, dict) else []

        # gather cardNos used
        used_card_nos = set()
        for door in doors:
            try:
                events = _fetch_events(door)
            except Exception as e:
                self.stderr.write(f"[{door.name}] event fetch failed: {e}")
                continue
            for ev in events:
                card_no = (ev.get("cardNo") or ev.get("cardNumber") or "").strip()
                if card_no:
                    used_card_nos.add(card_no)

        if not used_card_nos:
            self.stdout.write("No relevant events.")
            return

        # For each used card number → if we have an ACTIVE valid appointment, revoke everywhere
        for card_no in used_card_nos:
            try:
                appointment = Appointment.objects.get(card_no=card_no, status=Appointment.Status.ACTIVE)
            except Appointment.DoesNotExist:
                continue

            # Check validity window
            now = timezone.now()
            if not (appointment.valid_from <= now <= appointment.valid_to):
                continue

            # revoke on all doors
            for door in doors:
                try:
                    client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
                    client.delete_user(card_no)
                except Exception as e:
                    self.stderr.write(f"[{door.name}] revoke failed: {e}")

            appointment.status = Appointment.Status.USED
            appointment.used_at = timezone.now()
            appointment.save(update_fields=["status", "used_at", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"Revoked one-time appointment {card_no}"))
