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
from django.core.paginator import Paginator
from django.contrib import messages
from datetime import timedelta
from .models import User, Patient, Appointment, Terminal, QRCode
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


@csrf_exempt
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
    period_receipts = Appointment.objects.filter(
        created_at__date__range=[start_date, end_date]
    ).count()
    
    active_appointments = Appointment.objects.filter(
        qr_code__status="active", qr_code__expires_at__gt=timezone.now()
    ).count()
    
    total_patients = Patient.objects.count()
    
    # Get latest appointments for the selected period
    latest_appointments = (
        Appointment.objects.select_related("patient")
        .filter(created_at__date__range=[start_date, end_date])
        .order_by("-created_at")[:12]
    )
    
    context = {
        "user": request.user,
        "period": period,
        "period_label": period_label,
        "statistics": {
            "period_receipts": period_receipts,
            "active_appointments": active_appointments,
            "total_patients": total_patients,
        },
        "latest_appointments": latest_appointments,
    }
    return render(request, "medical_access/dashboard.html", context)


# =============================================================================
# PATIENT MODEL - CRUD OPERATIONS
# =============================================================================




@login_required
def patient_registration_view(request):
    today = timezone.now().date()

    # Calculate statistics
    today_receipts = Appointment.objects.filter(created_at__date=today).count()

    active_qr_codes = Appointment.objects.filter(
        qr_code__status="active", qr_code__expires_at__gt=timezone.now()
    ).count()

    # Get latest appointments
    latest_appointments = Appointment.objects.select_related(
        "patient"
    ).order_by("-created_at")[:10]

    context = {
        "user": request.user,
        "statistics": {
            "today_receipts": today_receipts,
            "active_qr_codes": active_qr_codes,
        },
        "latest_appointments": latest_appointments,
    }
    return render(request, "medical_access/patient_registration.html", context)


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
    appointments = Appointment.objects.select_related("patient", "qr_code").order_by(
        "-created_at"
    )

    # Pagination
    paginator = Paginator(appointments, 12)  # Show 12 appointments per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "appointments": page_obj,
        "page_obj": page_obj,
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
        medical_card_number = data.get("medical_card_number", "")

        # Validate required fields
        if not first_name or not last_name or not medical_card_number:
            return JsonResponse(
                {
                    "success": False,
                    "message": "First name, last name, and medical card number are required",
                },
                status=400,
            )

        with transaction.atomic():
            # Upsert Patient
            try:
                patient = Patient.objects.get(medical_card_number=medical_card_number)
                # Update patient info if name changed
                if (patient.first_name != first_name or 
                    patient.last_name != last_name):
                    patient.first_name = first_name
                    patient.last_name = last_name
                    patient.save()
            except Patient.DoesNotExist:
                # Create new patient
                patient = Patient.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    medical_card_number=medical_card_number,
                )

            # Create Appointment
            appointment = Appointment.objects.create(patient=patient)

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
        Appointment.objects.select_related("patient", "qr_code"), id=appointment_id
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
        if not data.get("first_name") or not data.get("last_name") or not data.get("medical_card_number"):
            return JsonResponse(
                {"success": False, "message": "First name, last name, and medical card number are required"}, status=400
            )

        # Update or create patient
        first_name = data.get("first_name").strip()
        last_name = data.get("last_name").strip()
        medical_card_number = data.get("medical_card_number").strip()
        
        # Try to find existing patient by medical card number
        try:
            patient = Patient.objects.get(medical_card_number=medical_card_number)
            # Update existing patient
            patient.first_name = first_name
            patient.last_name = last_name
            patient.save()
        except Patient.DoesNotExist:
            # Create new patient
            patient = Patient.objects.create(
                first_name=first_name,
                last_name=last_name,
                medical_card_number=medical_card_number
            )

        # Update appointment fields
        appointment.patient = patient

        # Update QR (if present)
        try:
            qr = appointment.qr_code
        except QRCode.DoesNotExist:
            qr = None

        if qr:
            # Handle QR code status updates
            if data.get("qr_status"):
                new_status = data.get("qr_status")
                current_status = qr.status
                
                # Map frontend status values to QR code status values
                status_mapping = {
                    'active': QRCode.Status.ACTIVE,
                    'entered': QRCode.Status.ENTERED,
                    'left': QRCode.Status.LEFT,
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

            # QR code is auto-generated, no manual editing

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
                    "patient_medical_card": appointment.patient.medical_card_number,
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
        
        # Get the patient before deleting the appointment
        patient = appointment.patient

        # Delete the appointment (QRCode is auto-deleted via OneToOne CASCADE)
        appointment.delete()
        
        # Delete the patient as well
        patient.delete()

        return JsonResponse(
            {
                "success": True,
                "message": "Appointment and patient deleted successfully.",
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
            Appointment.objects.select_related("patient", "qr_code"),
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


def health_check(request):
    """Simple health check endpoint for terminal testing"""
    return JsonResponse({
        "status": "ok",
        "timestamp": timezone.now().isoformat(),
        "server": "payverify_django"
    })