from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator
from django.contrib.auth.models import AbstractUser
import secrets
import string
import random


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        ADMIN = "admin", "Admin"
        RECEPTIONIST = "receptionist", "Receptionist"

    role = models.CharField(max_length=20, choices=Role.choices, blank=True)
    phone = models.CharField(
        max_length=15,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^\+?1?\d{9,15}$",
                message="Phone number must be entered in the format: +999999999. Up to 15 digits allowed.",
            )
        ],
    )

    class Meta:
        db_table = "users_user"
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["username"]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class Patient(models.Model):
    first_name = models.CharField(max_length=50, default="")
    last_name = models.CharField(max_length=50, default="")
    medical_card_number = models.CharField(
        max_length=20,
        unique=True,
        default="TEMP_CARD",
        help_text="Unique medical card number for the patient"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Patient"
        verbose_name_plural = "Patients"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.full_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self):
        """Display name with medical card number"""
        return f"{self.full_name} ({self.medical_card_number})"


class Integration(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Integration name (e.g., DMED, RemoteJobs)",
    )
    api_token = models.CharField(
        max_length=255,
        unique=True,
        editable=False,
        help_text="Auto-generated secure token for partner authentication",
    )
    is_active = models.BooleanField(
        default=True, help_text="Enable/disable this integration"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def token_preview(self):
        if not self.api_token:
            return "-"
        return f"{self.api_token[:8]}…{self.api_token[-4:]}"

    class Meta:
        verbose_name = "Integration"
        verbose_name_plural = "Integrations"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.api_token:
            self.api_token = secrets.token_hex(32)  # 64-char secure key
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"


class Appointment(models.Model):
    patient = models.ForeignKey(
        "Patient", on_delete=models.DO_NOTHING, related_name="appointments"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Appointment"
        verbose_name_plural = "Appointments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.patient.full_name} - Appointment #{self.id}"


class QRCode(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ENTERED = "entered", "Entered"
        LEFT = "left", "Left"
        EXPIRED = "expired", "Expired"

    appointment = models.OneToOneField(
        "Appointment", on_delete=models.CASCADE, related_name="qr_code"
    )
    code = models.CharField(max_length=12, unique=True, db_index=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )

    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "QR Code"
        verbose_name_plural = "QR Codes"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.code:
            chars = string.ascii_uppercase + string.digits
            self.code = "".join(random.choice(chars) for _ in range(12))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"QR {self.code} for Appointment {self.appointment.id}"

    @property
    def is_valid(self):
        now = timezone.now()
        return (
            (not self.revoked)
            and self.expires_at > now
            and self.status in [self.Status.ACTIVE, self.Status.ENTERED, self.Status.LEFT]
        )


class Terminal(models.Model):
    class Mode(models.TextChoices):
        ENTRY = "entry", "Entry"
        EXIT = "exit", "Exit"
        BOTH = "both", "Both"

    terminal_name = models.CharField(max_length=100)
    terminal_ip = models.GenericIPAddressField(unique=True)
    mac_address = models.CharField(
        max_length=17,
        unique=True,
        null=True,
        blank=True,
        help_text="Format: AA:BB:CC:DD:EE:FF",
    )
    terminal_username = models.CharField(max_length=50)
    terminal_password = models.CharField(max_length=100)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.ENTRY)

    # Health fields (new)
    reachable = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    # Control fields
    active = models.BooleanField(
        default=True, help_text="Set to False to skip this terminal"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Terminal"
        verbose_name_plural = "Terminals"
        ordering = ["terminal_name"]
        indexes = [
            models.Index(fields=["mode", "active"]),
        ]

    def __str__(self):
        return f"{self.terminal_name} ({self.mode})"
