from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib import messages
from django.db.models import Count, Q, Exists, OuterRef, Sum
from .models import User, Insurance, Role, Specialty, HospitalSettings, SpecialistConsultationFee, HospitalForm, FormCategory, Consumable, ConsumableCategory, VisitConsumable
from .decorators import admin_required, login_required_custom, role_required
from patients.models import Patient, Visit, VisitStatus
from billing.models import Payment, PaymentStatus, PaymentType, PaymentMethod
from audit.models import ChangeRequest, ChangeRequestStatus, AuditLog
import json
import random
import datetime
from django.utils import timezone


def custom_404(request, exception=None):
    return render(request, '404.html', status=404)


def _gen_captcha(request):
    a = random.randint(1, 15)
    b = random.randint(1, 15)
    request.session['captcha_answer'] = a + b
    return f"{a} + {b} = ?"


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    try:
        hs = HospitalSettings.get()
    except Exception:
        hs = None

    if request.method == 'POST':
        # Validate math captcha first
        expected = request.session.get('captcha_answer')
        user_answer = request.POST.get('captcha', '').strip()
        captcha_ok = user_answer.isdigit() and int(user_answer) == expected
        if not captcha_ok:
            messages.error(request, "Incorrect security check answer. Please try again.")
            return render(request, 'core/login.html', {
                'hospital_settings': hs,
                'captcha_question': _gen_captcha(request),
            })

        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.is_deleted:
                messages.error(request, "Your account has been deactivated.")
                return render(request, 'core/login.html', {
                    'hospital_settings': hs,
                    'captcha_question': _gen_captcha(request),
                })
            login(request, user)
            AuditLog.objects.create(
                user=user, action='LOGIN', model_name='User',
                object_id=str(user.id), description=f"User {user.username} logged in",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return redirect('dashboard')
        messages.error(request, "Invalid username or password.")

    return render(request, 'core/login.html', {
        'hospital_settings': hs,
        'captcha_question': _gen_captcha(request),
    })


def logout_view(request):
    if request.user.is_authenticated:
        AuditLog.objects.create(
            user=request.user, action='LOGOUT', model_name='User',
            object_id=str(request.user.id), description=f"User {request.user.username} logged out",
            ip_address=request.META.get('REMOTE_ADDR')
        )
    logout(request)
    return redirect('login')


def set_my_language(request):
    """Let any logged-in user pick their own display language, independent of the system default."""
    if request.method == 'POST' and request.user.is_authenticated:
        lang = request.POST.get('language', '')
        if lang in ('en', 'fr'):
            request.user.preferred_language = lang
            request.user.save(update_fields=['preferred_language'])
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'dashboard'
    return redirect(next_url)


@login_required_custom
def dashboard(request):
    user = request.user
    ctx = {'user': user}

    if user.role == Role.ADMIN:
        ctx['total_patients'] = Patient.objects.filter(is_deleted=False).count()
        ctx['total_visits'] = Visit.objects.filter(is_deleted=False).count()
        ctx['active_users'] = User.objects.filter(is_active=True, is_deleted=False).count()
        ctx['pending_requests'] = ChangeRequest.objects.filter(status=ChangeRequestStatus.PENDING).count()
        ctx['recent_patients'] = Patient.objects.filter(is_deleted=False).order_by('-created_at')[:5]
        ctx['pending_changes'] = ChangeRequest.objects.filter(status=ChangeRequestStatus.PENDING)[:5]

    elif user.role == Role.RECEPTIONIST:
        ctx['total_patients'] = Patient.objects.filter(is_deleted=False, registered_by=user).count()
        ctx['today_registrations'] = Patient.objects.filter(
            is_deleted=False, created_at__date=timezone.now().date()).count()
        ctx['pending_visits'] = Visit.objects.filter(is_deleted=False, status=VisitStatus.PENDING).count()
        ctx['recent_patients'] = Patient.objects.filter(is_deleted=False).order_by('-created_at')[:10]

    elif user.role == Role.DOCTOR:
        paid_consult = Payment.objects.filter(
            visit=OuterRef('pk'), payment_type=PaymentType.CONSULTATION,
            status=PaymentStatus.PAID, is_deleted=False
        )
        ctx['my_patients'] = Visit.objects.filter(
            doctor=user, is_deleted=False, status__in=[VisitStatus.PENDING, VisitStatus.IN_PROGRESS]
        ).annotate(has_paid=Exists(paid_consult)).select_related('patient').order_by('-has_paid', '-created_at')
        ctx['total_assigned'] = Visit.objects.filter(doctor=user, is_deleted=False).count()
        ctx['pending'] = Visit.objects.filter(doctor=user, is_deleted=False, status=VisitStatus.PENDING).count()
        ctx['in_progress'] = Visit.objects.filter(doctor=user, is_deleted=False, status=VisitStatus.IN_PROGRESS).count()

    elif user.role == Role.NURSE:
        ctx['pending_triage'] = Visit.objects.filter(
            is_deleted=False, status=VisitStatus.PENDING, triage__isnull=True
        ).select_related('patient', 'doctor')[:10]
        ctx['total_triaged_today'] = Visit.objects.filter(
            is_deleted=False, triage__created_at__date=timezone.now().date()
        ).count()
        ctx['triaged_today'] = Visit.objects.filter(
            is_deleted=False, triage__created_at__date=timezone.now().date()
        ).select_related('patient', 'doctor', 'triage').order_by('-triage__created_at')[:15]

    elif user.role == Role.ACCOUNTANT:
        from laboratory.models import LabRequest, LabRequestStatus

        ctx['pending_payments'] = Payment.objects.filter(is_deleted=False, status=PaymentStatus.PENDING).count()
        ctx['recent_payments'] = Payment.objects.filter(is_deleted=False).order_by('-created_at')[:10]

        paid_consult_sq = Payment.objects.filter(
            visit=OuterRef('pk'), payment_type__in=[PaymentType.CONSULTATION, PaymentType.COMBINED],
            status=PaymentStatus.PAID, is_deleted=False
        )
        unpaid_labs_sq = LabRequest.objects.filter(
            visit=OuterRef('pk'), is_deleted=False, status=LabRequestStatus.REQUESTED
        )
        unbilled_sq = VisitConsumable.objects.filter(
            visit=OuterRef('pk'), is_billed=False
        )
        from patients.models import VisitStatus as VS
        ctx['pending_visits'] = Visit.objects.filter(
            is_deleted=False, status__in=[VS.PENDING, VS.IN_PROGRESS]
        ).filter(
            ~Exists(paid_consult_sq) | Exists(unpaid_labs_sq) | Exists(unbilled_sq)
        ).annotate(
            has_paid_consult=Exists(paid_consult_sq),
            has_unpaid_labs=Exists(unpaid_labs_sq),
            has_unbilled_supplies=Exists(unbilled_sq),
        ).select_related('patient', 'doctor').order_by('-created_at')[:10]

    elif user.role == Role.LAB_TECHNICIAN:
        from laboratory.models import LabRequest, LabRequestStatus
        ctx['pending_labs_count'] = LabRequest.objects.filter(
            is_deleted=False, status__in=[LabRequestStatus.PAID, LabRequestStatus.REQUESTED, LabRequestStatus.IN_PROGRESS]
        ).count()
        ctx['recent_labs'] = LabRequest.objects.filter(
            is_deleted=False
        ).select_related('visit__patient', 'requested_by').order_by('-created_at')[:10]
        ctx['completed_today'] = LabRequest.objects.filter(
            is_deleted=False, status=LabRequestStatus.COMPLETED,
            updated_at__date=timezone.now().date()
        ).count()

    return render(request, 'core/dashboard.html', ctx)


# ─── USER MANAGEMENT (Admin only) ───────────────────────────────────────────

@admin_required
def user_list(request):
    from django.core.paginator import Paginator
    PER_PAGE_OPTS = [5, 25, 50, 100]
    q = request.GET.get('q', '').strip()
    per_page = int(request.GET.get('per_page', 25))
    if per_page not in PER_PAGE_OPTS:
        per_page = 25
    tab = request.GET.get('tab', 'active')
    if tab not in ('active', 'deactivated'):
        tab = 'active'

    if tab == 'active':
        users = User.objects.filter(is_deleted=False, is_active=True).exclude(id=request.user.id).order_by('role', 'last_name')
    else:
        users = User.objects.filter(is_deleted=False, is_active=False).order_by('role', 'last_name')

    if q:
        users = users.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(username__icontains=q) |
            Q(role__icontains=q)
        )

    deactivated_count = User.objects.filter(is_deleted=False, is_active=False).count()

    paginator = Paginator(users, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'core/user_list.html', {
        'page_obj': page_obj,
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
        'tab': tab,
        'deactivated_count': deactivated_count,
    })


@admin_required
def user_create(request):
    if request.method == 'POST':
        data = request.POST
        try:
            user = User.objects.create_user(
                username=data['username'],
                password=data['password'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                email=data.get('email', ''),
                role=data['role'],
                specialty=data.get('specialty', '') if data.get('role') == 'doctor' else '',
                phone=data.get('phone', ''),
                created_by=request.user,
                must_change_password=True,
            )
            AuditLog.objects.create(
                user=request.user, action='CREATE_USER', model_name='User',
                object_id=str(user.id), description=f"Created user {user.username} with role {user.role}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"User {user.get_full_name()} created. They will be prompted to set their own password on first login.")
            return redirect('user_list')
        except Exception as e:
            from django.db import IntegrityError
            if isinstance(e, IntegrityError) and 'username' in str(e).lower():
                messages.error(request, f"The username \"{data.get('username')}\" is already taken. Please choose a different one.")
            else:
                messages.error(request, f"Error creating user: {e}")
    return render(request, 'core/user_form.html', {'roles': Role.choices, 'specialties': Specialty.choices, 'action': 'Create'})


@admin_required
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk, is_deleted=False)
    if request.method == 'POST':
        data = request.POST
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.email = data.get('email', user.email)
        user.role = data.get('role', user.role)
        user.specialty = data.get('specialty', '') if user.role == 'doctor' else ''
        user.phone = data.get('phone', user.phone)
        user.save()
        AuditLog.objects.create(
            user=request.user, action='EDIT_USER', model_name='User',
            object_id=str(user.id), description=f"Edited user {user.username}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, "User updated successfully.")
        return redirect('user_list')
    return render(request, 'core/user_form.html', {'obj': user, 'roles': Role.choices, 'specialties': Specialty.choices, 'action': 'Edit'})


@admin_required
def user_toggle(request, pk):
    if request.method != 'POST':
        return redirect('user_list')
    user = get_object_or_404(User, pk=pk, is_deleted=False)
    if user.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect('user_list')
    user.is_active = not user.is_active
    user.save()
    status = "activated" if user.is_active else "deactivated"
    AuditLog.objects.create(
        user=request.user, action='TOGGLE_USER', model_name='User',
        object_id=str(user.id), description=f"User {user.username} {status}",
        ip_address=request.META.get('REMOTE_ADDR')
    )
    messages.success(request, f"User {status} successfully.")
    tab = 'active' if user.is_active else 'deactivated'
    return redirect(f"{reverse('user_list')}?tab={tab}")


@admin_required
def user_delete(request, pk):
    if request.method != 'POST':
        return redirect('user_list')
    if pk == request.user.pk:
        messages.error(request, "You cannot delete your own account.")
        return redirect(f"{reverse('user_list')}?tab=deactivated")
    user = get_object_or_404(User, pk=pk, is_deleted=False, is_active=False)
    name = user.get_full_name() or user.username
    deleted_records = []
    if user.role == Role.DOCTOR:
        from clinical.models import Consultation
        from laboratory.models import LabRequest
        c_count = Consultation.objects.filter(doctor=user, is_deleted=False).update(is_deleted=True)
        l_count = LabRequest.objects.filter(requested_by=user, is_deleted=False).update(is_deleted=True)
        if c_count:
            deleted_records.append(f"{c_count} consultation note{'s' if c_count != 1 else ''}")
        if l_count:
            deleted_records.append(f"{l_count} lab request{'s' if l_count != 1 else ''}")
    user.is_deleted = True
    user.save()
    AuditLog.objects.create(
        user=request.user, action='DELETE_USER', model_name='User',
        object_id=str(user.id),
        description=f"Permanently deleted {'doctor' if user.role == Role.DOCTOR else 'user'} {user.username}"
                    + (f" along with {', '.join(deleted_records)}" if deleted_records else ""),
        ip_address=request.META.get('REMOTE_ADDR')
    )
    extra = f" Their {', '.join(deleted_records)} were also removed." if deleted_records else ""
    messages.success(request, f'User "{name}" permanently deleted.{extra}')
    return redirect(f"{reverse('user_list')}?tab=deactivated")


@admin_required
def user_reset_password(request, pk):
    user = get_object_or_404(User, pk=pk, is_deleted=False)
    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        if new_password and len(new_password) >= 8:
            user.set_password(new_password)
            user.must_change_password = True
            user.save()
            AuditLog.objects.create(
                user=request.user, action='RESET_PASSWORD', model_name='User',
                object_id=str(user.id), description=f"Password reset for {user.username} by admin",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Password reset for {user.get_full_name()}. They will be prompted to choose a new password on next login.")
            return redirect('user_list')
        messages.error(request, "Password must be at least 8 characters.")
    return render(request, 'core/reset_password.html', {'obj': user})


@login_required_custom
def change_password(request):
    """Self-service password change — forced on first login or after admin reset."""
    if request.method == 'POST':
        current = request.POST.get('current_password', '')
        new_pw = request.POST.get('new_password', '')
        confirm = request.POST.get('confirm_password', '')

        if not request.user.check_password(current):
            messages.error(request, "Current password is incorrect.")
        elif len(new_pw) < 8:
            messages.error(request, "New password must be at least 8 characters.")
        elif new_pw != confirm:
            messages.error(request, "Passwords do not match.")
        else:
            request.user.set_password(new_pw)
            request.user.must_change_password = False
            request.user.save()
            update_session_auth_hash(request, request.user)
            AuditLog.objects.create(
                user=request.user, action='CHANGE_PASSWORD', model_name='User',
                object_id=str(request.user.id),
                description=f"User {request.user.username} changed their own password",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, "Password changed successfully.")
            return redirect('dashboard')

    return render(request, 'core/change_password.html')


@login_required_custom
def my_profile(request):
    """Any logged-in user can update their username and password."""
    user = request.user
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'username':
            new_username = request.POST.get('username', '').strip()
            if not new_username:
                messages.error(request, "Username cannot be empty.")
            elif User.objects.filter(username=new_username).exclude(pk=user.pk).exists():
                messages.error(request, "That username is already taken.")
            else:
                old_username = user.username
                user.username = new_username
                user.save()
                AuditLog.objects.create(
                    user=user, action='UPDATE_PROFILE', model_name='User',
                    object_id=str(user.id),
                    description=f"Username changed from {old_username} to {new_username}",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                messages.success(request, "Username updated successfully.")
        elif form_type == 'password':
            current = request.POST.get('current_password', '')
            new_pw = request.POST.get('new_password', '')
            confirm = request.POST.get('confirm_password', '')
            if not user.check_password(current):
                messages.error(request, "Current password is incorrect.")
            elif len(new_pw) < 8:
                messages.error(request, "New password must be at least 8 characters.")
            elif new_pw != confirm:
                messages.error(request, "New passwords do not match.")
            else:
                user.set_password(new_pw)
                user.save()
                update_session_auth_hash(request, user)
                AuditLog.objects.create(
                    user=user, action='CHANGE_PASSWORD', model_name='User',
                    object_id=str(user.id),
                    description=f"User {user.username} changed their password from profile",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                messages.success(request, "Password changed successfully.")
        return redirect('my_profile')
    return render(request, 'core/my_profile.html')


@admin_required
def admin_reports(request):
    """Date-range financial and operational report for admins."""
    from decimal import Decimal
    today = timezone.now().date()
    date_from_str = request.GET.get('date_from', (today - datetime.timedelta(days=30)).isoformat())
    date_to_str = request.GET.get('date_to', today.isoformat())
    try:
        dt_from = datetime.date.fromisoformat(date_from_str)
        dt_to = datetime.date.fromisoformat(date_to_str)
    except ValueError:
        dt_from = today - datetime.timedelta(days=30)
        dt_to = today

    paid_payments = Payment.objects.filter(
        is_deleted=False,
        status=PaymentStatus.PAID,
        created_at__date__gte=dt_from,
        created_at__date__lte=dt_to,
    )

    agg = paid_payments.aggregate(
        total_patient=Sum('patient_pays'),
        total_insurance=Sum('insurance_covered'),
        total_gross=Sum('total_amount'),
    )
    total_patient = agg['total_patient'] or Decimal('0')
    total_insurance = agg['total_insurance'] or Decimal('0')
    total_gross = agg['total_gross'] or Decimal('0')

    def type_stats(ptype):
        qs = paid_payments.filter(payment_type=ptype)
        return {
            'count': qs.count(),
            'total': qs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0'),
        }

    consultation_stats = type_stats(PaymentType.CONSULTATION)
    lab_stats = type_stats(PaymentType.LAB)
    supplies_stats = type_stats(PaymentType.SUPPLIES)
    combined_stats = type_stats(PaymentType.COMBINED)

    new_patients = Patient.objects.filter(
        is_deleted=False, created_at__date__gte=dt_from, created_at__date__lte=dt_to
    ).count()
    new_visits = Visit.objects.filter(
        is_deleted=False, created_at__date__gte=dt_from, created_at__date__lte=dt_to
    ).count()

    recent_payments = (
        paid_payments
        .select_related('visit__patient')
        .order_by('-created_at')[:30]
    )

    hs = HospitalSettings.get()
    return render(request, 'core/reports.html', {
        'date_from': date_from_str,
        'date_to': date_to_str,
        'total_patient': total_patient,
        'total_insurance': total_insurance,
        'total_gross': total_gross,
        'total_payments': paid_payments.count(),
        'consultation_stats': consultation_stats,
        'lab_stats': lab_stats,
        'supplies_stats': supplies_stats,
        'combined_stats': combined_stats,
        'new_patients': new_patients,
        'new_visits': new_visits,
        'recent_payments': recent_payments,
        'currency': hs.currency,
    })


# ─── INSURANCE MANAGEMENT ────────────────────────────────────────────────────

@admin_required
def hospital_settings(request):
    settings_obj = HospitalSettings.get()
    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'billing')
        try:
            if form_type == 'branding':
                name = request.POST.get('hospital_name', '').strip()
                if name:
                    settings_obj.hospital_name = name
                if 'logo' in request.FILES:
                    settings_obj.logo = request.FILES['logo']
                elif request.POST.get('remove_logo'):
                    settings_obj.logo = None
                logo_size = request.POST.get('logo_size', 'medium')
                if logo_size in ('small', 'medium', 'large'):
                    settings_obj.logo_size = logo_size
                settings_obj.updated_by = request.user
                settings_obj.save()
                AuditLog.objects.create(
                    user=request.user, action='UPDATE_SETTINGS', model_name='HospitalSettings',
                    object_id='1', description="Hospital branding updated",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                messages.success(request, "Branding saved successfully.")
            else:
                settings_obj.consultation_fee = request.POST.get('consultation_fee', '0') or '0'
                settings_obj.currency = request.POST.get('currency', 'CDF').strip() or 'CDF'
                fixed_fee = request.POST.get('fixed_fee', '').strip()
                if fixed_fee:
                    settings_obj.fixed_fee = fixed_fee
                settings_obj.updated_by = request.user
                settings_obj.save()
                AuditLog.objects.create(
                    user=request.user, action='UPDATE_SETTINGS', model_name='HospitalSettings',
                    object_id='1', description=f"Billing settings updated",
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                messages.success(request, "Billing settings saved successfully.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
        return redirect('hospital_settings')
    specialist_fees = SpecialistConsultationFee.objects.all()
    # Specialties that don't yet have a fee row
    used_specialties = set(specialist_fees.values_list('specialty', flat=True))
    available_specialties = [(v, l) for v, l in Specialty.choices if v not in used_specialties]
    from core.models import LogoSize
    return render(request, 'core/hospital_settings.html', {
        'settings': settings_obj,
        'specialist_fees': specialist_fees,
        'available_specialties': available_specialties,
        'logo_size_choices': LogoSize.choices,
    })


@admin_required
def specialist_fee_create(request):
    if request.method == 'POST':
        specialty = request.POST.get('specialty', '').strip()
        fee = request.POST.get('fee', '0').strip()
        if not specialty:
            messages.error(request, "Please select a specialty.")
            return redirect('hospital_settings')
        if SpecialistConsultationFee.objects.filter(specialty=specialty).exists():
            messages.error(request, "A fee for that specialty already exists.")
            return redirect('hospital_settings')
        try:
            obj = SpecialistConsultationFee.objects.create(
                specialty=specialty, fee=fee, updated_by=request.user
            )
            AuditLog.objects.create(
                user=request.user, action='CREATE_SPECIALIST_FEE', model_name='SpecialistConsultationFee',
                object_id=str(obj.id),
                description=f"Specialist fee created: {obj.get_specialty_display()} = {obj.fee} CDF",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Specialist fee for {obj.get_specialty_display()} set to {float(obj.fee):,.0f} CDF.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return redirect('hospital_settings')


@admin_required
def specialist_fee_edit(request, pk):
    obj = get_object_or_404(SpecialistConsultationFee, pk=pk)
    if request.method == 'POST':
        try:
            obj.fee = request.POST.get('fee', obj.fee)
            obj.is_active = 'is_active' in request.POST
            obj.updated_by = request.user
            obj.save()
            AuditLog.objects.create(
                user=request.user, action='EDIT_SPECIALIST_FEE', model_name='SpecialistConsultationFee',
                object_id=str(obj.id),
                description=f"Specialist fee updated: {obj.get_specialty_display()} = {obj.fee} CDF",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Fee for {obj.get_specialty_display()} updated.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return redirect('hospital_settings')


@admin_required
def specialist_fee_delete(request, pk):
    obj = get_object_or_404(SpecialistConsultationFee, pk=pk)
    if request.method == 'POST':
        label = obj.get_specialty_display()
        AuditLog.objects.create(
            user=request.user, action='DELETE_SPECIALIST_FEE', model_name='SpecialistConsultationFee',
            object_id=str(obj.id),
            description=f"Specialist fee deleted: {label}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        obj.delete()
        messages.success(request, f"Specialist fee for {label} removed.")
    return redirect('hospital_settings')


# ─── FORMS LIBRARY ───────────────────────────────────────────────────────────

@login_required_custom
def forms_library(request):
    q = request.GET.get('q', '').strip()
    cat = request.GET.get('category', '')

    forms_qs = HospitalForm.objects.select_related('uploaded_by')
    if request.user.role != Role.ADMIN:
        forms_qs = forms_qs.filter(is_active=True)

    if q:
        forms_qs = forms_qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if cat:
        forms_qs = forms_qs.filter(category=cat)

    # Group by category for display
    from itertools import groupby
    grouped = {}
    for form in forms_qs:
        grouped.setdefault(form.get_category_display(), []).append(form)

    return render(request, 'core/forms_library.html', {
        'grouped_forms': grouped,
        'all_forms': forms_qs,
        'categories': FormCategory.choices,
        'q': q,
        'selected_category': cat,
    })


@admin_required
def form_upload(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        category = request.POST.get('category', FormCategory.GENERAL)
        uploaded_file = request.FILES.get('file')

        if not title:
            messages.error(request, "A title is required.")
            return redirect('forms_library')
        if not uploaded_file:
            messages.error(request, "Please select a file to upload.")
            return redirect('forms_library')

        allowed_extensions = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg']
        ext = uploaded_file.name.rsplit('.', 1)[-1].lower() if '.' in uploaded_file.name else ''
        if ext not in allowed_extensions:
            messages.error(request, f"File type '.{ext}' is not allowed. Allowed: PDF, Word, Excel, or image files.")
            return redirect('forms_library')

        try:
            form_obj = HospitalForm.objects.create(
                title=title,
                description=description,
                category=category,
                file=uploaded_file,
                uploaded_by=request.user,
            )
            AuditLog.objects.create(
                user=request.user, action='UPLOAD_FORM', model_name='HospitalForm',
                object_id=str(form_obj.id),
                description=f"Form uploaded: {form_obj.title} ({form_obj.filename})",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Form '{form_obj.title}' uploaded successfully.")
        except Exception as e:
            messages.error(request, f"Upload failed: {e}")

    return redirect('forms_library')


@admin_required
def form_delete(request, pk):
    form_obj = get_object_or_404(HospitalForm, pk=pk)
    if request.method == 'POST':
        import os
        title = form_obj.title
        try:
            if form_obj.file and os.path.isfile(form_obj.file.path):
                os.remove(form_obj.file.path)
        except Exception:
            pass
        AuditLog.objects.create(
            user=request.user, action='DELETE_FORM', model_name='HospitalForm',
            object_id=str(pk),
            description=f"Form deleted: {title}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        form_obj.delete()
        messages.success(request, f"Form '{title}' deleted.")
    return redirect('forms_library')


@admin_required
def form_toggle(request, pk):
    form_obj = get_object_or_404(HospitalForm, pk=pk)
    if request.method == 'POST':
        form_obj.is_active = not form_obj.is_active
        form_obj.save()
        status = "activated" if form_obj.is_active else "deactivated"
        messages.success(request, f"Form '{form_obj.title}' {status}.")
    return redirect('forms_library')


@admin_required
def consumables_list(request):
    from django.core.paginator import Paginator
    PER_PAGE_OPTS = [10, 25, 50]
    q = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '')
    per_page = int(request.GET.get('per_page', 10))
    if per_page not in PER_PAGE_OPTS:
        per_page = 10

    consumables = Consumable.objects.all()
    if q:
        consumables = consumables.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if category_filter:
        consumables = consumables.filter(category=category_filter)

    paginator = Paginator(consumables, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'core/consumables.html', {
        'page_obj': page_obj,
        'categories': ConsumableCategory.choices,
        'category_filter': category_filter,
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
        'total_count': paginator.count,
    })


@admin_required
def consumable_create(request):
    if request.method == 'POST':
        try:
            c = Consumable.objects.create(
                name=request.POST['name'].strip(),
                category=request.POST.get('category', ConsumableCategory.ACT),
                description=request.POST.get('description', '').strip(),
                unit=request.POST.get('unit', 'unit').strip() or 'unit',
                unit_price=request.POST.get('unit_price', '0') or '0',
                created_by=request.user,
            )
            AuditLog.objects.create(
                user=request.user, action='CREATE_CONSUMABLE', model_name='Consumable',
                object_id=str(c.id), description=f"Created consumable '{c.name}'",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"'{c.name}' added to catalogue.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return redirect('consumables_list')


@admin_required
def consumable_edit(request, pk):
    c = get_object_or_404(Consumable, pk=pk)
    if request.method == 'POST':
        try:
            c.name = request.POST.get('name', c.name).strip()
            c.category = request.POST.get('category', c.category)
            c.description = request.POST.get('description', c.description).strip()
            c.unit = request.POST.get('unit', c.unit).strip() or 'unit'
            c.unit_price = request.POST.get('unit_price', c.unit_price) or '0'
            c.save()
            messages.success(request, f"'{c.name}' updated.")
            return redirect('consumables_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render(request, 'core/consumable_edit.html', {
        'c': c,
        'categories': ConsumableCategory.choices,
    })


@admin_required
def consumable_toggle(request, pk):
    c = get_object_or_404(Consumable, pk=pk)
    c.is_active = not c.is_active
    c.save()
    status = "activated" if c.is_active else "deactivated"
    messages.success(request, f"'{c.name}' {status}.")
    return redirect('consumables_list')


@admin_required
def consumable_delete(request, pk):
    c = get_object_or_404(Consumable, pk=pk)
    if c.visit_uses.exists():
        messages.error(request, f"Cannot delete '{c.name}' — it has been used in visits.")
        return redirect('consumables_list')
    if request.method == 'POST':
        name = c.name
        c.delete()
        messages.success(request, f"'{name}' deleted.")
        return redirect('consumables_list')
    return render(request, 'core/consumable_confirm_delete.html', {'c': c})


@role_required('nurse', 'doctor')
def visit_consumable_add(request, visit_pk):
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    if request.method == 'POST':
        consumable_id = request.POST.get('consumable_id')
        try:
            consumable = Consumable.objects.get(pk=consumable_id, is_active=True)
            raw_qty = str(request.POST.get('quantity', '1')).replace(',', '').strip() or '1'
            from decimal import Decimal
            qty = Decimal(raw_qty)
            if qty <= 0:
                messages.error(request, "Quantity must be greater than zero.")
                return redirect('visit_detail', pk=visit_pk)
            VisitConsumable.objects.create(
                visit=visit,
                consumable=consumable,
                quantity=qty,
                unit_price=consumable.unit_price,
                administered_by=request.user,
                notes=request.POST.get('notes', '').strip(),
            )
            messages.success(request, f"'{consumable.name}' x{qty} recorded.")
        except Consumable.DoesNotExist:
            messages.error(request, "Item not found in catalogue.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return redirect('visit_detail', pk=visit_pk)


@role_required('nurse', 'doctor')
def visit_consumable_remove(request, visit_pk, vc_pk):
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    vc = get_object_or_404(VisitConsumable, pk=vc_pk, visit=visit)
    if vc.is_billed:
        messages.error(request, "This item has already been billed and cannot be removed.")
        return redirect('visit_detail', pk=visit_pk)
    if request.method == 'POST':
        name = str(vc.consumable.name)
        vc.delete()
        messages.success(request, f"'{name}' removed.")
    return redirect('visit_detail', pk=visit_pk)


@admin_required
def insurance_list(request):
    from django.core.paginator import Paginator
    PER_PAGE_OPTS = [5, 25, 50, 100]
    q = request.GET.get('q', '').strip()
    per_page = int(request.GET.get('per_page', 25))
    if per_page not in PER_PAGE_OPTS:
        per_page = 25

    insurances = Insurance.objects.filter(is_deleted=False)

    if q:
        insurances = insurances.filter(Q(name__icontains=q))

    paginator = Paginator(insurances, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'core/insurance_list.html', {
        'page_obj': page_obj,
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
    })


@admin_required
def insurance_create(request):
    if request.method == 'POST':
        data = request.POST
        try:
            ins = Insurance.objects.create(
                name=data['name'],
                coverage_percentage=data['coverage_percentage'],
                created_by=request.user
            )
            AuditLog.objects.create(
                user=request.user, action='CREATE_INSURANCE', model_name='Insurance',
                object_id=str(ins.id), description=f"Created insurance {ins.name}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Insurance provider '{ins.name}' created.")
            return redirect('insurance_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render(request, 'core/insurance_form.html', {'action': 'Create'})


@admin_required
def insurance_edit(request, pk):
    ins = get_object_or_404(Insurance, pk=pk, is_deleted=False)
    if request.method == 'POST':
        ins.name = request.POST.get('name', ins.name)
        ins.coverage_percentage = request.POST.get('coverage_percentage', ins.coverage_percentage)
        ins.is_active = 'is_active' in request.POST
        ins.save()
        messages.success(request, "Insurance updated.")
        return redirect('insurance_list')
    return render(request, 'core/insurance_form.html', {'obj': ins, 'action': 'Edit'})


@admin_required
def insurance_delete(request, pk):
    ins = get_object_or_404(Insurance, pk=pk, is_deleted=False)
    if request.method == 'POST':
        name = ins.name
        ins.is_deleted = True
        ins.is_active = False
        ins.save()
        AuditLog.objects.create(
            user=request.user, action='DELETE_INSURANCE', model_name='Insurance',
            object_id=str(ins.id), description=f"Deleted insurance provider {name}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, f"Insurance provider '{name}' deleted.")
        return redirect('insurance_list')
    return render(request, 'core/insurance_confirm_delete.html', {'obj': ins})
