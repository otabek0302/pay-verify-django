import io
import json
import base64
import qrcode
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import timezone as dt_timezone
from django.db.models import Sum
from django.core.paginator import Paginator
from django.contrib import messages
from datetime import timedelta
from .models import User, Doctor, Patient, Appointment, Terminal, QRCode
from .services import probe_terminal, open_door

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def _qr_png(payload: str) -> bytes:
    """Generate QR code PNG image from payload"""
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# =============================================================================
# AUTHENTICATION & GENERAL VIEWS
# =============================================================================


def home_view(request):
    """Home page - redirect to login if not authenticated, otherwise to dashboard"""
    if request.user.is_authenticated:
        return redirect("medical_access:dashboard")
    return redirect("medical_access:login")


def login_view(request):
    """Login view"""
    if request.user.is_authenticated:
        return redirect("medical_access:dashboard")
    
    if request.method == "POST":
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse(
                {
                    "success": True,
                    "message": "Login successful! Redirecting...",
                    "redirect": "medical_access:dashboard",
                }
            )
        else:
            return JsonResponse(
                {"success": False, "message": "Invalid username or password"},
                status=400,
            )
    
    return render(request, "medical_access/login.html")


def logout_view(request):
    """Logout view"""
    logout(request)
    return redirect("medical_access:login")


@login_required
def dashboard_view(request):
    """Main dashboard view with statistics"""
    # Get period from request (default to 'today')
    period = request.GET.get("period", "today")
    now = timezone.now()
    
    # Calculate date range based on period
    if period == "today":
        start_date = now.date()
        end_date = now.date()
        period_label = "Today"
    elif period == "week":
        start_date = now.date() - timedelta(days=now.weekday())
        end_date = start_date + timedelta(days=6)
        period_label = "This Week"
    elif period == "month":
        start_date = now.date().replace(day=1)
        if now.month == 12:
            end_date = now.date().replace(
                year=now.year + 1, month=1, day=1
            ) - timedelta(days=1)
        else:
            end_date = now.date().replace(month=now.month + 1, day=1) - timedelta(
                days=1
            )
        period_label = "This Month"
    else:
        start_date = now.date()
        end_date = now.date()
        period_label = "Today"
    
    # Calculate comprehensive statistics for the selected period
    period_revenue = (
        Appointment.objects.filter(
            created_at__date__range=[start_date, end_date], qr_code__status="active"
        ).aggregate(total=Sum("doctor__price"))["total"]
        or 0
    )
    
    period_receipts = Appointment.objects.filter(
        created_at__date__range=[start_date, end_date]
    ).count()
    
    active_appointments = Appointment.objects.filter(
        qr_code__status="active", qr_code__expires_at__gt=timezone.now()
    ).count()
    
    active_doctors = Doctor.objects.count()
    total_patients = Patient.objects.count()
    
    # Get latest appointments for the selected period
    latest_appointments = (
        Appointment.objects.select_related("patient", "doctor")
        .filter(created_at__date__range=[start_date, end_date])
        .order_by("-created_at")[:12]
    )
    
    context = {
        "user": request.user,
        "period": period,
        "period_label": period_label,
        "statistics": {
            "period_revenue": period_revenue,
            "period_receipts": period_receipts,
            "active_appointments": active_appointments,
            "active_doctors": active_doctors,
            "total_patients": total_patients,
        },
        "latest_appointments": latest_appointments,
    }
    return render(request, "medical_access/dashboard.html", context)


# =============================================================================
# DOCTOR MODEL - CRUD OPERATIONS
# =============================================================================


@login_required
def doctors_view(request):
    doctors = Doctor.objects.all().order_by("last_name", "first_name")
    
    # Pagination
    paginator = Paginator(doctors, 12)  # Show 12 doctors per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    context = {
        "user": request.user,
        "doctors": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "medical_access/doctors.html", context)


@require_POST
@login_required
def create_doctor(request):
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return JsonResponse(
            {"success": False, "message": "Permission denied"}, status=403
        )
    
    try:
        data = json.loads(request.body)
        
        # Handle both full_name and separate first_name/last_name
        if "full_name" in data:
            full_name = data.get("full_name")
            if not full_name:
                return JsonResponse(
                    {"success": False, "message": "Full name is required"}, status=400
                )
            # Split full name into first and last name
            name_parts = full_name.split()
            first_name = name_parts[0] if name_parts else ""
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        else:
            first_name = data.get("first_name", "").strip()
            last_name = data.get("last_name", "").strip()
            if not first_name and not last_name:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "First name or last name is required",
                    },
                    status=400,
                )

        procedure = data.get("procedure", "General Consultation").strip()
        price = data.get("price", 0.00)
        
        # Create doctor with procedure and price
        doctor = Doctor.objects.create(
            first_name=first_name, last_name=last_name, procedure=procedure, price=price
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Doctor created successfully",
                "doctor": {
                    "id": doctor.id,
                    "first_name": doctor.first_name,
                    "last_name": doctor.last_name,
                    "procedure": doctor.procedure,
                    "price": str(doctor.price),
                },
            }
        )
        
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_GET
@login_required
def get_doctor(request, doctor_id):
    try:
        doctor = get_object_or_404(Doctor, id=doctor_id)
        
        return JsonResponse(
            {
                "success": True,
                "doctor": {
                    "id": doctor.id,
                    "first_name": doctor.first_name,
                    "last_name": doctor.last_name,
                    "procedure": doctor.procedure,
                    "price": str(doctor.price),
                    "full_name": doctor.full_name,
                },
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_POST
@login_required
def update_doctor(request, doctor_id):
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return JsonResponse(
            {"success": False, "message": "Permission denied"}, status=403
        )
    
    try:
        doctor = get_object_or_404(Doctor, id=doctor_id)
        data = json.loads(request.body)
        
        # Update doctor fields
        if data.get("full_name"):
            name_parts = data["full_name"].split()
            doctor.first_name = name_parts[0] if name_parts else ""
            doctor.last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        elif data.get("first_name") or data.get("last_name"):
            # Handle separate first_name and last_name fields
            if data.get("first_name"):
                doctor.first_name = data.get("first_name").strip()
            if data.get("last_name"):
                doctor.last_name = data.get("last_name").strip()
        
        # Update procedure and price
        if data.get("procedure"):
            doctor.procedure = data.get("procedure").strip()
        if data.get("price"):
            doctor.price = data.get("price")
        
        doctor.save()
        
        return JsonResponse(
            {
                "success": True,
                "message": "Doctor updated successfully",
                "doctor": {
                    "id": doctor.id,
                    "first_name": doctor.first_name,
                    "last_name": doctor.last_name,
                    "procedure": doctor.procedure,
                    "price": str(doctor.price),
                },
            }
        )
        
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_POST
@login_required
def delete_doctor(request, doctor_id):
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return JsonResponse(
            {"success": False, "message": "Permission denied"}, status=403
        )
    
    try:
        doctor = get_object_or_404(Doctor, id=doctor_id)
        doctor_name = doctor.full_name
        
        # Check if doctor has appointments
        if doctor.appointments.exists():
            return JsonResponse(
                {
                    "success": False,
                    "message": "Cannot delete doctor with existing appointments. Please delete appointments first.",
                },
                status=400,
            )
        
        # Delete the doctor
        doctor.delete()
        
        return JsonResponse(
            {"success": True, "message": f'Doctor "{doctor_name}" deleted successfully'}
        )
        
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


# =============================================================================
# PATIENT MODEL - CRUD OPERATIONS
# =============================================================================


@login_required
def patients_view(request):
    patients = Patient.objects.all().order_by("last_name", "first_name")

    # Pagination
    paginator = Paginator(patients, 12)  # Show 12 patients per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "user": request.user,
        "patients": page_obj,
        "page_obj": page_obj,
    }
    return render(request, "medical_access/patients.html", context)


@login_required
def patient_registration_view(request):
    today = timezone.now().date()

    # Calculate statistics
    today_revenue = (
        Appointment.objects.filter(
            created_at__date=today, qr_code__status="active"
        ).aggregate(total=Sum("doctor__price"))["total"]
        or 0
    )

    today_receipts = Appointment.objects.filter(created_at__date=today).count()

    active_qr_codes = Appointment.objects.filter(
        qr_code__status="active", qr_code__expires_at__gt=timezone.now()
    ).count()

    # Get latest appointments
    latest_appointments = Appointment.objects.select_related(
        "patient", "doctor"
    ).order_by("-created_at")[:10]

    # Get doctors for form
    doctors = Doctor.objects.all()

    context = {
        "user": request.user,
        "statistics": {
            "today_revenue": today_revenue,
            "today_receipts": today_receipts,
            "active_qr_codes": active_qr_codes,
        },
        "latest_appointments": latest_appointments,
        "doctors": doctors,
    }
    return render(request, "medical_access/patient_registration.html", context)


@login_required
def get_patient(request, patient_id):
    try:
        patient = get_object_or_404(Patient, id=patient_id)
        return JsonResponse(
            {
                "success": True,
                "patient": {
                    "id": patient.id,
                    "first_name": patient.first_name,
                    "last_name": patient.last_name,
                    "phone": patient.phone,
                    "passport_series": patient.passport_series,
                    "passport_number": patient.passport_number,
                    "full_name": patient.full_name,
                    "created_at": patient.created_at.isoformat(),
                    "updated_at": patient.updated_at.isoformat(),
                },
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_POST
@login_required
def create_patient(request):
        try:
            data = request.POST
            patient = Patient.objects.create(
                first_name=data.get("first_name", "").strip(),
                last_name=data.get("last_name", "").strip(),
                phone=data.get("phone", "").strip() or None,
                passport_series=data.get("passport_series", "").strip() or None,
                passport_number=data.get("passport_number", "").strip() or None,
            )
            return JsonResponse(
                {
                    "success": True,
                    "message": "Patient created successfully",
                    "patient": {
                        "id": patient.id,
                        "first_name": patient.first_name,
                        "last_name": patient.last_name,
                        "phone": patient.phone,
                        "passport_series": patient.passport_series,
                        "passport_number": patient.passport_number,
                        "full_name": patient.full_name,
                        "created_at": patient.created_at.strftime("%d/%m/%Y %H:%M"),
                    },
                }
            )
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)
    
@require_POST
@login_required
def update_patient(request, patient_id):
    """Update an existing patient"""
    try:
        patient = get_object_or_404(Patient, id=patient_id)
        data = request.POST

        patient.first_name = data.get("first_name", "").strip()
        patient.last_name = data.get("last_name", "").strip()
        patient.phone = data.get("phone", "").strip() or None
        patient.passport_series = data.get("passport_series", "").strip() or None
        patient.passport_number = data.get("passport_number", "").strip() or None

        patient.save()

        return JsonResponse(
            {
                "success": True,
                "message": "Patient updated successfully",
                "patient": {
                    "id": patient.id,
                    "first_name": patient.first_name,
                    "last_name": patient.last_name,
                    "phone": patient.phone,
                    "passport_series": patient.passport_series,
                    "passport_number": patient.passport_number,
                    "full_name": patient.full_name,
                },
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=400)
    

@require_POST
@login_required
def delete_patient(request, patient_id):
    """Delete a patient"""
    try:
        patient = get_object_or_404(Patient, id=patient_id)
        # Check if patient has appointments
        if patient.appointments.exists():
            return JsonResponse(
                {
                    "success": False,
                    "message": "Cannot delete patient with existing appointments. Please delete appointments first.",
                },
                status=400,
            )
        patient.delete()
        return JsonResponse({"success": True, "message": "Patient deleted successfully"})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=400)


# =============================================================================
# TERMINAL MODEL - OPERATIONS
# =============================================================================


@login_required
def terminals_view(request):
    # Check user role and redirect accordingly
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return redirect("medical_access:dashboard")

    # Get all terminals
    terminals = Terminal.objects.all().order_by("terminal_name")

    # Pagination
    paginator = Paginator(terminals, 12)  # Show 12 terminals per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "terminals": page_obj,
        "page_obj": page_obj,
        "user": request.user,
    }

    return render(request, "medical_access/terminals.html", context)


@login_required
def admin_terminal_health(request, pk: int):
    """Admin view for terminal health check"""
    t = get_object_or_404(Terminal, pk=pk)
    res = probe_terminal(t)

    if res.get("ok"):
        messages.success(request, f'Terminal "{t.terminal_name}" is reachable!')
    else:
        messages.error(
            request,
            f'Terminal "{t.terminal_name}" is not reachable: {res.get("error", "Unknown error")}',
        )

    return redirect("admin:medical_access_terminal_changelist")


@login_required
def admin_terminal_open(request, pk: int):
    """Admin view for opening terminal door"""
    t = get_object_or_404(Terminal, pk=pk)

    res = open_door(t, door_no=1)

    if res.get("ok"):
        messages.success(request, f'Door open command sent to "{t.terminal_name}"!')
    else:
        messages.error(
            request,
            f'Failed to open door on "{t.terminal_name}": {res.get("error", "Unknown error")}',
        )

    return redirect("admin:medical_access_terminal_changelist")


@require_POST
@login_required
def terminal_open_door_api(request, terminal_id):
    """Open door on a specific terminal"""
    # Check user permissions
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return JsonResponse(
            {"success": False, "message": "Permission denied"}, status=403
        )

    try:
        terminal = get_object_or_404(Terminal, id=terminal_id)

        # Use the open_door service function
        result = open_door(terminal, door_no=1)

        if result.get("ok"):
            return JsonResponse(
                {
                    "success": True,
                    "message": f"Door opened successfully on {terminal.terminal_name}",
                }
            )
        else:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Failed to open door on {terminal.terminal_name}: {result.get('error', 'Unknown error')}",
                },
                status=500,
            )

    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Error: {str(e)}"}, status=500
        )


# =============================================================================
# APPOINTMENT MODEL - CRUD OPERATIONS
# =============================================================================


@require_GET
@login_required
def appointments_view(request):
    """View for managing appointments (admin and super admin only)"""
    # Check user role and redirect accordingly
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return redirect("medical_access:dashboard")

    # User is admin, proceeding to appointments view
    appointments = Appointment.objects.select_related("patient", "doctor", "qr_code").order_by(
        "-created_at"
    )

    # Pagination
    paginator = Paginator(appointments, 12)  # Show 12 appointments per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "appointments": page_obj,
        "page_obj": page_obj,
        "doctors": Doctor.objects.all(),
        "patients": Patient.objects.all(),
    }

    return render(request, "medical_access/appointments.html", context)


@require_POST
@login_required
def create_appointment(request):
    """Create new appointment/receipt"""
    from django.db import transaction
    
    try:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "message": "Invalid JSON format"}, status=400
            )
        
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        phone = data.get("phone", "")
        passport_series = data.get("passport_series", "")
        passport_number = data.get("passport_number", "")
        doctor_id = data.get("doctor_id")

        # Validate required fields
        if not first_name or not last_name or not doctor_id:
            return JsonResponse(
                {
                    "success": False,
                    "message": "First name, last name, and doctor are required",
                },
                status=400,
            )

        # Fetch Doctor
        doctor = get_object_or_404(Doctor, id=doctor_id)

        with transaction.atomic():
            # Upsert Patient
            if passport_series and passport_number:
                try:
                    patient = Patient.objects.get(passport_series=passport_series, passport_number=passport_number)
                    # Update patient info if name/phone changed
                    if (patient.first_name != first_name or 
                        patient.last_name != last_name or 
                        patient.phone != phone):
                        patient.first_name = first_name
                        patient.last_name = last_name
                        patient.phone = phone
                        patient.save()
                except Patient.DoesNotExist:
                    # Create new patient
                    patient = Patient.objects.create(
                        first_name=first_name,
                        last_name=last_name,
                        phone=phone,
                        passport_series=passport_series,
                        passport_number=passport_number,
                    )
            else:
                # Create new patient with just name
                patient = Patient.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    passport_series=passport_series,
                    passport_number=passport_number,
                )

            # Create Appointment
            appointment = Appointment.objects.create(patient=patient, doctor=doctor)

            # Create QRCode
            now = timezone.now()
            expires_at = now + timedelta(hours=24)  # 24 hours validity
            
            qr_code_obj = QRCode.objects.create(
                appointment=appointment,
                expires_at=expires_at,
                status=QRCode.Status.ACTIVE,
            )

        return JsonResponse(
            {
                "success": True,
                "appointment_id": appointment.id,
                "qr": {
                    "code": qr_code_obj.code,
                    "status": qr_code_obj.status,
                    "expires_at": qr_code_obj.expires_at.isoformat(),
                    "expires_at_utc": qr_code_obj.expires_at.astimezone(dt_timezone.utc).replace(tzinfo=None).isoformat() + "Z"
                }
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)

@require_GET
@login_required
def appointment_detail(request, appointment_id):
    """View appointment details and generate QR if needed"""
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor", "qr_code"), id=appointment_id
    )

    context = {
        "appointment": appointment,
        "user": request.user,
    }
    return render(request, "medical_access/appointment_detail.html", context)


@require_POST
@login_required
def update_appointment(request, appointment_id):
    """Update an existing appointment"""
    try:
        appointment = get_object_or_404(Appointment, id=appointment_id)
        data = request.POST

        # Validate required fields
        if not data.get("patient_id"):
            return JsonResponse(
                {"success": False, "message": "Patient is required"}, status=400
            )
        if not data.get("doctor_id"):
            return JsonResponse(
                {"success": False, "message": "Doctor is required"}, status=400
            )

        # Validate foreign keys
        try:
            patient = Patient.objects.get(id=data.get("patient_id"))
        except Patient.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Patient not found"}, status=400
            )

        try:
            doctor = Doctor.objects.get(id=data.get("doctor_id"))
        except Doctor.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Doctor not found"}, status=400
            )

        # Update appointment fields
        appointment.patient = patient
        appointment.doctor = doctor

        # Update QR (if present)
        try:
            qr = appointment.qr_code
        except QRCode.DoesNotExist:
            qr = None

        if qr:
            # Handle QR code status updates
            if data.get("status"):
                new_status = data.get("status")
                current_status = qr.status
                
                # Map frontend status values to QR code status values
                status_mapping = {
                    'active': QRCode.Status.ACTIVE,
                    'enter': QRCode.Status.ENTERED,
                    'leave': QRCode.Status.LEFT,
                    'used': QRCode.Status.LEFT,  # Map 'used' to 'left'
                    'expired': QRCode.Status.EXPIRED
                }
                
                if new_status in status_mapping:
                    mapped_status = status_mapping[new_status]
                    
                    # Validate status transitions - allow more flexible transitions for admin updates
                    valid_transitions = {
                        QRCode.Status.ACTIVE: [QRCode.Status.ENTERED, QRCode.Status.LEFT, QRCode.Status.EXPIRED],
                        QRCode.Status.ENTERED: [QRCode.Status.ACTIVE, QRCode.Status.LEFT, QRCode.Status.EXPIRED],
                        QRCode.Status.LEFT: [QRCode.Status.ACTIVE, QRCode.Status.ENTERED, QRCode.Status.EXPIRED],  # Allow going back to active/entered
                        QRCode.Status.EXPIRED: [QRCode.Status.ACTIVE, QRCode.Status.ENTERED, QRCode.Status.LEFT]  # Allow reactivating expired codes
                    }

                    if mapped_status != current_status and mapped_status not in valid_transitions.get(current_status, []):
                        return JsonResponse(
                            {
                                "success": False,
                                "message": f"Invalid status transition from {current_status} to {mapped_status}"
                            },
                            status=400
                        )

                    qr.status = mapped_status
                    
                    # Update used_at timestamp logic
                    if mapped_status in [QRCode.Status.ENTERED, QRCode.Status.LEFT]:
                        if not qr.used_at:  # Set first time used
                            qr.used_at = timezone.now()
                    elif mapped_status == QRCode.Status.ACTIVE:
                        # If going back to active, clear the used_at timestamp
                        qr.used_at = None

            # Code: if provided and different → ensure uniqueness
            new_qr_code = data.get("qr_code", "").strip()
            if new_qr_code and new_qr_code != qr.code:
                if QRCode.objects.filter(code=new_qr_code).exclude(appointment=appointment).exists():
                    return JsonResponse(
                        {"success": False, "message": "QR code already exists"},
                        status=400,
                    )
                qr.code = new_qr_code

            # Dates
            if data.get("valid_from"):
                from django.utils.dateparse import parse_datetime
                valid_from = parse_datetime(data.get("valid_from"))
                if valid_from:
                    qr.created_at = valid_from

            if data.get("valid_till"):
                from django.utils.dateparse import parse_datetime
                valid_till = parse_datetime(data.get("valid_till"))
                if valid_till:
                    qr.expires_at = valid_till

            qr.save()

        # Save appointment changes
        appointment.save()

        return JsonResponse(
            {
                "success": True,
                "message": "Appointment updated successfully",
                "appointment": {
                    "id": appointment.id,
                    "patient_name": appointment.patient.full_name,
                    "doctor_name": appointment.doctor.full_name,
                    "doctor_procedure": appointment.doctor.procedure,
                    "doctor_price": float(appointment.doctor.price),
                    "status": qr.get_status_display() if qr else "No QR Code",
                    "qr_code": qr.code if qr else None,
                    "created_at": appointment.created_at.strftime("%Y-%m-%d %H:%M"),
                    "valid_from": qr.created_at.strftime("%Y-%m-%d %H:%M") if qr else None,
                    "valid_till": qr.expires_at.strftime("%Y-%m-%d %H:%M") if qr else None,
                },
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=400)
    
@require_POST
@login_required
def delete_appointment(request, appointment_id):
    """Delete an appointment - admin and super admin only"""
    if request.user.role not in [User.Role.ADMIN, User.Role.SUPER_ADMIN]:
        return JsonResponse(
            {"success": False, "message": "Permission denied"}, status=403
        )

    try:
        appointment = get_object_or_404(Appointment, id=appointment_id)

        # Delete the appointment (QRCode is auto-deleted via OneToOne CASCADE)
        appointment.delete()

        return JsonResponse(
            {
                "success": True,
                "message": "Appointment deleted successfully.",
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=400)
    

# =============================================================================
# QR CODE MODEL - OPERATIONS
# =============================================================================

@login_required
def create_qr_code(request, appointment_id):
    """Create QR code for appointment access with 24h validity"""
    try:
        appointment = get_object_or_404(
            Appointment.objects.select_related("patient", "qr_code"), id=appointment_id
        )

        # Check if QR code exists and is active
        try:
            qr = appointment.qr_code
        except QRCode.DoesNotExist:
            return JsonResponse({"error": "QR code not found"}, status=400)
            
        if qr.status != QRCode.Status.ACTIVE:
            return JsonResponse({"error": "QR code is not active"}, status=400)

        # Use existing QR code from appointment
        qr_code = qr.code

        # Return QR image
        response = HttpResponse(_qr_png(qr_code), content_type="image/png")
        response["Content-Disposition"] = (
            f'attachment; filename="qr_pass_{qr_code}.png"'
        )
        return response

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@login_required
def generate_qr_code_image(request, appointment_id):
    """Generate and display receipt with QR code"""
    try:
        appointment = get_object_or_404(
            Appointment.objects.select_related("patient", "doctor", "qr_code"),
            id=appointment_id,
        )

        # Generate QR code from appointment's QR code
        try:
            qr = appointment.qr_code
            qr_data = qr.code
        except QRCode.DoesNotExist:
            qr_data = str(appointment.id)
        img = qrcode.make(qr_data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        # Convert to base64 for embedding in HTML
        qr_code_base64 = base64.b64encode(buf.getvalue()).decode()

        context = {
            "appointment": appointment,
            "qr_code_base64": qr_code_base64,
            "user": request.user,
        }

        return render(request, "medical_access/receipt.html", context)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# =============================================================================
# KIOSK & QR SCANNING
# =============================================================================


@login_required
def kiosk_view(request):
    """QR Scanner/Kiosk view for scanning appointment QR codes"""
    context = {
        "user": request.user,
    }
    return render(request, "medical_access/kiosk.html", context)