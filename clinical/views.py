from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from core.models import Role
from core.decorators import role_required
from audit.models import AuditLog
from patients.models import Visit, VisitStatus
from .models import Triage, Consultation


@role_required('nurse', 'admin')
def triage_create(request, visit_pk):
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    if hasattr(visit, 'triage'):
        messages.warning(request, "Triage already recorded for this visit.")
        return redirect('visit_detail', pk=visit_pk)
    if request.method == 'POST':
        d = request.POST
        try:
            triage = Triage.objects.create(
                visit=visit,
                temperature=d.get('temperature') or None,
                blood_pressure=d.get('blood_pressure', ''),
                pulse_rate=d.get('pulse_rate') or None,
                respiratory_rate=d.get('respiratory_rate') or None,
                weight=d.get('weight') or None,
                height=d.get('height') or None,
                oxygen_saturation=d.get('oxygen_saturation') or None,
                chief_complaint=d['chief_complaint'],
                notes=d.get('notes', ''),
                recorded_by=request.user
            )
            visit.status = VisitStatus.IN_PROGRESS
            visit.save()
            AuditLog.objects.create(
                user=request.user, action='CREATE_TRIAGE', model_name='Triage',
                object_id=str(triage.id), description=f"Triage recorded for visit {visit_pk}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, "Triage recorded.")
            return redirect('visit_detail', pk=visit_pk)
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return render(request, 'clinical/triage_form.html', {'visit': visit})


@role_required('doctor', 'admin')
def consultation_create(request, visit_pk):
    """Unified assessment form — all sections on one page, save draft or complete."""
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    if request.user.role == Role.DOCTOR and visit.doctor != request.user:
        messages.error(request, "You are not assigned to this patient.")
        return redirect('dashboard')

    consultation = getattr(visit, 'consultation', None)

    if request.method == 'POST':
        d = request.POST
        action = d.get('action', 'save')   # 'save' = draft, 'complete' = finalise

        data = {
            'presenting_complaint': d.get('presenting_complaint', ''),
            'history':              d.get('history', ''),
            'past_history':         d.get('past_history', ''),
            'examination_findings': d.get('examination_findings', ''),
            'diagnosis':            d.get('diagnosis', ''),
            'treatment_plan':       d.get('treatment_plan', ''),
            'follow_up_notes':      d.get('follow_up_notes', ''),
        }

        if action == 'complete':
            patient_next = d.get('patient_next', 'none')
            data['admit_patient']     = (patient_next == 'admit')
            data['discharge_patient'] = (patient_next == 'discharge')

        if consultation:
            for k, v in data.items():
                setattr(consultation, k, v)
            consultation.save()
            audit_action = 'UPDATE_CONSULTATION'
        else:
            consultation = Consultation.objects.create(
                visit=visit, doctor=request.user, **data
            )
            audit_action = 'CREATE_CONSULTATION'

        if action == 'complete' and data.get('discharge_patient'):
            visit.status = VisitStatus.COMPLETED
            visit.save()

        AuditLog.objects.create(
            user=request.user, action=audit_action, model_name='Consultation',
            object_id=str(consultation.id),
            description=f"Consultation {'draft saved' if action == 'save' else 'completed'} for visit {visit_pk}",
            ip_address=request.META.get('REMOTE_ADDR')
        )

        if action == 'save':
            messages.success(request, "Assessment saved — you can continue editing it anytime.")
        else:
            messages.success(request, "Consultation completed.")
        return redirect('visit_detail', pk=visit_pk)

    return render(request, 'clinical/consultation_form.html', {
        'visit': visit,
        'consultation': consultation,
    })


@role_required('doctor', 'admin')
def consultation_step2(request, visit_pk):
    """Kept for URL compatibility — redirects to unified form."""
    return redirect('consultation_create', visit_pk=visit_pk)


@role_required('doctor', 'admin')
def consultation_edit(request, visit_pk):
    """Kept for URL compatibility — redirects to unified form."""
    return redirect('consultation_create', visit_pk=visit_pk)


@role_required('doctor', 'admin')
def doctor_records(request):
    """Completed consultations for the logged-in doctor, with search and pagination."""
    PER_PAGE_OPTS = [5, 25, 50, 100]
    q = request.GET.get('q', '').strip()
    per_page = int(request.GET.get('per_page', 25))
    if per_page not in PER_PAGE_OPTS:
        per_page = 25

    qs = Visit.objects.filter(
        is_deleted=False,
        consultation__diagnosis__gt='',
    ).select_related('patient', 'doctor', 'consultation').order_by('-consultation__updated_at')

    if request.user.role == Role.DOCTOR:
        qs = qs.filter(doctor=request.user)

    if q:
        qs = qs.filter(
            Q(patient__full_name__icontains=q) |
            Q(patient__patient_id__icontains=q) |
            Q(consultation__diagnosis__icontains=q)
        )

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'clinical/doctor_records.html', {
        'page_obj': page_obj,
        'q': q,
        'total': paginator.count,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
    })
