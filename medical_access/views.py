from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum
from django.core.paginator import Paginator
from django.contrib import messages
import json
import io
import base64
import qrcode
from datetime import timedelta
from .models import User, Doctor, Patient, Appointment, Terminal
from .services import probe_terminal, open_door, fetch_recent_scans, generate_simple_qr_code

def _qr_png(payload: str) -> bytes:
    """Generate QR code PNG image from payload"""
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

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
    # Get period from request (default to 'today')
    period = request.GET.get('period', 'today')
    now = timezone.now()
    
    # Calculate date range based on period
    if period == 'today':
        start_date = now.date()
        end_date = now.date()
        period_label = 'Today'
    elif period == 'week':
        start_date = now.date() - timedelta(days=now.weekday())
        end_date = start_date + timedelta(days=6)
        period_label = 'This Week'
    elif period == 'month':
        start_date = now.date().replace(day=1)
        if now.month == 12:
            end_date = now.date().replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = now.date().replace(month=now.month + 1, day=1) - timedelta(days=1)
        period_label = 'This Month'
    else:
        start_date = now.date()
        end_date = now.date()
        period_label = 'Today'
    
    # Calculate comprehensive statistics for the selected period
    period_revenue = Appointment.objects.filter(
        created_at__date__range=[start_date, end_date],
        status='active'
    ).aggregate(total=Sum('doctor__price'))['total'] or 0
    
    period_receipts = Appointment.objects.filter(
        created_at__date__range=[start_date, end_date]
    ).count()
    
    active_appointments = Appointment.objects.filter(
        status='active',
        valid_from__lte=timezone.now(),
        valid_till__gte=timezone.now()
    ).count()
    
    active_doctors = Doctor.objects.count()
    total_patients = Patient.objects.count()
    
    # Get latest appointments for the selected period
    latest_appointments = Appointment.objects.select_related(
        'patient', 'doctor'
    ).filter(
        created_at__date__range=[start_date, end_date]
    ).order_by('-created_at')[:12]
    
    context = {
        'user': request.user,
        'period': period,
        'period_label': period_label,
        'statistics': {
            'period_revenue': period_revenue,
            'period_receipts': period_receipts,
            'active_appointments': active_appointments,
            'active_doctors': active_doctors,
            'total_patients': total_patients,
        },
        'latest_appointments': latest_appointments,
    }
    return render(request, 'medical_access/dashboard.html', context)

@login_required
def patient_registration_view(request):
    """Patient registration view with appointment management"""
    today = timezone.now().date()
    
    # Calculate statistics
    today_revenue = Appointment.objects.filter(
        created_at__date=today,
        status='active'
    ).aggregate(total=Sum('doctor__price'))['total'] or 0
    
    today_receipts = Appointment.objects.filter(
        created_at__date=today
    ).count()
    
    active_qr_codes = Appointment.objects.filter(
        status='active',
        valid_from__lte=timezone.now(),
        valid_till__gte=timezone.now()
    ).count()
    
    # Get latest appointments
    latest_appointments = Appointment.objects.select_related(
        'patient', 'doctor'
    ).order_by('-created_at')[:10]
    
    # Get doctors for form
    doctors = Doctor.objects.all()
    
    context = {
        'user': request.user,
        'statistics': {
            'today_revenue': today_revenue,
            'today_receipts': today_receipts,
            'active_qr_codes': active_qr_codes,
        },
        'latest_appointments': latest_appointments,
        'doctors': doctors,
    }
    return render(request, 'medical_access/patient_registration.html', context)

@login_required
def doctors_view(request):
    """Doctors list view"""
    doctors = Doctor.objects.all().order_by('last_name', 'first_name')
    
    # Pagination
    paginator = Paginator(doctors, 12)  # Show 12 doctors per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'user': request.user,
        'doctors': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'medical_access/doctors.html', context)


@login_required
def patients_view(request):
    """Patients list view"""
    patients = Patient.objects.all().order_by('last_name', 'first_name')
    
    # Pagination
    paginator = Paginator(patients, 12)  # Show 12 patients per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'user': request.user,
        'patients': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'medical_access/patients.html', context)

@login_required
def appointments_view(request):
    """View for managing appointments (admin and super admin only)"""
    # Check user role and redirect accordingly
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return redirect('medical_access:dashboard')
    
    # User is admin, proceeding to appointments view
    appointments = Appointment.objects.select_related(
        'patient', 'doctor'
    ).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(appointments, 12)  # Show 12 appointments per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'appointments': page_obj,
        'page_obj': page_obj,
        'doctors': Doctor.objects.all(),
        'patients': Patient.objects.all(),
    }
    
    return render(request, 'medical_access/appointments.html', context)

@login_required
def terminals_view(request):
    """View for managing terminals (admin and super admin only)"""
    # Check user role and redirect accordingly
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return redirect('medical_access:dashboard')
    
    # Get all terminals
    terminals = Terminal.objects.all().order_by('terminal_name')
    
    # Pagination
    paginator = Paginator(terminals, 12)  # Show 12 terminals per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'terminals': page_obj,
        'page_obj': page_obj,
        'user': request.user,
    }
    
    return render(request, 'medical_access/terminals.html', context)

@login_required
def kiosk_view(request):
    """QR Scanner/Kiosk view for scanning appointment QR codes"""
    context = {
        'user': request.user,
    }
    return render(request, 'medical_access/kiosk.html', context)

@login_required
def verify_appointment(request, code):
    """Verify appointment by QR code or card number"""
    try:
        # Try to find appointment by QR code
        appointment = Appointment.objects.select_related(
            'patient', 'doctor'
        ).filter(
            qr_code=code
        ).first()
        
        if not appointment:
            return JsonResponse({
                'success': False,
                'message': 'Appointment not found with this code'
            }, status=404)
        
        # Check if appointment is valid
        if not appointment.is_valid:
            return JsonResponse({
                'success': False,
                'message': 'Appointment is no longer valid or has expired'
            }, status=400)
        
        # Mark as used if it's still active
        if appointment.status == Appointment.Status.ACTIVE:
            appointment.mark_as_used()
        
        return JsonResponse({
            'success': True,
            'appointment': {
                'id': appointment.id,
                'patient': {
                    'full_name': appointment.patient.full_name,
                    'first_name': appointment.patient.first_name,
                    'last_name': appointment.patient.last_name,
                },
                'doctor': {
                    'full_name': appointment.doctor.full_name if appointment.doctor else None,
                    'first_name': appointment.doctor.first_name if appointment.doctor else None,
                    'last_name': appointment.doctor.last_name if appointment.doctor else None,
                } if appointment.doctor else None,
                'procedure': {
                    'title': appointment.doctor.procedure,
                    'price': str(appointment.doctor.price),
                },
                'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M'),
                'status': appointment.status,
                'qr_code': appointment.qr_code,
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

@login_required
def appointment_detail(request, appointment_id):
    """View appointment details and generate QR if needed"""
    appointment = get_object_or_404(
        Appointment.objects.select_related('patient', 'doctor'),
        id=appointment_id
    )

    context = {
        'appointment': appointment,
        'user': request.user,
    }
    return render(request, 'medical_access/appointment_detail.html', context)

# API Views for AJAX

@require_POST
@login_required
def create_doctor(request):
    """Create new doctor - admin and super admin only"""
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        
        # Handle both full_name and separate first_name/last_name
        if 'full_name' in data:
            full_name = data.get('full_name')
            if not full_name:
                return JsonResponse({'success': False, 'message': 'Full name is required'}, status=400)
            # Split full name into first and last name
            name_parts = full_name.split()
            first_name = name_parts[0] if name_parts else ''
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
        else:
            first_name = data.get('first_name', '').strip()
            last_name = data.get('last_name', '').strip()
            if not first_name and not last_name:
                return JsonResponse({'success': False, 'message': 'First name or last name is required'}, status=400)
        
        procedure = data.get('procedure', 'General Consultation').strip()
        price = data.get('price', 0.00)
        
        # Create doctor with procedure and price
        doctor = Doctor.objects.create(
            first_name=first_name,
            last_name=last_name,
            procedure=procedure,
            price=price
        )
        
        return JsonResponse({
            'success': True, 
            'message': 'Doctor created successfully',
            'doctor': {
                'id': doctor.id,
                'first_name': doctor.first_name,
                'last_name': doctor.last_name,
                'procedure': doctor.procedure,
                'price': str(doctor.price)
            }
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
        passport_series = data.get('passport_series', '')
        passport_number = data.get('passport_number', '')
        doctor_id = data.get('doctor_id')
        
        if not first_name or not last_name or not doctor_id:
            return JsonResponse({'success': False, 'message': 'First name, last name, and doctor are required'}, status=400)
        
        # Get or create patient based on phone number (if provided) or name
        if phone:
            # Try to find existing patient by phone
            try:
                patient = Patient.objects.get(phone=phone)
                # Update patient info if name has changed
                if patient.first_name != first_name or patient.last_name != last_name:
                    patient.first_name = first_name
                    patient.last_name = last_name
                    patient.passport_series = passport_series
                    patient.passport_number = passport_number
                    patient.save()
            except Patient.DoesNotExist:
                # Create new patient
                patient = Patient.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    passport_series=passport_series,
                    passport_number=passport_number
                )
        else:
            # No phone provided, create new patient with just name
            patient = Patient.objects.create(
                first_name=first_name,
                last_name=last_name,
                passport_series=passport_series,
                passport_number=passport_number
            )
        
        doctor = get_object_or_404(Doctor, id=doctor_id)
        
        # Create appointment with simple QR code
        now = timezone.now()
        valid_till = now + timedelta(hours=24)  # 24 hours validity
        
        # Generate simple 12-character QR code
        qr_code = generate_simple_qr_code()
        
        appointment = Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            status='active',
            valid_from=now,
            valid_till=valid_till,
            qr_code=qr_code
        )
        
        return JsonResponse({
            'success': True, 
            'message': 'Appointment created successfully',
            'appointment_id': appointment.id
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
def create_qr(request, appointment_id):
    """Create QR code for appointment access with 24h validity"""
    try:
        appointment = get_object_or_404(
            Appointment.objects.select_related('patient'),
            id=appointment_id
        )
        
        if not appointment.paid:
            return JsonResponse({"error": "Payment required"}, status=400)
        
        # Only check if appointment is active, not if it's in the past
        if appointment.status != 'active':
            return JsonResponse({"error": "Appointment is not active"}, status=400)

        # Use existing QR code from appointment
        qr_code = appointment.qr_code

        # Return QR image
        response = HttpResponse(_qr_png(qr_code), content_type="image/png")
        response['Content-Disposition'] = f'attachment; filename="qr_pass_{qr_code}.png"'
        return response

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@login_required
def generate_receipt(request, appointment_id):
    """Generate and display receipt with QR code"""
    try:
        appointment = get_object_or_404(
            Appointment.objects.select_related('patient', 'doctor'),
            id=appointment_id
        )
        
        # Generate QR code from appointment's qr_code field
        qr_data = appointment.qr_code or str(appointment.id)
        img = qrcode.make(qr_data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        
        # Convert to base64 for embedding in HTML
        qr_code_base64 = base64.b64encode(buf.getvalue()).decode()
        
        context = {
            'appointment': appointment,
            'qr_code_base64': qr_code_base64,
            'user': request.user,
        }
        
        return render(request, 'medical_access/receipt.html', context)
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# Additional CRUD operations for doctors, procedures, patients, appointments
# (Update, Delete, Get operations - keeping them simple)

@require_POST
@login_required
def update_doctor(request, doctor_id):
    """Update doctor - admin and super admin only"""
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    try:
        doctor = get_object_or_404(Doctor, id=doctor_id)
        data = json.loads(request.body)
        
        # Update doctor fields
        if data.get('full_name'):
            name_parts = data['full_name'].split()
            doctor.first_name = name_parts[0] if name_parts else ''
            doctor.last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
        elif data.get('first_name') or data.get('last_name'):
            # Handle separate first_name and last_name fields
            if data.get('first_name'):
                doctor.first_name = data.get('first_name').strip()
            if data.get('last_name'):
                doctor.last_name = data.get('last_name').strip()
        
        # Update procedure and price
        if data.get('procedure'):
            doctor.procedure = data.get('procedure').strip()
        if data.get('price'):
            doctor.price = data.get('price')
        
        doctor.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Doctor updated successfully',
            'doctor': {
                'id': doctor.id,
                'first_name': doctor.first_name,
                'last_name': doctor.last_name,
                'procedure': doctor.procedure,
                'price': str(doctor.price)
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@require_POST
@login_required
def delete_doctor(request, doctor_id):
    """Delete doctor - admin and super admin only"""
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
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

@login_required
def get_doctor(request, doctor_id):
    """Get doctor details for editing"""
    try:
        doctor = get_object_or_404(Doctor, id=doctor_id)
        
        return JsonResponse({
            'success': True,
            'doctor': {
                'id': doctor.id,
                'first_name': doctor.first_name,
                'last_name': doctor.last_name,
                'procedure': doctor.procedure,
                'price': str(doctor.price),
                'full_name': doctor.full_name
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
                'passport_series': patient.passport_series,
                'passport_number': patient.passport_number,
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
                phone=data.get('phone', '').strip() or None,
                passport_series=data.get('passport_series', '').strip() or None,
                passport_number=data.get('passport_number', '').strip() or None
            )
            return JsonResponse({
                'success': True,
                'message': 'Patient created successfully',
                'patient': {
                    'id': patient.id,
                    'first_name': patient.first_name,
                    'last_name': patient.last_name,
                    'phone': patient.phone,
                    'passport_series': patient.passport_series,
                    'passport_number': patient.passport_number,
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
            patient.passport_series = data.get('passport_series', '').strip() or None
            patient.passport_number = data.get('passport_number', '').strip() or None
            
            patient.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Patient updated successfully',
                'patient': {
                    'id': patient.id,
                    'first_name': patient.first_name,
                    'last_name': patient.last_name,
                    'phone': patient.phone,
                    'passport_series': patient.passport_series,
                    'passport_number': patient.passport_number,
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
def update_appointment(request, appointment_id):
    """Update an existing appointment"""
    if request.method == 'POST':
        try:
            appointment = get_object_or_404(Appointment, id=appointment_id)
            data = request.POST
            
            # Validate required fields
            if not data.get('patient_id'):
                return JsonResponse({'success': False, 'message': 'Patient is required'}, status=400)
            if not data.get('doctor_id'):
                return JsonResponse({'success': False, 'message': 'Doctor is required'}, status=400)
            
            # Check if patient exists
            try:
                patient = Patient.objects.get(id=data.get('patient_id'))
            except Patient.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Patient not found'}, status=400)
            
            # Check if doctor exists
            try:
                doctor = Doctor.objects.get(id=data.get('doctor_id'))
            except Doctor.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Doctor not found'}, status=400)
            
            # Update appointment fields
            appointment.patient = patient
            appointment.doctor = doctor
            
            # Update status if provided
            if data.get('status'):
                appointment.status = data.get('status')
            
            # Update QR code if provided and different
            new_qr_code = data.get('qr_code', '').strip()
            if new_qr_code and new_qr_code != appointment.qr_code:
                # Check if QR code already exists for another appointment
                if Appointment.objects.filter(qr_code=new_qr_code).exclude(id=appointment_id).exists():
                    return JsonResponse({'success': False, 'message': 'QR code already exists'}, status=400)
                appointment.qr_code = new_qr_code
            
            # Update validity dates if provided
            if data.get('valid_from'):
                from django.utils.dateparse import parse_datetime
                valid_from = parse_datetime(data.get('valid_from'))
                if valid_from:
                    appointment.valid_from = valid_from
            
            if data.get('valid_till'):
                from django.utils.dateparse import parse_datetime
                valid_till = parse_datetime(data.get('valid_till'))
                if valid_till:
                    appointment.valid_till = valid_till
            
            appointment.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Appointment updated successfully',
                'appointment': {
                    'id': appointment.id,
                    'patient_name': appointment.patient.full_name,
                    'doctor_name': appointment.doctor.full_name,
                    'doctor_procedure': appointment.doctor.procedure,
                    'doctor_price': float(appointment.doctor.price),
                    'status': appointment.get_status_display(),
                    'qr_code': appointment.qr_code,
                    'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M'),
                    'valid_from': appointment.valid_from.strftime('%Y-%m-%d %H:%M') if appointment.valid_from else None,
                    'valid_till': appointment.valid_till.strftime('%Y-%m-%d %H:%M') if appointment.valid_till else None,
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@login_required
def delete_appointment(request, appointment_id):
    """Delete an appointment and associated patient - admin and super admin only"""
    # Check user role and redirect accordingly
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)
    
    if request.method == 'POST':
        try:
            appointment = get_object_or_404(Appointment, id=appointment_id)
            
            # Get patient info before deletion
            patient = appointment.patient
            patient_name = patient.full_name
            
            # Delete the appointment first
            appointment.delete()
            
            # Delete the associated patient
            patient.delete()
            
            return JsonResponse({
                'success': True, 
                'message': f'Appointment and patient "{patient_name}" deleted successfully.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

# REMOVED: Terminal API Views - Redundant with admin actions

# Admin button views
@login_required
def admin_terminal_health(request, pk: int):
    """Admin view for terminal health check"""
    t = get_object_or_404(Terminal, pk=pk)
    res = probe_terminal(t)
    
    if res.get("ok"):
        messages.success(request, f'Terminal "{t.terminal_name}" is reachable!')
    else:
        messages.error(request, f'Terminal "{t.terminal_name}" is not reachable: {res.get("error", "Unknown error")}')
    
    return redirect('admin:medical_access_terminal_changelist')

@login_required
def admin_terminal_open(request, pk: int):
    """Admin view for opening terminal door"""
    t = get_object_or_404(Terminal, pk=pk)
    
    res = open_door(t, door_no=1)
    
    if res.get("ok"):
        messages.success(request, f'Door open command sent to "{t.terminal_name}"!')
    else:
        messages.error(request, f'Failed to open door on "{t.terminal_name}": {res.get("error", "Unknown error")}')
    
    return redirect('admin:medical_access_terminal_changelist')

# Manual repush API for appointments
def to_iso(dt):
    """ISO format the device accepts, e.g. "2025-09-06T07:00:00" """
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

# REMOVED: repush_qr_to_all_terminals - Not needed for Remote-Only Mode

# QR validation and door control for terminals
@csrf_exempt
@require_POST
def validate_qr_and_open_door(request, terminal_id: int):
    """Validate QR code and open door if valid appointment"""
    terminal = get_object_or_404(Terminal, pk=terminal_id)
    data = json.loads(request.body)
    qr_code = data.get('qr_code') or data.get('qr_payload')  # Support both field names for backward compatibility
    
    if not qr_code:
        return JsonResponse({"ok": False, "error": "QR code required"}, status=400)
    
    try:
        # Find appointment with this QR code (active, enter, or leave status)
        now = timezone.now()
        appointment = Appointment.objects.filter(
            qr_code=qr_code,
            status__in=['active', 'enter', 'leave'],
            valid_from__lte=now,
            valid_till__gte=now
        ).first()
        
        if not appointment:
            return JsonResponse({
                "ok": False, 
                "error": "Invalid or expired QR code",
                "appointment": None
            })
        
        # Determine if this is entry or exit based on terminal mode and appointment status
        terminal_mode = terminal.mode.lower()
        can_proceed = False
        new_status = appointment.status
        
        if terminal_mode == "entry":
            if appointment.status == 'active':
                can_proceed = True
                new_status = 'enter'
        elif terminal_mode == "exit":
            if appointment.status == 'enter':
                can_proceed = True
                new_status = 'leave'
        else:  # 'both' mode
            if appointment.status == 'active':
                can_proceed = True
                new_status = 'enter'
            elif appointment.status == 'enter':
                can_proceed = True
                new_status = 'leave'
        
        if not can_proceed:
            return JsonResponse({
                "ok": False, 
                "error": f"Access denied: Invalid status transition from {appointment.status} for {terminal_mode} mode",
                "appointment": {
                    "id": appointment.id,
                    "patient": appointment.patient.full_name,
                    "doctor": appointment.doctor.full_name,
                    "status": appointment.status
                }
            })
        
        # Update appointment status (terminal opens door itself)
        appointment.status = new_status
        if new_status == 'enter':
            appointment.used_at = now
        appointment.save()
        
        # Open door
        result = open_door(terminal, door_no=1)
        if result.get('ok'):
            # Update appointment status
            appointment.status = new_status
            if new_status == 'enter':
                appointment.used_at = now
            appointment.save()
            
            return JsonResponse({
                "ok": True,
                "message": "Door opened successfully",
                "appointment": {
                    "id": appointment.id,
                    "patient": appointment.patient.full_name,
                    "doctor": appointment.doctor.full_name,
                    "status": appointment.status
                }
            })
        else:
            return JsonResponse({
                "ok": False,
                "error": f"Failed to open door: {result.get('error')}",
                "appointment": {
                    "id": appointment.id,
                    "patient": appointment.patient.full_name,
                    "doctor": appointment.doctor.full_name,
                    "status": appointment.status
                }
            })
            
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

# Simple scan event logging API
@csrf_exempt
@require_POST
def log_scan_event(request):
    """
    Simple API endpoint to receive QR/card scan events from terminals.
    Just logs to console and returns terminal mode.
    Expected JSON payload:
    {
        "terminal_ip": "192.168.100.60",
        "qr_code": "99536641",
        "scan_type": "qr"  // optional: "qr", "card", or "unknown"
    }
    """
    try:
        data = json.loads(request.body)
        terminal_ip = data.get('terminal_ip')
        qr_code = data.get('qr_code') or data.get('qr_payload')  # Support both field names
        scan_type = data.get('scan_type', 'unknown')
        
        if not terminal_ip or not qr_code:
            return JsonResponse({
                "ok": False, 
                "error": "Missing required fields: terminal_ip, qr_code"
            }, status=400)
        
        # Get terminal mode
        terminal = Terminal.objects.filter(terminal_ip=terminal_ip, active=True).first()
        terminal_mode = terminal.mode if terminal else "unknown"
        
        # Determine scan type if not provided
        if scan_type == 'unknown':
            if qr_code.isdigit():
                scan_type = 'card'
            else:
                scan_type = 'qr'
        
        # Log scan event
        import logging
        logger = logging.getLogger(__name__)
        
        # Check if it's a valid appointment (optional validation)
        is_valid = False
        if scan_type in ['qr', 'card']:
            active_appointment = Appointment.objects.filter(
                qr_code=qr_code,
                status__in=['active', 'enter', 'leave'],
                valid_from__lte=timezone.now(),
                valid_till__gte=timezone.now()
            ).first()
            
            if active_appointment:
                is_valid = True
        
        return JsonResponse({
            "ok": True,
            "terminal_ip": terminal_ip,
            "terminal_mode": terminal_mode,
            "qr_code": qr_code,
            "scan_type": scan_type,
            "is_valid": is_valid,
            "timestamp": timezone.now().isoformat()
        })
            
    except json.JSONDecodeError:
        return JsonResponse({
            "ok": False, 
            "error": "Invalid JSON payload"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "ok": False, 
            "error": str(e)
        }, status=500)

# Get terminal mode API
@require_GET
def get_terminal_mode_api(request, terminal_ip: str):
    """Get the current mode of a terminal"""
    terminal = Terminal.objects.filter(terminal_ip=terminal_ip, active=True).first()
    mode = terminal.mode if terminal else "unknown"
    
    return JsonResponse({
        "ok": True,
        "terminal_ip": terminal_ip,
        "mode": mode
    })

# Terminal door control API
@require_POST
@login_required
def terminal_open_door_api(request, terminal_id):
    """Open door on a specific terminal"""
    # Check user permissions
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return JsonResponse({
            'success': False,
            'message': 'Permission denied'
        }, status=403)
    
    try:
        terminal = get_object_or_404(Terminal, id=terminal_id)
        
        # Use the open_door service function
        result = open_door(terminal, door_no=1)
        
        if result.get('ok'):
            return JsonResponse({
                'success': True,
                'message': f'Door opened successfully on {terminal.terminal_name}'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'Failed to open door on {terminal.terminal_name}: {result.get("error", "Unknown error")}'
            }, status=500)
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        }, status=500)

# Get recent scans from terminal
@require_GET
def last_scans(request, pk: int):
    """Get recent access events from a terminal"""
    term = get_object_or_404(Terminal, pk=pk)
    secs = int(request.GET.get("seconds", "120"))
    res = fetch_recent_scans(term, secs)
    
    # Add terminal metadata to response
    res["terminal"] = {
        "id": term.id,
        "name": term.terminal_name,
        "ip": term.terminal_ip,
        "mode": term.mode,
    }
    
    status = 200 if res.get("ok") else 502
    return JsonResponse(res, status=status, json_dumps_params={"ensure_ascii": False})
