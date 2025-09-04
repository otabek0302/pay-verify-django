from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import requests
import json
from requests.auth import HTTPDigestAuth
from medical_access.models import Appointment, Door, AccessEvent
from controller.hik_client import HikClient

class Command(BaseCommand):
    help = "Poll door events and auto-mark passes as USED when scanned at terminals."

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=2,
            help='Poll interval in minutes (default: 2 minutes)'
        )
        parser.add_argument(
            '--continuous',
            action='store_true',
            help='Run continuously every 10 seconds (for production)'
        )

    def handle(self, *args, **options):
        interval_minutes = options['interval']
        continuous = options['continuous']
        
        if continuous:
            self.stdout.write("🔄 Starting continuous polling (every 10 seconds)...")
            self.stdout.write("Press Ctrl+C to stop")
            import time
            while True:
                try:
                    self.poll_events(interval_minutes)
                    time.sleep(10)  # Poll every 10 seconds
                except KeyboardInterrupt:
                    self.stdout.write("\n⏹️  Polling stopped by user")
                    break
                except Exception as e:
                    self.stderr.write(f"Polling error: {e}")
                    time.sleep(10)  # Continue polling even if error
        else:
            self.poll_events(interval_minutes)

    def poll_events(self, interval_minutes):
        """Poll events from all doors and mark passes as used"""
        doors = list(Door.objects.all())
        if not doors:
            self.stdout.write("No doors configured.")
            return

        # Poll last N minutes
        end = timezone.now()
        start = end - timedelta(minutes=interval_minutes)
        
        self.stdout.write(f"🔍 Polling events from {start.strftime('%H:%M:%S')} to {end.strftime('%H:%M:%S')}")

        used_cards = set()
        total_events = 0

        for door in doors:
            try:
                events = self._fetch_door_events(door, start, end)
                total_events += len(events)
                
                for event in events:
                    card_no = self._extract_card_number(event)
                    if card_no:
                        used_cards.add(card_no)
                        self.stdout.write(f"📱 {door.name}: Card {card_no} used at {event.get('time', 'unknown')}")
                        
            except Exception as e:
                self.stderr.write(f"❌ {door.name}: Failed to fetch events - {e}")

        self.stdout.write(f"📊 Found {total_events} events across {len(doors)} doors")
        
        if used_cards:
            marked_count = self._mark_passes_as_used(used_cards)
            self.stdout.write(self.style.SUCCESS(f"✅ Marked {marked_count} passes as USED"))
        else:
            self.stdout.write("📭 No card usage detected")

    def _fetch_door_events(self, door, start_time, end_time):
        """Fetch access events from a specific door"""
        base = f"http://{door.terminal_ip}"
        auth = HTTPDigestAuth(door.terminal_username, door.terminal_password)
        
        # Try JSON format first
        body = {
            "AcsEventCond": {
                "searchID": "1",
                "searchResultPosition": 0,
                "maxResults": 100,
                "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        }
        
        url = f"{base}/ISAPI/AccessControl/AcsEvent?format=json"
        
        try:
            # Try POST with JSON
            r = requests.post(
                url,
                data=json.dumps(body),
                headers={"Content-Type": "application/json"},
                auth=auth,
                timeout=8,
                verify=False
            )
            
            if r.status_code == 200:
                data = r.json()
                return data.get("AcsEvent", []) if isinstance(data, dict) else []
            
            elif r.status_code in [404, 415, 400]:
                # Fallback to XML format
                return self._fetch_events_xml(door, start_time, end_time)
            
            else:
                r.raise_for_status()
                
        except Exception as e:
            # Try XML fallback on any error
            return self._fetch_events_xml(door, start_time, end_time)

    def _fetch_events_xml(self, door, start_time, end_time):
        """Fallback: Fetch events using XML format"""
        base = f"http://{door.terminal_ip}"
        auth = HTTPDigestAuth(door.terminal_username, door.terminal_password)
        
        xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<AcsEventCond version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
    <searchID>1</searchID>
    <searchResultPosition>0</searchResultPosition>
    <maxResults>100</maxResults>
    <startTime>{start_time.strftime("%Y-%m-%dT%H:%M:%SZ")}</startTime>
    <endTime>{end_time.strftime("%Y-%m-%dT%H:%M:%SZ")}</endTime>
</AcsEventCond>"""
        
        try:
            r = requests.post(
                f"{base}/ISAPI/AccessControl/AcsEvent",
                data=xml_body,
                headers={"Content-Type": "application/xml"},
                auth=auth,
                timeout=8,
                verify=False
            )
            r.raise_for_status()
            
            # Parse XML response (simplified)
            # In production, use xml.etree.ElementTree for proper parsing
            events = []
            if 'cardNo' in r.text:
                # Simple regex to extract card numbers from XML
                import re
                card_matches = re.findall(r'<cardNo>([^<]+)</cardNo>', r.text)
                time_matches = re.findall(r'<time>([^<]+)</time>', r.text)
                
                for i, card in enumerate(card_matches):
                    events.append({
                        'cardNo': card,
                        'time': time_matches[i] if i < len(time_matches) else 'unknown'
                    })
            
            return events
            
        except Exception as e:
            self.stderr.write(f"XML events fetch failed: {e}")
            return []

    def _extract_card_number(self, event):
        """Extract card number from event data"""
        # Try different possible field names
        return (
            event.get('cardNo') or 
            event.get('cardNumber') or 
            event.get('employeeNo') or
            ''
        ).strip()

    def _mark_passes_as_used(self, used_cards):
        """Mark appointments as USED if they were scanned at terminals"""
        marked_count = 0
        
        for card_no in used_cards:
            try:
                # Find ACTIVE appointment with this card number
                appointment = Appointment.objects.get(
                    card_no=card_no,
                    status=Appointment.Status.ACTIVE
                )
                
                # Check if appointment is still within validity window
                now = timezone.now()
                if appointment.valid_from <= now <= appointment.valid_to:
                    # Mark as used
                    appointment.mark_as_used()
                    
                    # Log the hardware access event
                    AccessEvent.objects.create(
                        card_no=card_no,
                        source=AccessEvent.Source.API,
                        result=AccessEvent.Result.ALLOW,
                        reason='Terminal scan detected - marked as used',
                        appointment=appointment
                    )
                    
                    marked_count += 1
                    self.stdout.write(f"✅ Card {card_no}: Marked as USED")
                else:
                    self.stdout.write(f"⏰ Card {card_no}: Outside validity window")
                    
            except Appointment.DoesNotExist:
                self.stdout.write(f"❓ Card {card_no}: No active appointment found")
            except Exception as e:
                self.stderr.write(f"❌ Card {card_no}: Error marking as used - {e}")
                
        return marked_count
