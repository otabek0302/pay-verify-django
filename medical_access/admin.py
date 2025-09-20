from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse
from .models import User, Patient, Appointment, Terminal, Integration, QRCode
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

# Patient Admin
class PatientAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'medical_card_number', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('first_name', 'last_name', 'medical_card_number')
    ordering = ('last_name', 'first_name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'medical_card_number')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# Appointment Admin
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('patient__first_name', 'patient__last_name', 'patient__medical_card_number')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    actions = []
    
    fieldsets = (
        ('Appointment Details', {
            'fields': ('patient',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    

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
    list_display = ('name', 'is_active', 'token_preview', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    ordering = ('name',)
    readonly_fields = ('api_token', 'token_preview', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Integration Information', {
            'fields': ('name', 'is_active'),
            'description': 'Create integration for external partners. They will use the generated token to authenticate API requests.'
        }),
        ('API Token', {
            'fields': ('token_preview', 'api_token'),
            'description': 'This token is automatically generated and used by partners to authenticate API requests. Share this token securely with your partners!'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

# QRCode Admin
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'appointment', 'status', 'expires_at', 'revoked', 'created_at')
    list_filter = ('status', 'revoked', 'created_at')
    search_fields = ('code',)
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
medical_admin_site.register(Patient, PatientAdmin)
medical_admin_site.register(Appointment, AppointmentAdmin)
medical_admin_site.register(Terminal, TerminalAdmin)
medical_admin_site.register(Integration, IntegrationAdmin)
medical_admin_site.register(QRCode, QRCodeAdmin)

# Also register with default admin site for super admin users
admin.site.register(User, CustomUserAdmin)
admin.site.register(Patient, PatientAdmin)
admin.site.register(Appointment, AppointmentAdmin)
admin.site.register(Terminal, TerminalAdmin)
admin.site.register(Integration, IntegrationAdmin)
admin.site.register(QRCode, QRCodeAdmin)