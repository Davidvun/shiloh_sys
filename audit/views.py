from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from core.decorators import admin_required, login_required_custom
from audit.models import ChangeRequest, ChangeRequestStatus, ChangeRequestType, AuditLog


@admin_required
def change_request_list(request):
    from django.core.paginator import Paginator
    from django.db.models import Q
    PER_PAGE_OPTS = [5, 25, 50, 100]
    action_filter = request.GET.get('action', '')
    q = request.GET.get('q', '').strip()
    per_page = int(request.GET.get('per_page', 25))
    if per_page not in PER_PAGE_OPTS:
        per_page = 25

    logs_qs = AuditLog.objects.filter(
        action__in=['EDIT_PATIENT', 'DELETE_PATIENT']
    ).select_related('user').order_by('-created_at')

    if action_filter:
        logs_qs = logs_qs.filter(action=action_filter)

    if q:
        logs_qs = logs_qs.filter(
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(user__username__icontains=q) |
            Q(description__icontains=q)
        )

    paginator = Paginator(logs_qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'audit/change_request_list.html', {
        'page_obj': page_obj,
        'action_filter': action_filter,
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
    })


@admin_required
def change_request_review(request, pk):
    cr = get_object_or_404(ChangeRequest, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        cr.reviewed_by = request.user
        cr.reviewed_at = timezone.now()
        cr.admin_notes = request.POST.get('admin_notes', '')

        if action == 'approve':
            cr.status = ChangeRequestStatus.APPROVED
            cr.save()

            # Apply the change
            try:
                model_class = cr.content_type.model_class()
                obj = model_class.objects.get(pk=cr.object_id)

                if cr.request_type == ChangeRequestType.DELETE:
                    obj.is_deleted = True
                    obj.save()
                    AuditLog.objects.create(
                        user=request.user, action='APPROVED_DELETE',
                        model_name=cr.content_type.model,
                        object_id=str(cr.object_id),
                        description=f"Soft-deleted {cr.content_type.model} #{cr.object_id}",
                        ip_address=request.META.get('REMOTE_ADDR')
                    )
                elif cr.request_type == ChangeRequestType.EDIT:
                    for field, value in cr.after_data.items():
                        if hasattr(obj, field):
                            setattr(obj, field, value)
                    obj.save()
                    AuditLog.objects.create(
                        user=request.user, action='APPROVED_EDIT',
                        model_name=cr.content_type.model,
                        object_id=str(cr.object_id),
                        description=f"Applied edit to {cr.content_type.model} #{cr.object_id}",
                        ip_address=request.META.get('REMOTE_ADDR')
                    )
                messages.success(request, "Change approved and applied.")
            except Exception as e:
                messages.error(request, f"Change approved but failed to apply: {e}")

        elif action == 'reject':
            cr.status = ChangeRequestStatus.REJECTED
            cr.save()
            AuditLog.objects.create(
                user=request.user, action='REJECTED_CHANGE',
                model_name=cr.content_type.model,
                object_id=str(cr.object_id),
                description=f"Rejected {cr.request_type} request #{pk}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, "Change request rejected.")

        return redirect('change_request_list')

    return render(request, 'audit/change_request_review.html', {'cr': cr})


@admin_required
def audit_log(request):
    from django.core.paginator import Paginator
    from django.db.models import Q
    PER_PAGE_OPTS = [5, 25, 50, 100]
    q = request.GET.get('q', '').strip()
    per_page = int(request.GET.get('per_page', 25))
    if per_page not in PER_PAGE_OPTS:
        per_page = 25

    logs = AuditLog.objects.all().select_related('user').order_by('-created_at')

    if q:
        logs = logs.filter(
            Q(user__username__icontains=q) |
            Q(action__icontains=q) |
            Q(model_name__icontains=q) |
            Q(description__icontains=q)
        )

    paginator = Paginator(logs, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'audit/audit_log.html', {
        'page_obj': page_obj,
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
    })
