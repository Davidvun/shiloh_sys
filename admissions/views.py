from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from core.models import Role
from core.decorators import role_required
from audit.models import AuditLog
from patients.models import Visit
from .models import Admission, AdmissionStatus


@role_required('doctor', 'admin')
def admission_create(request, visit_pk):
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    if request.user.role == Role.DOCTOR and visit.doctor != request.user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    if hasattr(visit, 'admission'):
        messages.warning(request, "Patient is already admitted.")
        return redirect('visit_detail', pk=visit_pk)
    if request.method == 'POST':
        d = request.POST
        admission = Admission.objects.create(
            visit=visit,
            ward=d['ward'],
            bed_number=d['bed_number'],
            daily_rate=d.get('daily_rate', 0),
            admission_notes=d.get('admission_notes', ''),
            admitted_by=request.user
        )
        AuditLog.objects.create(
            user=request.user, action='ADMIT_PATIENT', model_name='Admission',
            object_id=str(admission.id),
            description=f"Admitted {visit.patient} to Ward {admission.ward} Bed {admission.bed_number}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, f"Patient admitted to Ward {admission.ward}, Bed {admission.bed_number}.")
        return redirect('visit_detail', pk=visit_pk)
    return render(request, 'admissions/admission_form.html', {'visit': visit})


@role_required('doctor', 'admin')
def patient_discharge(request, visit_pk):
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    admission = get_object_or_404(Admission, visit=visit)
    if request.method == 'POST':
        admission.discharge_date = timezone.now()
        admission.status = AdmissionStatus.DISCHARGED
        admission.discharge_notes = request.POST.get('discharge_notes', '')
        admission.discharged_by = request.user
        admission.save()
        AuditLog.objects.create(
            user=request.user, action='DISCHARGE_PATIENT', model_name='Admission',
            object_id=str(admission.id), description=f"Discharged {visit.patient}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, "Patient discharged.")
        return redirect('visit_detail', pk=visit_pk)
    return render(request, 'admissions/discharge_form.html', {'visit': visit, 'admission': admission})


@role_required('admin', 'nurse')
def admission_list(request):
    from django.core.paginator import Paginator
    from django.db.models import Q
    PER_PAGE_OPTS = [5, 25, 50, 100]
    q = request.GET.get('q', '').strip()
    per_page = int(request.GET.get('per_page', 25))
    if per_page not in PER_PAGE_OPTS:
        per_page = 25

    admissions = Admission.objects.filter(
        is_deleted=False, status=AdmissionStatus.ADMITTED
    ).select_related('visit__patient', 'visit__doctor')

    if q:
        admissions = admissions.filter(
            Q(visit__patient__full_name__icontains=q) |
            Q(visit__patient__patient_id__icontains=q) |
            Q(ward__icontains=q) |
            Q(bed_number__icontains=q)
        )

    paginator = Paginator(admissions, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'admissions/admission_list.html', {
        'page_obj': page_obj,
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
    })
