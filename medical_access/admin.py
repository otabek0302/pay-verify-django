from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
import logging
from .models import User, Doctor, Patient, Procedure, Door, Appointment, AccessEvent
from .controller.hik_client import HikClient

log = logging.getLogger("medical_access")

# Custom User Admin
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'first_name', 'last_name')
    ordering = ('username',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('Medical Access Info', {'fields': ('role', 'phone')}),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Medical Access Info', {'fields': ('role', 'phone')}),
    )

# Doctor Admin
@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'first_name', 'last_name', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('first_name', 'last_name')
    ordering = ('last_name', 'first_name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# Patient Admin
@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('first_name', 'last_name', 'phone')
    ordering = ('last_name', 'first_name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'phone')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# Procedure Admin
@admin.register(Procedure)
class ProcedureAdmin(admin.ModelAdmin):
    list_display = ('title', 'price', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('title',)
    ordering = ('title',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Procedure Details', {
            'fields': ('title', 'price')
        }),
        ('Medical Staff', {
            'fields': ('doctors',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# Door Admin
@admin.register(Door)
class DoorAdmin(admin.ModelAdmin):
    list_display = ('name', 'room_number', 'terminal_ip', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'room_number', 'terminal_ip')
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Door Information', {
            'fields': ('name', 'room_number')
        }),
        ('Terminal Configuration', {
            'fields': ('terminal_ip', 'terminal_username', 'terminal_password')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# Appointment Admin
@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'doctor', 'procedure', 'appointment_date', 'appointment_time', 'status', 'paid', 'card_no', 'created_at')
    list_filter = ('status', 'paid', 'created_at')
    search_fields = ('patient__first_name', 'patient__last_name', 'patient__phone', 'doctor__first_name', 'doctor__last_name', 'procedure__title', 'card_no')
    ordering = ('-appointment_date', '-appointment_time')
    readonly_fields = ('card_no', 'qr_payload', 'created_at', 'updated_at')
    date_hierarchy = 'appointment_date'
    
    fieldsets = (
        ('Appointment Details', {
            'fields': ('patient', 'doctor', 'procedure', 'appointment_date', 'appointment_time')
        }),
        ('Status & Payment', {
            'fields': ('status', 'paid')
        }),
        ('QR Code & Access', {
            'fields': ('card_no', 'qr_payload', 'valid_from', 'valid_to', 'used_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        old_paid = False
        if obj.pk:
            old_paid = Appointment.objects.filter(pk=obj.pk).values_list("paid", flat=True).first() or False
        super().save_model(request, obj, form, change)  # ✅ ensures post_save fires

        # Optional: direct fallback if signals were misconfigured
        if obj.paid and (not old_paid):
            self._provision_now(obj)

    def _provision_now(self, appt: Appointment):
        # Provision appointment directly to terminals
        emp = f"APT{appt.id}"
        # Make user name unique per appointment to avoid conflicts
        patient_name = f"{appt.patient.full_name} - {appt.procedure.title} #{appt.id}"
        def _do():
            for door in Door.objects.all():
                try:
                    c = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
                    c.create_user(emp, patient_name, appt.valid_from, appt.valid_to)
                    c.bind_card(emp, appt.card_no, appt.valid_from, appt.valid_to)
                    c.grant_door(emp, door_no=1, time_section_no=1)
                    log.info(f"[ADMIN][{door.name}] Provision OK for appt {appt.id}")
                except Exception as e:
                    log.exception(f"[ADMIN][{door.name}] Provision FAILED for appt {appt.id}: {e}")
        transaction.on_commit(_do)


# Access Event Admin
@admin.register(AccessEvent)
class AccessEventAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'card_no', 'result', 'reason', 'source', 'patient_name', 'operator')
    list_filter = ('result', 'source', 'timestamp')
    search_fields = ('card_no', 'reason', 'operator', 'appointment__patient__first_name', 'appointment__patient__last_name')
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp', 'ip_address', 'user_agent')
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Access Details', {
            'fields': ('card_no', 'result', 'reason', 'source')
        }),
        ('Related Records', {
            'fields': ('appointment', 'door', 'operator')
        }),
        ('Audit Information', {
            'fields': ('timestamp', 'ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )
    
    def patient_name(self, obj):
        return obj.patient_name
    patient_name.short_description = 'Patient'

# Register the custom User model
admin.site.register(User, CustomUserAdmin)