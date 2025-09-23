from django.urls import path
from . import views
from .views_events import validate_qr_and_open_door, hik_event_receiver, get_terminal_mode_api
from .api_views import create_appointment_api, validate_qr_code_api

app_name = 'medical_access'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),

    path('patient-registration/', views.patient_registration_view, name='patient_registration'),
    path('appointments/', views.appointments_view, name='appointments'),

    path('appointment/<int:appointment_id>/', views.appointment_detail, name='appointment_detail'),
    path('appointment/<int:appointment_id>/qr/', views.create_qr_code, name='create_qr'),
    path('appointment/<int:appointment_id>/receipt/', views.generate_qr_code_image, name='generate_receipt'),

    # Terminals
    path('terminals/', views.terminals_view, name='terminals'),
    path('terminals/<int:terminal_id>/open/', views.terminal_open_door_api, name='terminal_open_door'),

    # Kiosk
    path('kiosk/', views.kiosk_view, name='kiosk'),

    # API endpoints (CRUD)
    path('create-appointment/', views.create_appointment, name='create_appointment'),

    # Appointment CRUD
    path('appointments/<int:appointment_id>/update/', views.update_appointment, name='update_appointment'),
    path('appointments/<int:appointment_id>/delete/', views.delete_appointment, name='delete_appointment'),

    # Admin terminal actions
    path('admin/terminals/<int:pk>/health/', views.admin_terminal_health, name='admin_terminal_health'),
    path('admin/terminals/<int:pk>/open/', views.admin_terminal_open, name='admin_terminal_open'),

    # Remote validation + Hik events
    path('terminals/<int:terminal_id>/validate-qr/', validate_qr_and_open_door, name='validate_qr_and_open_door'),
    path('terminals/<str:terminal_ip>/mode/', get_terminal_mode_api, name='get_terminal_mode'),
    path('hik/events/', hik_event_receiver, name='hik_events'),

    # External API endpoints
    path('api/create-appointment/', create_appointment_api, name='api_create_appointment'),
    path('api/validate-qr/', validate_qr_code_api, name='api_validate_qr'),

    # Health check endpoint for terminal testing
    path('health/', views.health_check, name='health_check'),
]