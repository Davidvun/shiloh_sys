from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Exists, OuterRef, Subquery
from core.models import User, Insurance, Role
from core.decorators import role_required, login_required_custom, admin_required
from audit.models import ChangeRequest, ChangeRequestType, AuditLog, ChangeRequestStatus
from .models import Patient, Visit, VisitStatus
from billing.models import Payment, PaymentStatus, PaymentType
import json
from django.contrib.contenttypes.models import ContentType


@login_required_custom
def patient_list(request):
    from django.core.paginator import Paginator
    user = request.user
    q = request.GET.get('q', '').strip()
    PER_PAGE_OPTS = [5, 25, 50, 100]
    per_page = int(request.GET.get('per_page', 25))
    if per_page not in PER_PAGE_OPTS:
        per_page = 25

    patients = Patient.objects.filter(is_deleted=False)

    # Accountants should not see patient list directly
    if user.role == Role.ACCOUNTANT:
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    # Doctors only see patients with an active visit assigned to them
    if user.role == Role.DOCTOR:
        patients = patients.filter(
            visits__doctor=user,
            visits__is_deleted=False,
            visits__status__in=[VisitStatus.PENDING, VisitStatus.IN_PROGRESS]
        ).distinct()

    # Nurses see all patients with an active pending visit
    if user.role == Role.NURSE:
        active_visit = Visit.objects.filter(
            patient=OuterRef('pk'), is_deleted=False,
            status=VisitStatus.PENDING,
        )
        patients = patients.filter(Exists(active_visit))

    if q:
        patients = patients.filter(
            Q(full_name__icontains=q) | Q(patient_id__icontains=q) | Q(phone__icontains=q)
        )

    # Annotate each patient with their active visit's payment status
    active_visit_qs = Visit.objects.filter(
        patient=OuterRef('pk'), is_deleted=False,
        status__in=[VisitStatus.PENDING, VisitStatus.IN_PROGRESS]
    )
    if user.role == Role.DOCTOR:
        active_visit_qs = active_visit_qs.filter(doctor=user)

    paid_qs = Payment.objects.filter(
        visit__patient=OuterRef('pk'), visit__is_deleted=False,
        visit__status__in=[VisitStatus.PENDING, VisitStatus.IN_PROGRESS],
        payment_type=PaymentType.CONSULTATION, status=PaymentStatus.PAID, is_deleted=False
    )
    if user.role == Role.DOCTOR:
        paid_qs = paid_qs.filter(visit__doctor=user)

    # Annotate with triage visit PK for nurses (any pending visit without triage yet)
    triage_visit_qs = Visit.objects.filter(
        patient=OuterRef('pk'), is_deleted=False,
        status=VisitStatus.PENDING, triage__isnull=True
    ).values('pk')[:1]

    patients = patients.annotate(
        has_active_visit=Exists(active_visit_qs),
        has_paid_visit=Exists(paid_qs),
        triage_visit_pk=Subquery(triage_visit_qs)
    )

    paginator = Paginator(patients, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'patients/patient_list.html', {
        'page_obj': page_obj,
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
    })


@role_required('receptionist', 'admin')
def patient_register(request):
    if request.method == 'POST':
        data = request.POST
        insurance_id = data.get('insurance')
        insurance = Insurance.objects.filter(pk=insurance_id, is_deleted=False).first() if insurance_id else None
        try:
            patient = Patient.objects.create(
                full_name=data['full_name'],
                age=data['age'],
                gender=data['gender'],
                phone=data['phone'],
                address=data['address'],
                insurance=insurance,
                registered_by=request.user
            )
            AuditLog.objects.create(
                user=request.user, action='REGISTER_PATIENT', model_name='Patient',
                object_id=str(patient.id), description=f"Registered patient {patient.full_name}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Patient registered. ID: {patient.patient_id}")
            return redirect('patient_detail', pk=patient.pk)
        except Exception as e:
            messages.error(request, f"Error: {e}")

    insurances = Insurance.objects.filter(is_deleted=False, is_active=True)
    return render(request, 'patients/patient_form.html', {'insurances': insurances, 'action': 'Register'})


@login_required_custom
def patient_detail(request, pk):
    user = request.user
    patient = get_object_or_404(Patient, pk=pk, is_deleted=False)

    # Doctors can only see patients assigned to them
    if user.role == Role.DOCTOR:
        has_access = Visit.objects.filter(patient=patient, doctor=user, is_deleted=False).exists()
        if not has_access:
            messages.error(request, "You are not assigned to this patient.")
            return redirect('dashboard')

    # Accountants can see patient for billing, but only billing info
    visits = Visit.objects.filter(patient=patient, is_deleted=False).select_related('doctor')

    ctx = {'patient': patient, 'visits': visits}

    # Only show financial info to accountants and admins
    if user.role in [Role.ACCOUNTANT, Role.ADMIN]:
        from billing.models import Payment
        ctx['payments'] = patient.visits.filter(is_deleted=False).prefetch_related('payments')

    return render(request, 'patients/patient_detail.html', ctx)


@role_required('receptionist', 'admin')
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk, is_deleted=False)
    if request.method == 'POST':
        data = request.POST
        before = {
            'full_name': patient.full_name, 'age': patient.age,
            'gender': patient.gender, 'phone': patient.phone, 'address': patient.address
        }
        patient.full_name = data.get('full_name', patient.full_name)
        patient.age = data.get('age', patient.age)
        patient.gender = data.get('gender', patient.gender)
        patient.phone = data.get('phone', patient.phone)
        patient.address = data.get('address', patient.address)
        patient.save()
        after = {
            'full_name': patient.full_name, 'age': patient.age,
            'gender': patient.gender, 'phone': patient.phone, 'address': patient.address
        }
        AuditLog.objects.create(
            user=request.user, action='EDIT_PATIENT', model_name='Patient',
            object_id=str(patient.id),
            description=f"Edited patient {patient.full_name} (ID: {patient.patient_id}). Before: {before}. After: {after}.",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, "Patient details updated successfully.")
        return redirect('patient_detail', pk=pk)
    return render(request, 'patients/patient_edit.html', {'patient': patient})


@role_required('receptionist', 'admin')
def patient_delete(request, pk):
    patient = get_object_or_404(Patient, pk=pk, is_deleted=False)
    if request.method == 'POST':
        name = patient.full_name
        pid = patient.patient_id
        patient.is_deleted = True
        patient.save()
        AuditLog.objects.create(
            user=request.user, action='DELETE_PATIENT', model_name='Patient',
            object_id=str(patient.id),
            description=f"Deleted patient {name} (ID: {pid}). Reason: {request.POST.get('reason', 'N/A')}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, f"Patient {name} has been deleted.")
        return redirect('patient_list')
    return render(request, 'patients/patient_confirm_delete.html', {'patient': patient})


@role_required('receptionist', 'admin')
def patient_edit_request(request, pk):
    return redirect('patient_edit', pk=pk)


@role_required('receptionist', 'admin')
def patient_delete_request(request, pk):
    return redirect('patient_delete', pk=pk)


# ─── VISITS ─────────────────────────────────────────────────────────────────

@role_required('receptionist', 'admin')
def visit_create(request, patient_pk):
    patient = get_object_or_404(Patient, pk=patient_pk, is_deleted=False)
    doctors = User.objects.filter(role=Role.DOCTOR, is_active=True, is_deleted=False)
    if request.method == 'POST':
        doctor_id = request.POST.get('doctor')
        doctor = get_object_or_404(User, pk=doctor_id, role=Role.DOCTOR)
        visit = Visit.objects.create(
            patient=patient,
            doctor=doctor,
            assigned_by=request.user,
            needs_triage=True,
            notes=request.POST.get('notes', '')
        )
        AuditLog.objects.create(
            user=request.user, action='CREATE_VISIT', model_name='Visit',
            object_id=str(visit.id), description=f"Created visit for {patient} → Dr. {doctor}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, f"Visit created. Patient added to the queue.")

        return redirect('patient_detail', pk=patient.pk)
    return render(request, 'patients/visit_form.html', {'patient': patient, 'doctors': doctors})


@login_required_custom
def visit_detail(request, pk):
    user = request.user
    visit = get_object_or_404(Visit, pk=pk, is_deleted=False)

    # Enforce doctor can only see their own visits
    if user.role == Role.DOCTOR and visit.doctor != user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    from clinical.models import Triage, Consultation
    from billing.models import Payment, PaymentType, PaymentStatus
    consultation_paid = visit.payments.filter(
        payment_type__in=[PaymentType.CONSULTATION, PaymentType.COMBINED],
        status=PaymentStatus.PAID,
        is_deleted=False
    ).exists()
    ctx = {
        'visit': visit,
        'consultation_paid': consultation_paid,
    }

    # Clinical data is strictly off-limits for admin — only clinical staff can see it
    if user.role in [Role.NURSE, Role.DOCTOR]:
        ctx['triage'] = getattr(visit, 'triage', None)

    if user.role == Role.DOCTOR:
        ctx['consultation'] = getattr(visit, 'consultation', None)
        from laboratory.models import LabRequest
        ctx['lab_requests'] = visit.lab_requests.filter(
            is_deleted=False
        ).select_related('result', 'result__performed_by').prefetch_related(
            'result__values__parameter'
        ).order_by('created_at')

    from core.models import VisitConsumable, Consumable, ConsumableCategory
    ctx['visit_consumables'] = visit.consumables.select_related(
        'consumable', 'administered_by'
    ).order_by('created_at')
    if user.role in [Role.NURSE, Role.DOCTOR]:
        all_consumables = Consumable.objects.filter(is_active=True).order_by('category', 'name')
        ctx['all_consumables'] = all_consumables
        ctx['consumable_categories'] = ConsumableCategory.choices
        category_labels = dict(ConsumableCategory.choices)
        ctx['consumables_data'] = [
            {
                'id': c.pk,
                'name': c.name,
                'category': category_labels.get(c.category, c.category),
                'unit': c.unit,
                'price': float(c.unit_price) if c.unit_price else None,
            }
            for c in all_consumables
        ]

    return render(request, 'patients/visit_detail.html', ctx)
