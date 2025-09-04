from django.core.management.base import BaseCommand
from django.utils import timezone
from medical_access.models import Door
from medical_access.controller.hik_client import HikClient

class Command(BaseCommand):
    help = "Provision a test card to all doors (valid 24h)."

    def add_arguments(self, parser):
        parser.add_argument("--card", required=True, help="Plain card number to encode in QR (digits only)")
        parser.add_argument("--name", default="Temp QR")

    def handle(self, *args, **opts):
        card = opts["card"]
        begin = timezone.now()
        end = begin + timezone.timedelta(hours=24)
        begin_s = begin.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_s = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        self.stdout.write(f"🔄 Provisioning card: {card}")
        self.stdout.write(f"⏰ Valid from: {begin_s}")
        self.stdout.write(f"⏰ Valid to: {end_s}")
        self.stdout.write("=" * 50)

        success_count = 0
        for d in Door.objects.all():
            try:
                self.stdout.write(f"→ {d.name} @ {d.terminal_ip}")
                c = HikClient(d.terminal_ip, d.terminal_username, d.terminal_password)
                c.ping()
                
                employee_no = f"TEST{card}"
                c.create_user(employee_no, opts["name"], begin, end)
                c.bind_card(employee_no, card, begin, end)
                c.grant_door(employee_no, door_no=1, time_section_no=1)
                self.stdout.write(self.style.SUCCESS(f"   ✅ SUCCESS"))
                success_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ FAILED: {e}"))

        self.stdout.write("=" * 50)
        if success_count > 0:
            self.stdout.write(self.style.SUCCESS(f"🎉 Provisioned to {success_count} door(s)!"))
            self.stdout.write("📱 Now generate a QR with ONLY this card number:")
            self.stdout.write(self.style.SUCCESS(f"   {card}"))
            self.stdout.write("🚪 Scan it at the terminal - the door should open!")
        else:
            self.stdout.write(self.style.ERROR("❌ Failed to provision to any doors"))
            self.stdout.write("💡 Check device credentials and network connectivity")
