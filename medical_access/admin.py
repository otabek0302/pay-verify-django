from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse
from django.utils.html import format_html
from .models import User, Doctor, Patient, Appointment, Terminal, Integration, QRCode
from .services import probe_terminal, open_door

# Custom Admin Site with Role-based Access
class MedicalAccessAdminSite(admin.AdminSite):
    site_header = "Medical Access System - Super Admin"
    site_title = "Medical Access Admin"
    index_title = "Super Admin Dashboard"
    
    def has_permission(self, request):
        """Allow only super admin users to access the Django admin site"""
        return (
            request.user.is_authenticated and 
            request.user.is_active and 
            (hasattr(request.user, 'role') and request.user.role == 'super_admin')
        )
    
    def login(self, request, extra_context=None):
        """ Redirect to custom login if user doesn't have super admin role """
        if not self.has_permission(request):
            return redirect_to_login(request.get_full_path(), reverse('medical_access:login'))
        return super().login(request, extra_context)
    
    def index(self, request, extra_context=None):
        """Redirect to custom login if user doesn't have super admin role"""
        if not self.has_permission(request):
            return redirect_to_login(request.get_full_path(), reverse('medical_access:login'))
        return super().index(request, extra_context)

# Create custom admin site instance
medical_admin_site = MedicalAccessAdminSite(name='medical_admin')

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
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'first_name', 'last_name', 'procedure', 'price', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('first_name', 'last_name', 'procedure')
    ordering = ('last_name', 'first_name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name')
        }),
        ('Medical Information', {
            'fields': ('procedure', 'price')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# Patient Admin
class PatientAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'passport_series', 'passport_number', 'phone', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('first_name', 'last_name', 'phone', 'passport_series', 'passport_number')
    ordering = ('last_name', 'first_name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'phone')
        }),
        ('Passport Information', {
            'fields': ('passport_series', 'passport_number')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# Appointment Admin
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'doctor', 'qr_code_status', 'qr_code_expires', 'created_at')
    list_filter = ('qr_code__status', 'created_at')
    search_fields = ('patient__first_name', 'patient__last_name', 'patient__phone', 'doctor__first_name', 'doctor__last_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    actions = []
    
    fieldsets = (
        ('Appointment Details', {
            'fields': ('patient', 'doctor', 'created_by')
        }),
        ('QR Code', {
            'fields': ('qr_code',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def qr_code_status(self, obj):
        return obj.qr_code.status if hasattr(obj, 'qr_code') else 'No QR Code'
    qr_code_status.short_description = 'Status'
    
    def qr_code_expires(self, obj):
        return obj.qr_code.expires_at if hasattr(obj, 'qr_code') else 'No QR Code'
    qr_code_expires.short_description = 'Expires At'

# Admin actions for Terminal
@admin.action(description="Test connection (ISAPI)")
def admin_test_connection(modeladmin, request, queryset):
    ok, fail = 0, 0
    for t in queryset:
        res = probe_terminal(t)
        ok += 1 if res.get("ok") else 0
        fail += 0 if res.get("ok") else 1
    modeladmin.message_user(request, f"Probe done: OK={ok}, Failed={fail}")

@admin.action(description="Open door 1 (test)")
def admin_open_door(modeladmin, request, queryset):
    done, fail = 0, 0
    for t in queryset:
        res = open_door(t, door_no=1)
        done += 1 if res.get("ok") else 0
        fail += 0 if res.get("ok") else 1
    modeladmin.message_user(request, f"Open door sent: OK={done}, Failed={fail}")

# Terminal Admin
class TerminalAdmin(admin.ModelAdmin):
    list_display = ("terminal_name", "terminal_ip", "mac_address", "mode", "active", "reachable", "last_seen", "short_error")
    list_filter = ("mode", "active", "reachable", "created_at")
    search_fields = ("terminal_name", "terminal_ip", "mac_address", "terminal_username")
    actions = [admin_test_connection, admin_open_door]
    readonly_fields = ('created_at', 'updated_at')
    
    def short_error(self, obj):
        return (obj.last_error or "")[:60]
    short_error.short_description = "Last Error"
    
    fieldsets = (
        ('Terminal Information', {
            'fields': ('terminal_name', 'terminal_ip', 'mac_address', 'mode')
        }),
        ('Credentials', {
            'fields': ('terminal_username', 'terminal_password')
        }),
        ('Health Status', {
            'fields': ('reachable', 'last_seen', 'last_error'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# Integration Admin
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ('name', 'api_url', 'is_active', 'created_at', 'token_preview')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'api_url')
    ordering = ('name',)
    readonly_fields = ('api_token', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Integration Information', {
            'fields': ('name', 'api_url', 'is_active')
        }),
        ('API Token', {
            'fields': ('token_preview',),
            'description': 'This token is automatically generated and used by external platforms to authenticate API requests. Keep it secure!'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def token_preview(self, obj):
        if obj.api_token:
            return f"{obj.api_token[:8]}...{obj.api_token[-8:]}"
        return "No token"
    token_preview.short_description = "Token Preview"
    
    def get_readonly_fields(self, request, obj=None):
        # Make api_token readonly after creation
        if obj:  # editing an existing object
            return self.readonly_fields
        return ('created_at', 'updated_at')  # allow setting token on creation

# QRCode Admin
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'appointment', 'status', 'expires_at', 'revoked', 'created_at')
    list_filter = ('status', 'revoked', 'created_at', 'expires_at')
    search_fields = ('code', 'appointment__patient__first_name', 'appointment__patient__last_name')
    ordering = ('-created_at',)
    readonly_fields = ('code', 'created_at')
    
    fieldsets = (
        ('QR Code Information', {
            'fields': ('code', 'appointment', 'status', 'revoked')
        }),
        ('Expiration', {
            'fields': ('expires_at',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

# Register all models with the custom admin site
medical_admin_site.register(User, CustomUserAdmin)
medical_admin_site.register(Doctor, DoctorAdmin)
medical_admin_site.register(Patient, PatientAdmin)
medical_admin_site.register(Appointment, AppointmentAdmin)
medical_admin_site.register(Terminal, TerminalAdmin)
medical_admin_site.register(Integration, IntegrationAdmin)
medical_admin_site.register(QRCode, QRCodeAdmin)

# Also register with default admin site for super admin users
admin.site.register(User, CustomUserAdmin)
admin.site.register(Doctor, DoctorAdmin)
admin.site.register(Patient, PatientAdmin)
admin.site.register(Appointment, AppointmentAdmin)
admin.site.register(Terminal, TerminalAdmin)
admin.site.register(Integration, IntegrationAdmin)
admin.site.register(QRCode, QRCodeAdmin)