from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator, RegexValidator
from django.utils import timezone

class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        ADMIN = "admin", "Admin"
        RECEPTIONIST = "receptionist", "Receptionist"
    
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
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    passport_series = models.CharField(max_length=10, blank=True, null=True)
    passport_number = models.CharField(max_length=20, blank=True, null=True)
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

class Appointment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        ENTER = 'enter', 'Enter'
        LEAVE = 'leave', 'Leave'
        USED = 'used', 'Used'
        EXPIRED = 'expired', 'Expired'
    
    patient = models.ForeignKey(Patient, on_delete=models.DO_NOTHING, related_name='appointments')
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name='appointments')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    
    # QR Code and validity fields (Simple 12-character codes)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_till = models.DateTimeField(null=True, blank=True)
    qr_code = models.CharField(max_length=12, unique=True, null=True, blank=True)  # Simple 12-character QR code
    used_at = models.DateTimeField(null=True, blank=True)  # When QR was used
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Appointment'
        verbose_name_plural = 'Appointments'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.patient.full_name} - {self.doctor.procedure} on {self.created_at.date()}"
    
    def save(self, *args, **kwargs):
        # Auto-generate simple 12-character QR code if not provided
        if not self.qr_code:
            import random
            import string
            # Generate 12-character alphanumeric code (uppercase letters and numbers)
            characters = string.ascii_uppercase + string.digits
            self.qr_code = ''.join(random.choice(characters) for _ in range(12))
            
        super().save(*args, **kwargs)
    
    @property
    def is_valid(self):
        now = timezone.now()
        return (
            self.status == self.Status.ACTIVE and
            self.valid_from and self.valid_till and
            self.valid_from <= now <= self.valid_till
        )
    
    def mark_as_used(self):
        self.status = self.Status.ENTER
        self.used_at = timezone.now()
        self.save()
    
    def mark_as_leave(self):
        self.status = self.Status.LEAVE
        self.save()

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