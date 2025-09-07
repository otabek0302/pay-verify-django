from django.urls import path
from . import views
from .views_events import hik_event_receiver, dmed_create_appointment, dmed_appointment_status

app_name = 'medical_access'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),

    path('patient-registration/', views.patient_registration_view, name='patient_registration'),
    path('doctors/', views.doctors_view, name='doctors'),
    path('patients/', views.patients_view, name='patients'),
    path('appointments/', views.appointments_view, name='appointments'),
    
    path('appointment/<int:appointment_id>/', views.appointment_detail, name='appointment_detail'),
    path('appointment/<int:appointment_id>/qr/', views.create_qr, name='create_qr'),
    path('appointment/<int:appointment_id>/receipt/', views.generate_receipt, name='generate_receipt'),
    
    # Terminals
    path('terminals/', views.terminals_view, name='terminals'),
    path('terminals/<int:terminal_id>/open/', views.terminal_open_door_api, name='terminal_open_door'),
    
    # QR Scanner/Kiosk
    path('kiosk/', views.kiosk_view, name='kiosk'),
    path('verify-appointment/<str:code>/', views.verify_appointment, name='verify_appointment'),
    
    # API endpoints
    path('create-appointment/', views.create_appointment, name='create_appointment'),
    path('create-doctor/', views.create_doctor, name='create_doctor'),
    path('create-patient/', views.create_patient, name='create_patient'),
    
    # Doctor CRUD
    path('doctors/<int:doctor_id>/', views.get_doctor, name='get_doctor'),
    path('update-doctor/<int:doctor_id>/', views.update_doctor, name='update_doctor'),
    path('delete-doctor/<int:doctor_id>/', views.delete_doctor, name='delete_doctor'),
    
    # Patient CRUD
    path('patients/<int:patient_id>/', views.get_patient, name='get_patient'),
    path('patients/<int:patient_id>/update/', views.update_patient, name='update_patient'),
    path('patients/<int:patient_id>/delete/', views.delete_patient, name='delete_patient'),
    
    # Appointment CRUD
    path('appointments/<int:appointment_id>/update/', views.update_appointment, name='update_appointment'),
    path('appointments/<int:appointment_id>/delete/', views.delete_appointment, name='delete_appointment'),
    
    # Admin terminal actions
    path('admin/terminals/<int:pk>/health/', views.admin_terminal_health, name='admin_terminal_health'),
    path('admin/terminals/<int:pk>/open/', views.admin_terminal_open, name='admin_terminal_open'),
    
    # REMOVED: Appointment repush API - Not needed for Remote-Only Mode
    
    # QR validation and door control
    path('terminals/<int:terminal_id>/validate-qr/', views.validate_qr_and_open_door, name='validate_qr_and_open_door'),
    
    # Scan event logging (console only)
    path('scan-events/', views.log_scan_event, name='log_scan_event'),
    path('terminals/<str:terminal_ip>/mode/', views.get_terminal_mode_api, name='get_terminal_mode'),
    
    # Get recent scans from terminal
    path('terminals/<int:pk>/last-scans/', views.last_scans, name='terminal_last_scans'),
    
    # Hikvision event push receiver
    path('hik/events/', hik_event_receiver, name='hik_events'),
    
    # DMED Platform Integration APIs
    path('dmed/appointments/', dmed_create_appointment, name='dmed_create_appointment'),
    path('dmed/appointments/<int:appointment_id>/status/', dmed_appointment_status, name='dmed_appointment_status'),
]