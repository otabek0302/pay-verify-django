from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Sum, Count, Q
import json
import io
import uuid
import qrcode
from datetime import timedelta, date
from .models import User, Doctor, Patient, Appointment, Procedure, Door, AccessEvent
from .controller.hik_client import HikClient
from django.views.decorators.csrf import csrf_exempt

def _qr_png(payload: str) -> bytes:
    """Generate QR code PNG image from payload"""
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def _provision_to_all_doors(card_no: str, person_name: str, valid_from=None, valid_to=None) -> dict:
    """
    Push user+card+rights to every active Door.
    Returns {'ok': [...], 'fail': [(door_id, err), ...]}
    """
    results = {"ok": [], "fail": []}
    doors_qs = Door.objects.all()
    # if you have 'active' field, use: Door.objects.filter(active=True)
    
    # Format times for Hikvision API
    begin_time = valid_from.strftime("%Y-%m-%dT%H:%M:%SZ") if valid_from else None
    end_time = valid_to.strftime("%Y-%m-%dT%H:%M:%SZ") if valid_to else None
    
    for door in doors_qs:
        try:
            client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
            client.ping()
            
            # Use appointment ID as employee number for uniqueness
            employee_no = f"TEMP{card_no}"
            
            client.create_user(employee_no, person_name, valid_from, valid_to)
            client.bind_card(employee_no, card_no, valid_from, valid_to)
            # if Door has room_number/door_no use it; else default 1
            door_no = getattr(door, "room_number", getattr(door, "door_no", 1))
            client.grant_door(employee_no, door_no=door_no)
            results["ok"].append(door.id)
        except Exception as e:
            results["fail"].append((door.id, str(e)))
    return results

def _revoke_from_all_doors(card_no: str) -> dict:
    """
    Remove user+card+rights from every Door.
    Returns {'ok': [...], 'fail': [(door_id, err), ...]}
    """
    results = {"ok": [], "fail": []}
    doors_qs = Door.objects.all()
    
    for door in doors_qs:
        try:
            client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
            employee_no = f"TEMP{card_no}"
            client.delete_user(employee_no)
            results["ok"].append(door.id)
        except Exception as e:
            results["fail"].append((door.id, str(e)))
    
    return results

def home_view(request):
    """Home page - redirect to login if not authenticated, otherwise to dashboard"""
    if request.user.is_authenticated:
        return redirect('medical_access:dashboard')
    return redirect('medical_access:login')

def login_view(request):
    """Login view"""
    if request.user.is_authenticated:
        return redirect('medical_access:dashboard')
    
    if request.method == 'POST':
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({'success': True, 'message': 'Login successful! Redirecting...', 'redirect': 'medical_access:dashboard'})
        else:
            return JsonResponse({'success': False, 'message': 'Invalid username or password'}, status=400)
    
    return render(request, 'medical_access/login.html')

def logout_view(request):
    """Logout view"""
    logout(request)
    return redirect('medical_access:login')

@login_required
def dashboard_view(request):
    """Main dashboard view with statistics"""
    today = timezone.now().date()
    
    # Calculate comprehensive statistics
    today_revenue = Appointment.objects.filter(
        appointment_date=today,
        paid=True
    ).aggregate(total=Sum('procedure__price'))['total'] or 0
    
    today_receipts = Appointment.objects.filter(
        appointment_date=today
    ).count()
    
    scans_24h_allow = Appointment.objects.filter(
        valid_from__gte=timezone.now() - timedelta(hours=24),
        status='used'
    ).count()
    
    scans_24h_deny = Appointment.objects.filter(
        valid_from__gte=timezone.now() - timedelta(hours=24),
        status='expired'
    ).count()
    
    active_posts = Appointment.objects.filter(
        status='active',
        valid_from__lte=timezone.now(),
        valid_to__gte=timezone.now()
    ).count()
    
    active_doctors = Doctor.objects.count()
    active_procedures = Procedure.objects.count()
    total_patients = Patient.objects.count()
    total_locations = 0  # Doors are now independent, not tied to procedures
    
    # Get latest appointments
    latest_appointments = Appointment.objects.select_related(
        'patient', 'doctor', 'procedure'
    ).order_by('-created_at')[:12]
    
    context = {
        'user': request.user,
        'statistics': {
            'today_revenue': today_revenue,
            'today_receipts': today_receipts,
            'scans_24h_allow': scans_24h_allow,
            'scans_24h_deny': scans_24h_deny,
            'active_posts': active_posts,
            'active_doctors': active_doctors,
            'active_procedures': active_procedures,
            'total_patients': total_patients,
            'total_locations': total_locations,
        },
        'latest_appointments': latest_appointments,
    }
    return render(request, 'medical_access/dashboard.html', context)



@login_required
def patient_registration_view(request):
    """Cash register view with statistics and appointment management"""
    today = timezone.now().date()
    
    # Calculate statistics
    today_revenue = Appointment.objects.filter(
        appointment_date=today,
        paid=True
    ).aggregate(total=Sum('procedure__price'))['total'] or 0
    
    today_receipts = Appointment.objects.filter(
        appointment_date=today
    ).count()
    
    today_entrances = Appointment.objects.filter(
        valid_from__date=today,
        status='used'
    ).count()
    
    today_exits = Appointment.objects.filter(
        valid_from__date=today,
        status='used'
    ).count()
    
    active_qr_codes = Appointment.objects.filter(
        status='active',
        valid_from__lte=timezone.now(),
        valid_to__gte=timezone.now()
    ).count()
    
    # Get latest appointments
    latest_appointments = Appointment.objects.select_related(
        'patient', 'doctor', 'procedure'
    ).order_by('-created_at')[:10]
    
    # Get procedures and doctors for form
    procedures = Procedure.objects.all()
    doctors = Doctor.objects.all()
    
    context = {
        'user': request.user,
        'statistics': {
            'today_revenue': today_revenue,
            'today_receipts': today_receipts,
            'today_entrances': today_entrances,
            'today_exits': today_exits,
            'active_qr_codes': active_qr_codes,
        },
        'latest_appointments': latest_appointments,
        'procedures': procedures,
        'doctors': doctors,
    }
    return render(request, 'medical_access/patient_registration.html', context)

@login_required
def doctors_view(request):
    """Doctors list view"""
    doctors = Doctor.objects.all()
    context = {
        'user': request.user,
        'doctors': doctors,
    }
    return render(request, 'medical_access/doctors.html', context)

@login_required
def procedures_view(request):
    """Procedures list view"""
    procedures = Procedure.objects.all()
    doctors = Doctor.objects.all()  # Add doctors for the form
    context = {
        'user': request.user,
        'procedures': procedures,
        'doctors': doctors,  # Include doctors in context
    }
    return render(request, 'medical_access/procedures.html', context)

@login_required
def patients_view(request):
    """Patients list view"""
    patients = Patient.objects.all()
    context = {
        'user': request.user,
        'patients': patients,
    }
    return render(request, 'medical_access/patients.html', context)

@require_POST
@login_required
def create_doctor(request):
    """Create new doctor - admin only"""
    if request.user.role != User.Role.ADMIN:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        full_name = data.get('full_name')
        
        if not full_name:
            return JsonResponse({'success': False, 'message': 'Full name is required'}, status=400)
        
        # Split full name into first and last name
        name_parts = full_name.split()
        first_name = name_parts[0] if name_parts else ''
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
        
        # Create doctor directly
        doctor = Doctor.objects.create(
            first_name=first_name,
            last_name=last_name
        )
        
        return JsonResponse({
            'success': True, 
            'message': 'Doctor created successfully',
            'doctor_id': doctor.id
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@require_POST
@login_required
def create_procedure(request):
    """Create new procedure - admin only"""
    if request.user.role != User.Role.ADMIN:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        title = data.get('title')
        price = data.get('price')
        doctor_ids = data.get('doctors', [])
        
        if not title or not price:
            return JsonResponse({'success': False, 'message': 'Title and price are required'}, status=400)
        
        # Create procedure
        procedure = Procedure.objects.create(
            title=title,
            price=price
        )
        
        # Assign doctors if provided
        if doctor_ids:
            doctors = Doctor.objects.filter(id__in=doctor_ids)
            procedure.doctors.set(doctors)
        
        return JsonResponse({
            'success': True,
            'message': f'Procedure "{title}" created successfully',
            'procedure': {
                'id': procedure.id,
                'title': procedure.title,
                'price': str(procedure.price)
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@require_POST
@login_required
def update_doctor(request, doctor_id):
    """Update doctor - admin only"""
    if request.user.role != User.Role.ADMIN:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    try:
        doctor = get_object_or_404(Doctor, id=doctor_id)
        data = json.loads(request.body)
        
        # Update doctor fields
        if data.get('full_name'):
            name_parts = data['full_name'].split()
            doctor.first_name = name_parts[0] if name_parts else ''
            doctor.last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
        
        doctor.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Doctor updated successfully',
            'doctor': {
                'full_name': doctor.full_name,
                'first_name': doctor.first_name,
                'last_name': doctor.last_name
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@require_POST
@login_required
def delete_doctor(request, doctor_id):
    """Delete doctor - admin only"""
    if request.user.role != User.Role.ADMIN:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    try:
        doctor = get_object_or_404(Doctor, id=doctor_id)
        doctor_name = doctor.full_name
        
        # Check if doctor has appointments
        if doctor.appointments.exists():
            return JsonResponse({
                'success': False, 
                'message': 'Cannot delete doctor with existing appointments. Please delete appointments first.'
            }, status=400)
        
        # Delete the doctor
        doctor.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Doctor "{doctor_name}" deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@require_POST
@login_required
def create_appointment(request):
    """Create new appointment/receipt"""
    try:
        data = json.loads(request.body)
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        phone = data.get('phone', '')
        procedure_id = data.get('procedure_id')
        doctor_id = data.get('doctor_id')
        amount = data.get('amount')
        
        if not first_name or not last_name or not procedure_id:
            return JsonResponse({'success': False, 'message': 'First name, last name, and procedure are required'}, status=400)
        
        # Get or create patient based on phone number (if provided) or name
        if phone:
            # Try to find existing patient by phone
            try:
                patient = Patient.objects.get(phone=phone)
                # Update patient info if name has changed
                if patient.first_name != first_name or patient.last_name != last_name:
                    patient.first_name = first_name
                    patient.last_name = last_name
                    patient.save()
            except Patient.DoesNotExist:
                # Create new patient
                patient = Patient.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone
                )
        else:
            # No phone provided, create new patient with just name
            patient = Patient.objects.create(
                first_name=first_name,
                last_name=last_name
            )
        
        procedure = get_object_or_404(Procedure, id=procedure_id)
        doctor = None
        if doctor_id:
            doctor = get_object_or_404(Doctor, id=doctor_id)
        
        # Create appointment with QR code fields
        now = timezone.now()
        valid_to = now + timedelta(hours=24)  # 24 hours validity
        
        appointment = Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            procedure=procedure,
            appointment_date=timezone.now().date(),
            appointment_time=timezone.now().time(),
            paid=True,  # Default to paid
            status='active',
            valid_from=now,
            valid_to=valid_to
        )
        
        return JsonResponse({
            'success': True, 
            'message': 'Appointment created successfully',
            'appointment_id': appointment.id
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@require_POST
@login_required
def create_qr(request, appointment_id):
    """Create QR code for appointment access with 24h validity and provision to all doors"""
    try:
        appointment = get_object_or_404(
            Appointment.objects.select_related('patient'),
            id=appointment_id
        )
        
        if not appointment.paid:
            return JsonResponse({"error": "Payment required"}, status=400)
        
        if appointment.appointment_datetime <= timezone.now():
            return JsonResponse({"error": "Appointment has already passed"}, status=400)

        # Use existing card_no from appointment
        card_no = appointment.card_no
        payload = appointment.qr_payload

        # Provision to all doors with validity times (ISAPI hardware integration)
        person_name = getattr(appointment.patient, "full_name", None) or "Patient"
        try:
            provision = _provision_to_all_doors(card_no, person_name, appointment.valid_from, appointment.valid_to)
            print(f"[PROVISION] Card {card_no}: Success={len(provision['ok'])}, Failed={len(provision['fail'])}")
            if provision['fail']:
                print(f"[PROVISION] Failed doors: {provision['fail']}")
        except Exception as e:
            print(f"[PROVISION] Error provisioning card {card_no}: {e}")
            # Continue anyway - kiosk verification will still work

        # Return QR image
        response = HttpResponse(_qr_png(payload), content_type="image/png")
        response['Content-Disposition'] = f'attachment; filename="qr_pass_{card_no}.png"'
        return response

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@login_required
def generate_receipt(request, appointment_id):
    """Generate and display receipt with QR code"""
    try:
        appointment = get_object_or_404(
            Appointment.objects.select_related('patient', 'doctor', 'procedure'),
            id=appointment_id
        )
        
        # Generate QR code from appointment's card_no or qr_payload
        qr_data = appointment.qr_payload or appointment.card_no or str(appointment.id)
        img = qrcode.make(qr_data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        
        # Convert to base64 for embedding in HTML
        import base64
        qr_code_base64 = base64.b64encode(buf.getvalue()).decode()
        
        context = {
            'appointment': appointment,
            'qr_code_base64': qr_code_base64,
            'user': request.user,
        }
        
        return render(request, 'medical_access/receipt.html', context)
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@login_required
def appointment_detail(request, appointment_id):
    """View appointment details and generate QR if needed"""
    appointment = get_object_or_404(
        Appointment.objects.select_related('patient', 'doctor', 'procedure'),
        id=appointment_id
    )

    context = {
        'appointment': appointment,
        'user': request.user,
    }
    return render(request, 'medical_access/appointment_detail.html', context)

@require_POST
@login_required
def delete_procedure(request, procedure_id):
    """Delete procedure - admin only"""
    if request.user.role != User.Role.ADMIN:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    try:
        procedure = get_object_or_404(Procedure, id=procedure_id)
        procedure_name = procedure.title
        
        procedure.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Procedure "{procedure_name}" deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
def get_procedure(request, procedure_id):
    """Get procedure details for editing"""
    try:
        procedure = get_object_or_404(Procedure, id=procedure_id)
        
        return JsonResponse({
            'success': True,
            'procedure': {
                'id': procedure.id,
                'title': procedure.title,
                'price': procedure.price,
                'doctors': [doctor.id for doctor in procedure.doctors.all()]
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
def get_procedure_doctors(request, procedure_id):
    """Get doctors assigned to a specific procedure for appointment creation"""
    try:
        procedure = get_object_or_404(Procedure, id=procedure_id)
        doctors = procedure.doctors.all()
        
        return JsonResponse({
            'success': True,
            'doctors': [
                {
                    'id': doctor.id,
                    'full_name': doctor.full_name,
                    'first_name': doctor.first_name,
                    'last_name': doctor.last_name
                }
                for doctor in doctors
            ]
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@require_POST
@login_required
def update_procedure(request, procedure_id):
    """Update procedure - admin only"""
    if request.user.role != User.Role.ADMIN:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    try:
        procedure = get_object_or_404(Procedure, id=procedure_id)
        data = json.loads(request.body)
        
        if data.get('title'):
            procedure.title = data['title']
        
        if data.get('price'):
            procedure.price = data['price']

        procedure.save()
        
        # Update doctor assignments
        if 'doctors' in data:
            doctor_ids = data['doctors']
            doctors = Doctor.objects.filter(id__in=doctor_ids)
            procedure.doctors.set(doctors)
        
        return JsonResponse({
            'success': True,
            'message': 'Procedure updated successfully',
            'procedure': {
                'id': procedure.id,
                'title': procedure.title,
                'price': procedure.price,
                'doctors': [doctor.id for doctor in procedure.doctors.all()]
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
def get_patient(request, patient_id):
    """Get patient details for editing"""
    try:
        patient = get_object_or_404(Patient, id=patient_id)
        return JsonResponse({
            'success': True,
            'patient': {
                'id': patient.id,
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'phone': patient.phone,
                'full_name': patient.full_name,
                'created_at': patient.created_at.isoformat(),
                'updated_at': patient.updated_at.isoformat()
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
def create_patient(request):
    """Create a new patient"""
    if request.method == 'POST':
        try:
            data = request.POST
            patient = Patient.objects.create(
                first_name=data.get('first_name', '').strip(),
                last_name=data.get('last_name', '').strip(),
                phone=data.get('phone', '').strip() or None
            )
            return JsonResponse({
                'success': True,
                'message': 'Patient created successfully',
                'patient': {
                    'id': patient.id,
                    'first_name': patient.first_name,
                    'last_name': patient.last_name,
                    'phone': patient.phone,
                    'full_name': patient.full_name,
                    'created_at': patient.created_at.strftime('%d/%m/%Y %H:%M')
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@login_required
def update_patient(request, patient_id):
    """Update an existing patient"""
    if request.method == 'POST':
        try:
            patient = get_object_or_404(Patient, id=patient_id)
            data = request.POST
            
            patient.first_name = data.get('first_name', '').strip()
            patient.last_name = data.get('last_name', '').strip()
            patient.phone = data.get('phone', '').strip() or None
            
            patient.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Patient updated successfully',
                'patient': {
                    'id': patient.id,
                    'first_name': patient.first_name,
                    'last_name': patient.last_name,
                    'phone': patient.phone,
                    'full_name': patient.full_name
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@login_required
def delete_patient(request, patient_id):
    """Delete a patient"""
    if request.method == 'POST':
        try:
            patient = get_object_or_404(Patient, id=patient_id)
            
            # Check if patient has appointments
            if patient.appointments.exists():
                return JsonResponse({
                    'success': False, 
                    'message': 'Cannot delete patient with existing appointments. Please delete appointments first.'
                }, status=400)
            
            patient.delete()
            return JsonResponse({'success': True, 'message': 'Patient deleted successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@login_required
def appointments_view(request):
    """View for managing appointments (admin only)"""
    print(f"DEBUG: User role: {request.user.role}, User: {request.user.username}")
    if request.user.role != User.Role.ADMIN:
        print(f"DEBUG: Redirecting to dashboard - user role is {request.user.role}")
        return redirect('medical_access:dashboard')
    
    print(f"DEBUG: User is admin, proceeding to appointments view")
    appointments = Appointment.objects.select_related(
        'patient', 'doctor', 'procedure'
    ).order_by('-appointment_date', '-appointment_time')
    
    context = {
        'appointments': appointments,
        'doctors': Doctor.objects.all(),
        'procedures': Procedure.objects.all(),
        'patients': Patient.objects.all(),
    }
    
    return render(request, 'medical_access/appointments.html', context)

@login_required
def create_appointment_admin(request):
    """Create a new appointment from admin panel"""
    if request.user.role != User.Role.ADMIN:
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        try:
            data = request.POST
            
            # Get the related objects
            patient = get_object_or_404(Patient, id=data.get('patient_id'))
            doctor = get_object_or_404(Doctor, id=data.get('doctor_id'))
            procedure = get_object_or_404(Procedure, id=data.get('procedure_id'))
            
            # Create the appointment
            appointment = Appointment.objects.create(
                patient=patient,
                doctor=doctor,
                procedure=procedure,
                appointment_date=data.get('appointment_date'),
                appointment_time=data.get('appointment_time'),
                status=data.get('status', 'scheduled'),

                paid=data.get('paid') == 'on'
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Appointment created successfully',
                'appointment': {
                    'id': appointment.id,
                    'patient_name': appointment.patient.full_name,
                    'procedure_name': appointment.procedure.title,
                    'doctor_name': appointment.doctor.full_name,
                    'date': appointment.appointment_date.strftime('%d/%m/%Y'),
                    'time': appointment.appointment_time.strftime('%H:%M'),
                    'status': appointment.get_status_display(),
                    'paid': 'Paid' if appointment.paid else 'Unpaid'
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@login_required
def update_appointment(request, appointment_id):
    """Update an existing appointment"""
    if request.user.role != User.Role.ADMIN:
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        try:
            appointment = get_object_or_404(Appointment, id=appointment_id)
            data = request.POST
            
            # Update the related objects
            if data.get('patient_id'):
                appointment.patient = get_object_or_404(Patient, id=data.get('patient_id'))
            if data.get('doctor_id'):
                appointment.doctor = get_object_or_404(Doctor, id=data.get('doctor_id'))
            if data.get('procedure_id'):
                appointment.procedure = get_object_or_404(Procedure, id=data.get('procedure_id'))
            
            # Update other fields
            if data.get('appointment_date'):
                appointment.appointment_date = data.get('appointment_date')
            if data.get('appointment_time'):
                appointment.appointment_time = data.get('appointment_time')
            if data.get('status'):
                appointment.status = data.get('status')

            # Always set paid to True since all appointments are paid by default
            appointment.paid = True
            appointment.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Appointment updated successfully',
                'appointment': {
                    'id': appointment.id,
                    'patient_name': appointment.patient.full_name,
                    'procedure_name': appointment.procedure.title,
                    'doctor_name': appointment.doctor.full_name,
                    'date': appointment.appointment_date.strftime('%d/%m/%Y'),
                    'time': appointment.appointment_time.strftime('%H:%M'),
                    'status': appointment.get_status_display()
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@login_required
def delete_appointment(request, appointment_id):
    """Delete an appointment"""
    if request.user.role != User.Role.ADMIN:
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        try:
            appointment = get_object_or_404(Appointment, id=appointment_id)
            
            # Handle all related data before deleting appointment
            from medical_access.models import AccessEvent
            from django.db import connection
            
            # 1. Set appointment to null in AccessEvent records (preserve audit data)
            AccessEvent.objects.filter(appointment=appointment).update(appointment=None)
            
            # 2. Get appointment details for logging
            appointment_info = f"{appointment.patient.full_name} - {appointment.procedure.title}"
            
            # 3. Use raw SQL to delete appointment (bypass foreign key constraints)
            with connection.cursor() as cursor:
                # Temporarily disable foreign key constraints
                cursor.execute("PRAGMA foreign_keys=OFF")
                try:
                    # Delete the appointment
                    cursor.execute("DELETE FROM medical_access_appointment WHERE id = %s", [appointment_id])
                finally:
                    # Re-enable foreign key constraints
                    cursor.execute("PRAGMA foreign_keys=ON")
            
            return JsonResponse({
                'success': True, 
                'message': f'Appointment "{appointment_info}" deleted successfully'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@login_required
def revoke_pass(request, appointment_id):
    """Manually revoke an appointment from all doors"""
    if request.user.role != User.Role.ADMIN:
        return JsonResponse({'success': False, 'message': 'Admin access required'}, status=403)
    
    try:
        appointment = get_object_or_404(Appointment, id=appointment_id)
        
        # Check if appointment is active
        if appointment.status != 'active' or not appointment.card_no:
            return JsonResponse({'success': False, 'message': 'No active appointment found'}, status=404)
        
        # Revoke from all doors
        revoke_results = _revoke_from_all_doors(appointment.card_no)
        
        # Mark as revoked
        appointment.status = 'revoked'
        appointment.used_at = timezone.now()
        appointment.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Appointment {appointment.card_no} revoked successfully',
            'revoke_results': revoke_results
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

# Import QR API functions
from .qr_api import qr_verify_api, kiosk_view, remote_open_door_api


@csrf_exempt
@require_POST
def provision_appointment_to_terminals(request, appointment_id):
    """
    Simple API to provision an appointment to all terminals.
    POST /medical_access/appointment/<id>/provision/
    """
    try:
        appointment = Appointment.objects.get(id=appointment_id)
        
        if not appointment.paid:
            return JsonResponse({
                'success': False,
                'error': 'Appointment must be paid before provisioning'
            }, status=400)
        
        # Check if appointment has QR code fields
        if not appointment.card_no:
            return JsonResponse({
                'success': False,
                'error': 'No QR code found for this appointment'
            }, status=400)
        
        if not appointment.card_no.isdigit():
            return JsonResponse({
                'success': False,
                'error': f'Invalid card number: {appointment.card_no} (must be numeric)'
            }, status=400)
        
        # Provision to all terminals
        results = []
        for door in Door.objects.all():
            try:
                client = HikClient(door.terminal_ip, door.terminal_username, door.terminal_password)
                
                # Create user
                employee_no = f"APT{appointment.id}"
                client.create_user(employee_no, appointment.patient.full_name, appointment.valid_from, appointment.valid_to)
                
                # Bind card
                client.bind_card(employee_no, appointment.card_no, appointment.valid_from, appointment.valid_to)
                
                # Skip door authorization (not supported)
                client.grant_door(employee_no, door_no=1, time_section_no=1)
                
                results.append({
                    'door': door.name,
                    'status': 'success',
                    'user': employee_no,
                    'card': temp_pass.card_no
                })
                
            except Exception as e:
                results.append({
                    'door': door.name,
                    'status': 'failed',
                    'error': str(e)
                })
        
        success_count = len([r for r in results if r['status'] == 'success'])
        
        return JsonResponse({
            'success': True,
            'message': f'Provisioned to {success_count}/{len(results)} terminals',
            'results': results
        })
        
    except Appointment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Appointment not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
