from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, RegexValidator
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
    phone = models.CharField(max_length=15, blank=True, validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message='Phone number must be entered in the format: +999999999. Up to 15 digits allowed.')])
    
    class Meta:
        db_table = 'users_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['username']
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

class Doctor(models.Model):
    first_name = models.CharField(max_length=50, default='')
    last_name = models.CharField(max_length=50, default='')
    procedure = models.CharField(max_length=160, default='General Consultation')
    price = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, validators=[MinValueValidator(0.01, 'Price must be greater than 0')])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Doctor'
        verbose_name_plural = 'Doctors'
        ordering = ['last_name', 'first_name']
    
    def __str__(self):
        return f"Dr. {self.full_name}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

class Patient(models.Model):
    first_name = models.CharField(max_length=50, default='')
    last_name = models.CharField(max_length=50, default='')
    passport_series = models.CharField(max_length=10, blank=True, null=True, default='')
    passport_number = models.CharField(max_length=20, blank=True, null=True, default='')
    phone = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message='Phone number must be entered in the format: +999999999. Up to 15 digits allowed.')]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Patient'
        verbose_name_plural = 'Patients'
        ordering = ['last_name', 'first_name']
    
    def __str__(self):
        return f"{self.full_name}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    @property
    def display_name(self):
        """Display name with phone if available"""
        if self.phone:
            return f"{self.full_name} ({self.phone})"
        return self.full_name

class Integration(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Integration name (e.g., DMED, RemoteJobs)")
    api_url = models.URLField(blank=True, null=True, help_text="Base API endpoint if needed")
    api_token = models.CharField(max_length=255, unique=True, editable=False, help_text="Auto-generated secure token")
    is_active = models.BooleanField(default=True, help_text="Enable/disable this integration")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Integration'
        verbose_name_plural = 'Integrations'
        ordering = ['name']
    
    def save(self, *args, **kwargs):
        if not self.api_token:
            self.api_token = secrets.token_hex(32)  # 64-char secure key
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"

class Appointment(models.Model):
    
    patient = models.ForeignKey("Patient", on_delete=models.DO_NOTHING, related_name="appointments")
    doctor = models.ForeignKey("Doctor", on_delete=models.DO_NOTHING, related_name="appointments")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Appointment'
        verbose_name_plural = 'Appointments'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.patient.full_name} - {self.doctor.procedure}"

class QRCode(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        ENTERED = 'entered', 'Entered'
        LEFT = 'left', 'Left'
        EXPIRED = 'expired', 'Expired'

    appointment = models.OneToOneField("Appointment", on_delete=models.CASCADE, related_name="qr_code")
    code = models.CharField(max_length=12, unique=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

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
            self.code = ''.join(random.choice(chars) for _ in range(12))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"QR {self.code} for Appointment {self.appointment.id}"

    @property
    def is_valid(self):
        now = timezone.now()
        return (not self.revoked) and self.expires_at > now and self.status in [self.Status.ACTIVE, self.Status.ENTERED]
    
class Terminal(models.Model):
    class Mode(models.TextChoices):
        ENTRY = 'entry', 'Entry'
        EXIT = 'exit', 'Exit'
        BOTH = 'both', 'Both'
    
    terminal_name = models.CharField(max_length=100)
    terminal_ip = models.GenericIPAddressField(unique=True)
    terminal_username = models.CharField(max_length=50)
    terminal_password = models.CharField(max_length=100)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.ENTRY)
    
    # Health fields (new)
    reachable = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    
    # Control fields
    active = models.BooleanField(default=True, help_text="Set to False to skip this terminal")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Terminal'
        verbose_name_plural = 'Terminals'
        ordering = ['terminal_name']
        indexes = [
            models.Index(fields=["mode", "active"]),
        ]
    
    def __str__(self):
        return f"{self.terminal_name} ({self.mode})"