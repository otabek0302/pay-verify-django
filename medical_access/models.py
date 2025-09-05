from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator, RegexValidator
from django.utils import timezone
import uuid

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        DOCTOR = "doctor", "Doctor"
        PATIENT = "patient", "Patient"
    
    role = models.CharField(max_length=20, choices=Role.choices, blank=True)
    phone = models.CharField(
        max_length=15, 
        blank=True,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message='Phone number must be entered in the format: +999999999. Up to 15 digits allowed.')]
    )
    
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
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
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

class Door(models.Model):
    name = models.CharField(max_length=80)
    room_number = models.CharField(max_length=20, blank=True, null=True, help_text="Room number (e.g., 101, A-12)")
    terminal_ip = models.GenericIPAddressField()
    terminal_username = models.CharField(max_length=64)
    terminal_password = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Door'
        verbose_name_plural = 'Doors'
        ordering = ['name']
    
    def __str__(self):
        if self.room_number:
            return f"{self.name} (Room {self.room_number})"
        return self.name
    
    @property
    def display_name(self):
        """Get formatted display name with room number"""
        if self.room_number:
            return f"{self.name} - Room {self.room_number}"
        return self.name

class Procedure(models.Model):
    title = models.CharField(max_length=160)
    price = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(0.01, 'Price must be greater than 0')]
    )
    doctors = models.ManyToManyField(Doctor, related_name='procedures')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Procedure'
        verbose_name_plural = 'Procedures'
        ordering = ['title']
    
    def __str__(self):
        return f"{self.title} - {self.price} sum"
    
    @property
    def location_info(self):
        """Get formatted location information"""
        return "Location not specified"

class Patient(models.Model):
    first_name = models.CharField(max_length=50, default='Unknown')
    last_name = models.CharField(max_length=50, default='Patient')
    phone = models.CharField(max_length=20, blank=True, null=True)
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

class Appointment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        ENTER = 'enter', 'Enter'
        LEAVE = 'leave', 'Leave'
        USED = 'used', 'Used'
        EXPIRED = 'expired', 'Expired'
        REVOKED = 'revoked', 'Revoked'
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='appointments')
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name='appointments')
    procedure = models.ForeignKey(Procedure, on_delete=models.PROTECT, related_name='appointments')
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    paid = models.BooleanField(default=True)  # Default to paid when created
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    
    # QR Code and Access Control fields (merged from TemporaryPass)
    card_no = models.CharField(max_length=32, unique=True, null=True, blank=True)
    qr_payload = models.TextField(blank=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Appointment'
        verbose_name_plural = 'Appointments'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.patient.full_name} - {self.procedure.title} on {self.appointment_date}"
    
    def save(self, *args, **kwargs):
        # Auto-generate numeric card number if not provided (DS-K1T342 expects digits only)
        if not self.card_no:
            import random
            # Generate 8-digit numeric card number
            self.card_no = str(random.randint(10000000, 99999999))
        
        # Set QR payload to card number
        if not self.qr_payload:
            self.qr_payload = self.card_no
            
        super().save(*args, **kwargs)
    
    @property
    def appointment_datetime(self):
        return timezone.make_aware(
            timezone.datetime.combine(self.appointment_date, self.appointment_time)
        )
    
    @property
    def is_valid(self):
        now = timezone.now()
        return (
            self.status == self.Status.ACTIVE and
            self.valid_from <= now <= self.valid_to
        )
    
    def mark_as_used(self):
        self.status = self.Status.USED
        self.used_at = timezone.now()
        self.save()
    
    def mark_as_expired(self):
        self.status = self.Status.EXPIRED
        self.save()

class AccessEvent(models.Model):
    class Result(models.TextChoices):
        ALLOW = 'allow', 'Allow'
        DENY = 'deny', 'Deny'
    
    class Source(models.TextChoices):
        KIOSK = 'kiosk', 'Kiosk'
        ADMIN = 'admin', 'Admin Override'
        API = 'api', 'API'
    
    # Core fields
    card_no = models.CharField(max_length=32, db_index=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.KIOSK)
    result = models.CharField(max_length=10, choices=Result.choices)
    reason = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Optional fields
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='access_events')
    operator = models.CharField(max_length=100, blank=True, help_text="Staff member who performed override")
    door = models.ForeignKey(Door, on_delete=models.SET_NULL, null=True, blank=True, related_name='access_events')
    
    # Audit fields
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        verbose_name = 'Access Event'
        verbose_name_plural = 'Access Events'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['card_no', '-timestamp']),
            models.Index(fields=['result', '-timestamp']),
            models.Index(fields=['source', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.get_result_display()} - {self.card_no} at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    @property
    def patient_name(self):
        """Get patient name if available"""
        if self.appointment:
            return self.appointment.patient.full_name
        return "Unknown"