from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from core.models import Role
from core.decorators import role_required, admin_required
from audit.models import AuditLog
from patients.models import Visit
from .models import LabRequest, LabResult, LabRequestStatus, LabTest, LabTestCategory, LabTestParameter, LabResultValue


@role_required('doctor', 'admin')
def lab_request_create(request, visit_pk):
    import json as _json
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    if request.user.role == Role.DOCTOR and visit.doctor != request.user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    if request.method == 'POST':
        raw = request.POST.get('tests_json', '')
        try:
            tests_list = _json.loads(raw) if raw else []
        except ValueError:
            tests_list = []
        if not tests_list:
            messages.error(request, "Please add at least one lab test before submitting.")
            return redirect('lab_request_create', visit_pk=visit_pk)
        created = []
        for item in tests_list:
            lab_test = None
            test_name = (item.get('custom_test_name') or '').strip()
            test_id = item.get('lab_test')
            if test_id:
                try:
                    lab_test = LabTest.objects.get(pk=test_id, is_active=True)
                    test_name = lab_test.name
                except LabTest.DoesNotExist:
                    pass
            if not test_name:
                continue
            lab = LabRequest.objects.create(
                visit=visit,
                lab_test=lab_test,
                test_name=test_name,
                test_description=item.get('test_description', ''),
                urgency=item.get('urgency', 'routine'),
                requested_by=request.user
            )
            if lab_test:
                param_ids = item.get('parameters', [])
                if param_ids:
                    lab.selected_parameters.set(
                        LabTestParameter.objects.filter(pk__in=param_ids, lab_test=lab_test)
                    )
            AuditLog.objects.create(
                user=request.user, action='REQUEST_LAB', model_name='LabRequest',
                object_id=str(lab.id),
                description=f"Lab request {lab.test_name} for visit {visit_pk}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            created.append(lab.test_name)
        if created:
            messages.success(request, f"{len(created)} lab test(s) requested: {', '.join(created)}.")
        return redirect('visit_detail', pk=visit_pk)
    categories = LabTestCategory.objects.filter(is_active=True).prefetch_related('tests__parameters')
    tests_data = []
    for cat in categories:
        for t in cat.tests.all():
            if not t.is_active:
                continue
            tests_data.append({
                'id': t.pk,
                'name': t.name,
                'category': cat.name,
                'price': float(t.default_price) if t.default_price else None,
                'parameters': [{'id': p.pk, 'name': p.name, 'unit': p.unit} for p in t.parameters.all()],
            })
    tests_data.sort(key=lambda x: (x['category'].lower(), x['name'].lower()))
    return render(request, 'laboratory/lab_request_form.html', {'visit': visit, 'tests_data': tests_data})


@role_required('lab_technician', 'admin')
def lab_queue(request):
    """Patient list — one row per visit with active lab requests."""
    from django.core.paginator import Paginator
    from django.db.models import Prefetch, Q
    PER_PAGE_OPTS = [5, 25, 50, 100]
    q = request.GET.get('q', '').strip()
    per_page = int(request.GET.get('per_page', 25))
    if per_page not in PER_PAGE_OPTS:
        per_page = 25

    active_qs = LabRequest.objects.filter(
        is_deleted=False,
        status__in=[LabRequestStatus.PAID, LabRequestStatus.REQUESTED, LabRequestStatus.IN_PROGRESS]
    ).select_related('requested_by')

    visits = Visit.objects.filter(
        is_deleted=False,
        lab_requests__status__in=[LabRequestStatus.PAID, LabRequestStatus.REQUESTED, LabRequestStatus.IN_PROGRESS],
        lab_requests__is_deleted=False,
    ).distinct().select_related('patient', 'doctor').prefetch_related(
        Prefetch('lab_requests', queryset=active_qs, to_attr='active_labs')
    ).order_by('-created_at')

    if q:
        visits = visits.filter(
            Q(patient__full_name__icontains=q) |
            Q(patient__patient_id__icontains=q)
        )

    paginator = Paginator(visits, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    URGENCY_RANK = {'stat': 0, 'urgent': 1, 'routine': 2}
    for v in page_obj:
        v.lab_count = len(v.active_labs)
        top = min(v.active_labs, key=lambda l: URGENCY_RANK.get(l.urgency, 9), default=None)
        v.top_urgency = top.urgency if top else 'routine'
        v.has_unpaid = any(l.status == LabRequestStatus.REQUESTED for l in v.active_labs)

    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'laboratory/lab_queue.html', {
        'page_obj': page_obj,
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
    })


@role_required('lab_technician', 'admin')
def lab_queue_visit(request, visit_pk):
    """Detail — all active lab requests for one visit."""
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    labs = LabRequest.objects.filter(
        visit=visit, is_deleted=False,
        status__in=[LabRequestStatus.PAID, LabRequestStatus.REQUESTED, LabRequestStatus.IN_PROGRESS]
    ).select_related('requested_by', 'lab_test__category').order_by('urgency', 'created_at')
    if not labs.exists():
        messages.info(request, "No active lab tests for this patient.")
        return redirect('lab_queue')
    return render(request, 'laboratory/lab_queue_visit.html', {'visit': visit, 'labs': labs})


@role_required('lab_technician', 'admin')
def lab_result_upload(request, lab_pk):
    lab = get_object_or_404(LabRequest, pk=lab_pk, is_deleted=False)
    if lab.lab_test and lab.selected_parameters.exists():
        parameters = lab.selected_parameters.all()
    elif lab.lab_test:
        parameters = lab.lab_test.parameters.all()
    else:
        parameters = LabTestParameter.objects.none()
    if request.method == 'POST':
        d = request.POST
        result_text = d.get('result_text', '')
        if parameters.exists() and not result_text:
            lines = []
            for p in parameters:
                val = (d.get(f'param_{p.pk}') or '').strip()
                if val:
                    unit = f" {p.unit}" if p.unit else ""
                    lines.append(f"{p.name}: {val}{unit}")
            result_text = "\n".join(lines)
        result = LabResult.objects.create(
            lab_request=lab,
            result_text=result_text,
            reference_range=d.get('reference_range', ''),
            interpretation=d.get('interpretation', ''),
            performed_by=request.user,
            result_file=request.FILES.get('result_file')
        )
        for p in parameters:
            val = (d.get(f'param_{p.pk}') or '').strip()
            if val:
                LabResultValue.objects.create(
                    result=result, parameter=p, value=val,
                    is_abnormal=f'abnormal_{p.pk}' in d
                )
        lab.status = LabRequestStatus.COMPLETED
        lab.save()
        AuditLog.objects.create(
            user=request.user, action='UPLOAD_LAB_RESULT', model_name='LabResult',
            object_id=str(result.id), description=f"Result uploaded for lab {lab_pk}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, "Lab result uploaded.")
        remaining = LabRequest.objects.filter(
            visit=lab.visit, is_deleted=False,
            status__in=[LabRequestStatus.PAID, LabRequestStatus.IN_PROGRESS, LabRequestStatus.REQUESTED]
        ).exists()
        if remaining:
            return redirect('lab_queue_visit', visit_pk=lab.visit_id)
        return redirect('lab_queue')
    return render(request, 'laboratory/lab_result_form.html', {'lab': lab, 'parameters': parameters})


# ─── ADMIN: LAB CATALOG MANAGEMENT ────────────────────────────────────────────

@role_required('doctor', 'admin')
def lab_request_cancel(request, pk):
    if request.method != 'POST':
        return redirect('dashboard')
    lab = get_object_or_404(LabRequest, pk=pk, is_deleted=False)
    if request.user.role == Role.DOCTOR and lab.requested_by != request.user:
        messages.error(request, "Access denied.")
        return redirect('visit_detail', pk=lab.visit_id)
    if lab.status != LabRequestStatus.REQUESTED:
        messages.error(request, f"Cannot cancel '{lab.test_name}' — it has already been paid or is in progress. Contact billing to revoke the payment.")
        return redirect('visit_detail', pk=lab.visit_id)
    lab.is_deleted = True
    lab.save()
    AuditLog.objects.create(
        user=request.user, action='CANCEL_LAB_REQUEST', model_name='LabRequest',
        object_id=str(lab.id), description=f"Cancelled lab request '{lab.test_name}' for visit {lab.visit_id}",
        ip_address=request.META.get('REMOTE_ADDR')
    )
    messages.success(request, f"Lab request '{lab.test_name}' cancelled.")
    return redirect('visit_detail', pk=lab.visit_id)


@role_required('lab_technician', 'admin')
def lab_completed(request):
    from django.core.paginator import Paginator
    from django.db.models import Q
    q = request.GET.get('q', '').strip()
    labs = LabRequest.objects.filter(
        is_deleted=False,
        status=LabRequestStatus.COMPLETED
    ).select_related('visit__patient', 'requested_by', 'result').order_by('-updated_at')
    if q:
        labs = labs.filter(
            Q(visit__patient__full_name__icontains=q) |
            Q(test_name__icontains=q) |
            Q(visit__patient__patient_id__icontains=q)
        )
    paginator = Paginator(labs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'laboratory/lab_completed.html', {'page_obj': page_obj, 'q': q})


@role_required('lab_technician', 'admin')
def lab_result_edit(request, lab_pk):
    lab = get_object_or_404(LabRequest, pk=lab_pk, is_deleted=False, status=LabRequestStatus.COMPLETED)
    result = get_object_or_404(LabResult, lab_request=lab)
    if lab.lab_test and lab.selected_parameters.exists():
        parameters = lab.selected_parameters.all()
    elif lab.lab_test:
        parameters = lab.lab_test.parameters.all()
    else:
        parameters = LabTestParameter.objects.none()
    if request.method == 'POST':
        d = request.POST
        result_text = d.get('result_text', '')
        if parameters.exists():
            result.values.all().delete()
            lines = []
            for p in parameters:
                val = (d.get(f'param_{p.pk}') or '').strip()
                if val:
                    unit = f" {p.unit}" if p.unit else ""
                    lines.append(f"{p.name}: {val}{unit}")
                    LabResultValue.objects.create(
                        result=result, parameter=p, value=val,
                        is_abnormal=f'abnormal_{p.pk}' in d
                    )
            if not result_text:
                result_text = "\n".join(lines)
        result.result_text = result_text
        result.reference_range = d.get('reference_range', result.reference_range)
        result.interpretation = d.get('interpretation', result.interpretation)
        if 'result_file' in request.FILES:
            result.result_file = request.FILES['result_file']
        result.save()
        AuditLog.objects.create(
            user=request.user, action='EDIT_LAB_RESULT', model_name='LabResult',
            object_id=str(result.id), description=f"Edited result for lab {lab_pk} ({lab.test_name})",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, f"Result for '{lab.test_name}' updated.")
        return redirect('lab_completed')
    return render(request, 'laboratory/lab_result_edit.html', {
        'lab': lab, 'result': result, 'parameters': parameters
    })


@admin_required
def lab_catalog(request):
    categories = LabTestCategory.objects.prefetch_related('tests__parameters').all()
    return render(request, 'laboratory/lab_catalog.html', {'categories': categories})


@admin_required
def lab_category_create(request):
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        if not name:
            messages.error(request, "Category name is required.")
        elif LabTestCategory.objects.filter(name__iexact=name).exists():
            messages.error(request, f"Category '{name}' already exists.")
        else:
            order = LabTestCategory.objects.count() + 1
            cat = LabTestCategory.objects.create(name=name, order=order)
            AuditLog.objects.create(
                user=request.user, action='CREATE_LAB_CATEGORY', model_name='LabTestCategory',
                object_id=str(cat.id), description=f"Created lab category {cat.name}",
                ip_address=request.META.get('REMOTE_ADDR'))
            messages.success(request, f"Category '{cat.name}' added.")
        return redirect('lab_catalog')
    return redirect('lab_catalog')


@admin_required
def lab_category_toggle(request, pk):
    cat = get_object_or_404(LabTestCategory, pk=pk)
    cat.is_active = not cat.is_active
    cat.save()
    messages.success(request, f"Category '{cat.name}' {'activated' if cat.is_active else 'disabled'}.")
    return redirect('lab_catalog')


@admin_required
def lab_category_delete(request, pk):
    if request.method != 'POST':
        return redirect('lab_catalog')
    cat = get_object_or_404(LabTestCategory, pk=pk)
    active_statuses = [LabRequestStatus.REQUESTED, LabRequestStatus.PAID, LabRequestStatus.IN_PROGRESS]
    if LabRequest.objects.filter(lab_test__category=cat, status__in=active_statuses).exists():
        messages.error(request, f"Cannot delete '{cat.name}' — it has active lab requests in progress. Disable it instead.")
        return redirect('lab_catalog')
    name = cat.name
    cat.delete()
    AuditLog.objects.create(
        user=request.user, action='DELETE_LAB_CATEGORY', model_name='LabTestCategory',
        object_id=str(pk), description=f"Deleted lab category {name}",
        ip_address=request.META.get('REMOTE_ADDR'))
    messages.success(request, f"Category '{name}' deleted.")
    return redirect('lab_catalog')


@admin_required
def lab_test_create(request):
    if request.method == 'POST':
        d = request.POST
        cat_id = d.get('category')
        name = (d.get('name') or '').strip()
        price = d.get('default_price') or 0
        if not (cat_id and name):
            messages.error(request, "Category and test name are required.")
        elif LabTest.objects.filter(category_id=cat_id, name__iexact=name).exists():
            messages.error(request, f"Test '{name}' already exists in that category.")
        else:
            t = LabTest.objects.create(category_id=cat_id, name=name, default_price=price or 0)
            AuditLog.objects.create(
                user=request.user, action='CREATE_LAB_TEST', model_name='LabTest',
                object_id=str(t.id), description=f"Created lab test {t.name}",
                ip_address=request.META.get('REMOTE_ADDR'))
            messages.success(request, f"Test '{t.name}' added.")
    return redirect('lab_catalog')


@admin_required
def lab_test_edit(request, pk):
    t = get_object_or_404(LabTest, pk=pk)
    if request.method == 'POST':
        d = request.POST
        t.name = (d.get('name') or t.name).strip()
        t.default_price = d.get('default_price') or 0
        t.category_id = d.get('category') or t.category_id
        t.is_active = 'is_active' in d
        t.save()
        messages.success(request, f"Test '{t.name}' updated.")
        return redirect('lab_catalog')
    return render(request, 'laboratory/lab_test_form.html', {'test': t, 'categories': LabTestCategory.objects.all()})


@admin_required
def lab_test_toggle(request, pk):
    t = get_object_or_404(LabTest, pk=pk)
    t.is_active = not t.is_active
    t.save()
    messages.success(request, f"Test '{t.name}' {'activated' if t.is_active else 'disabled'}.")
    return redirect('lab_catalog')


@admin_required
def lab_test_delete(request, pk):
    if request.method != 'POST':
        return redirect('lab_catalog')
    t = get_object_or_404(LabTest, pk=pk)
    active_statuses = [LabRequestStatus.REQUESTED, LabRequestStatus.PAID, LabRequestStatus.IN_PROGRESS]
    if LabRequest.objects.filter(lab_test=t, status__in=active_statuses).exists():
        messages.error(request, f"Cannot delete '{t.name}' — it has active lab requests in progress. Disable it instead.")
        return redirect('lab_catalog')
    name = t.name
    t.delete()
    AuditLog.objects.create(
        user=request.user, action='DELETE_LAB_TEST', model_name='LabTest',
        object_id=str(pk), description=f"Deleted lab test {name}",
        ip_address=request.META.get('REMOTE_ADDR'))
    messages.success(request, f"Test '{name}' deleted.")
    return redirect('lab_catalog')


@admin_required
def lab_test_parameter_create(request, test_pk):
    test = get_object_or_404(LabTest, pk=test_pk)
    if request.method == 'POST':
        d = request.POST
        name = (d.get('name') or '').strip()
        if not name:
            messages.error(request, "Component name is required.")
        elif LabTestParameter.objects.filter(lab_test=test, name__iexact=name).exists():
            messages.error(request, f"Component '{name}' already exists for this test.")
        else:
            order = test.parameters.count() + 1
            LabTestParameter.objects.create(
                lab_test=test, name=name,
                unit=(d.get('unit') or '').strip(),
                reference_range=(d.get('reference_range') or '').strip(),
                order=order,
            )
            messages.success(request, f"Component '{name}' added to '{test.name}'.")
    return redirect('lab_catalog')


@admin_required
def lab_test_parameter_delete(request, pk):
    param = get_object_or_404(LabTestParameter, pk=pk)
    if request.method == 'POST':
        test_name = param.lab_test.name
        param.delete()
        messages.success(request, f"Component removed from '{test_name}'.")
    return redirect('lab_catalog')
