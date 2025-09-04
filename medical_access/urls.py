from django.urls import path
from . import views
from .views_hik import hik_event_webhook
from .views_api import qr_verify

# Force load signals to ensure they are registered
from . import signals  # noqa

app_name = 'medical_access'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),

    path('patient-registration/', views.patient_registration_view, name='patient_registration'),
    path('doctors/', views.doctors_view, name='doctors'),
    path('procedures/', views.procedures_view, name='procedures'),
    path('patients/', views.patients_view, name='patients'),
    path('appointment/<int:appointment_id>/', views.appointment_detail, name='appointment_detail'),
    path('appointment/<int:appointment_id>/qr/', views.create_qr, name='create_qr'),
    path('appointment/<int:appointment_id>/receipt/', views.generate_receipt, name='generate_receipt'),
    path('create-appointment/', views.create_appointment, name='create_appointment'),
    path('create-doctor/', views.create_doctor, name='create_doctor'),
    path('create-procedure/', views.create_procedure, name='create_procedure'),
    path('update-doctor/<int:doctor_id>/', views.update_doctor, name='update_doctor'),
    path('delete-doctor/<int:doctor_id>/', views.delete_doctor, name='delete_doctor'),
    path('procedures/<int:procedure_id>/', views.get_procedure, name='get_procedure'),
    path('procedures/<int:procedure_id>/doctors/', views.get_procedure_doctors, name='get_procedure_doctors'),
    path('update-procedure/<int:procedure_id>/', views.update_procedure, name='update_procedure'),
    path('delete-procedure/<int:procedure_id>/', views.delete_procedure, name='delete_procedure'),
    # Patient CRUD operations
    path('patients/create/', views.create_patient, name='create_patient'),
    path('patients/<int:patient_id>/', views.get_patient, name='get_patient'),
    path('patients/<int:patient_id>/update/', views.update_patient, name='update_patient'),
    path('patients/<int:patient_id>/delete/', views.delete_patient, name='delete_patient'),
    path('appointments/', views.appointments_view, name='appointments'),
    path('appointments/create/', views.create_appointment_admin, name='create_appointment_admin'),
    path('appointments/<int:appointment_id>/update/', views.update_appointment, name='update_appointment'),
    path('appointments/<int:appointment_id>/delete/', views.delete_appointment, name='delete_appointment'),
    path('appointment/<int:appointment_id>/revoke/', views.revoke_pass, name='revoke_pass'),
    
    # QR Verification API
    path('api/qr/verify/', qr_verify, name='qr_verify_api'),
    path('api/door/remote-open/', views.remote_open_door_api, name='remote_open_door'),
    path('kiosk/', views.kiosk_view, name='kiosk'),
    path('appointment/<int:appointment_id>/provision/', views.provision_appointment_to_terminals, name='provision_appointment'),
    
    # Hikvision Event Listener
    path('hik/events/', hik_event_webhook, name='hik_event_webhook'),
]