from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
from core.models import Role
from core.decorators import role_required, login_required_custom
from audit.models import AuditLog
from patients.models import Visit, Patient
from laboratory.models import LabRequest, LabRequestStatus
from .models import Payment, PaymentType, PaymentMethod, PaymentStatus


def consultation_fee_for_visit(visit):
    from core.models import HospitalSettings, SpecialistConsultationFee

    fee = HospitalSettings.get().consultation_fee
    specialist_label = None
    if visit.doctor and visit.doctor.specialty:
        specialist_fee = SpecialistConsultationFee.objects.filter(
            specialty=visit.doctor.specialty, is_active=True
        ).first()
        if specialist_fee:
            fee = specialist_fee.fee
            specialist_label = visit.doctor.get_specialty_display()
    return fee, specialist_label


@role_required('accountant', 'admin')
def payment_list(request):
    from django.core.paginator import Paginator
    from django.db.models import Q
    PER_PAGE_OPTS = [5, 25, 50, 100]
    q = request.GET.get('q', '').strip()
    per_page = int(request.GET.get('per_page', 25))
    if per_page not in PER_PAGE_OPTS:
        per_page = 25

    status_filter = request.GET.get('status', '')

    payments = Payment.objects.filter(is_deleted=False).select_related(
        'visit__patient', 'processed_by', 'revoked_by'
    ).order_by('-created_at')

    if status_filter in [s[0] for s in PaymentStatus.choices]:
        payments = payments.filter(status=status_filter)

    if q:
        payments = payments.filter(
            Q(receipt_number__icontains=q) |
            Q(visit__patient__full_name__icontains=q) |
            Q(visit__patient__patient_id__icontains=q)
        )

    paginator = Paginator(payments, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'billing/payment_list.html', {
        'page_obj': page_obj,
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
        'status_filter': status_filter,
        'status_choices': PaymentStatus.choices,
    })


@role_required('accountant', 'admin')
def payment_create(request, visit_pk):
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    consultation_fee, specialist_label = consultation_fee_for_visit(visit)

    if request.method == 'POST':
        data = request.POST
        try:
            payment_type = data.get('payment_type')
            if payment_type == PaymentType.CONSULTATION:
                if Payment.objects.filter(
                    visit=visit, payment_type__in=[PaymentType.CONSULTATION, PaymentType.COMBINED],
                    status=PaymentStatus.PAID, is_deleted=False
                ).exists():
                    messages.error(request, "This visit's consultation has already been paid.")
                    return redirect('payment_create', visit_pk=visit_pk)
                raw_total = str(consultation_fee)
            else:
                raw_total = data.get('total_amount') or data.get('total_amount_manual', '0')
            raw_total = str(raw_total).replace(',', '').strip() or '0'
            total = Decimal(raw_total)

            insurance = visit.patient.insurance
            if insurance:
                patient_pct = (Decimal('100') - Decimal(str(insurance.coverage_percentage))) / Decimal('100')
                patient_pays = total * patient_pct
                insurance_covered = total - patient_pays
            else:
                patient_pays = total
                insurance_covered = Decimal('0')

            raw_paid = str(data.get('amount_paid', '') or '').replace(',', '').strip()
            amount_paid = Decimal(raw_paid) if raw_paid else patient_pays

            payment = Payment(
                visit=visit,
                payment_type=payment_type,
                payment_method=data['payment_method'],
                total_amount=total,
                patient_pays=patient_pays,
                insurance_covered=insurance_covered,
                amount_paid=amount_paid,
                status=PaymentStatus.PAID,
                notes=data.get('notes', ''),
                processed_by=request.user
            )
            with transaction.atomic():
                payment.save()

            AuditLog.objects.create(
                user=request.user, action='CREATE_PAYMENT', model_name='Payment',
                object_id=str(payment.id),
                description=f"Payment {payment.receipt_number} confirmed for visit {visit_pk}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Payment confirmed. Receipt: {payment.receipt_number}")
            return redirect('payment_receipt', pk=payment.pk)
        except Exception as e:
            messages.error(request, f"Error: {e}")

    ctx = {
        'visit': visit,
        'payment_types': PaymentType.choices,
        'payment_methods': PaymentMethod.choices,
        'consultation_fee': consultation_fee,
        'specialist_label': specialist_label,
    }
    return render(request, 'billing/payment_form.html', ctx)


@login_required_custom
def payment_receipt(request, pk):
    payment = get_object_or_404(Payment, pk=pk, is_deleted=False)
    user = request.user
    # Only accountants, admin, and the patient's doctor can see receipts
    if user.role not in [Role.ACCOUNTANT, Role.ADMIN]:
        if user.role == Role.DOCTOR and payment.visit.doctor != user:
            messages.error(request, "Access denied.")
            return redirect('dashboard')
    from core.models import HospitalSettings
    hs = HospitalSettings.get()

    # For combined payments, build structured line items for the receipt
    combined_line_items = []
    if payment.payment_type == PaymentType.COMBINED:
        from decimal import Decimal
        notes_parts = [p.strip() for p in payment.notes.split(' | ')] if payment.notes else []

        # Build a lookup of lab test prices from the visit for old-format fallback
        lab_price_lookup = {}
        try:
            visit_labs = LabRequest.objects.filter(
                visit=payment.visit, is_deleted=False
            ).select_related('lab_test')
            for lr in visit_labs:
                price = lr.lab_test.default_price if lr.lab_test and lr.lab_test.default_price else None
                lab_price_lookup[lr.test_name.strip().lower()] = price
        except Exception:
            pass

        for part in notes_parts:
            # ── New structured format ──────────────────────────────────────
            if part.startswith('CONSULT::'):
                segments = part.split('::')
                try:
                    combined_line_items.append({
                        'label': 'Consultation Fee',
                        'detail': '',
                        'amount': float(segments[1].replace(',', '')),
                    })
                except (IndexError, ValueError):
                    combined_line_items.append({'label': 'Consultation Fee', 'detail': '', 'amount': None})

            elif part.startswith('LAB::'):
                segments = part.split('::')
                name = segments[1].strip() if len(segments) > 1 else 'Lab Test'
                try:
                    amount = float(segments[2].replace(',', '')) if len(segments) > 2 else None
                except (ValueError, AttributeError):
                    amount = None
                combined_line_items.append({'label': name, 'detail': 'Lab Test', 'amount': amount})

            # ── Legacy format (old receipts) ───────────────────────────────
            elif part.startswith('Consultation:'):
                amount_str = part.replace('Consultation:', '').strip().replace(',', '')
                try:
                    combined_line_items.append({
                        'label': 'Consultation Fee',
                        'detail': '',
                        'amount': float(amount_str),
                    })
                except ValueError:
                    combined_line_items.append({'label': 'Consultation Fee', 'detail': '', 'amount': None})

            elif part.startswith('Lab tests:'):
                names = part.replace('Lab tests:', '').strip()
                for name in [n.strip() for n in names.split(',') if n.strip()]:
                    # Try to look up the price from the visit's lab requests
                    amount = lab_price_lookup.get(name.lower())
                    amount = float(amount) if amount is not None else None
                    combined_line_items.append({'label': name, 'detail': 'Lab Test', 'amount': amount})

        # Supplies — always from linked records for full qty/price detail
        supplies = payment.billed_consumables.select_related('consumable').all()
        for s in supplies:
            subtotal = Decimal(str(s.quantity)) * Decimal(str(s.unit_price))
            combined_line_items.append({
                'label': s.consumable.name,
                'detail': f'{s.quantity} × {s.unit_price:,g} {hs.currency}',
                'amount': float(subtotal),
            })

    patient_copy_items = []
    if payment.payment_type == PaymentType.COMBINED:
        category_totals = {'Consultation': Decimal('0'), 'Labs': Decimal('0'), 'Supplies': Decimal('0')}
        for item in combined_line_items:
            if item['label'] == 'Consultation Fee':
                category = 'Consultation'
            elif item.get('detail') == 'Lab Test':
                category = 'Labs'
            else:
                category = 'Supplies'
            if item.get('amount') is not None:
                category_totals[category] += Decimal(str(item['amount']))
        patient_copy_items = [
            {'label': label, 'amount': amount}
            for label, amount in category_totals.items()
            if amount
        ]
    else:
        type_labels = {
            PaymentType.CONSULTATION: 'Consultation',
            PaymentType.LAB: 'Labs',
            PaymentType.SUPPLIES: 'Supplies',
        }
        label = type_labels.get(payment.payment_type, payment.get_payment_type_display())
        patient_copy_items = [{'label': label, 'amount': payment.total_amount}]

    return render(request, 'billing/receipt.html', {
        'payment': payment,
        'hospital_settings': hs,
        'currency': hs.currency,
        'combined_line_items': combined_line_items,
        'patient_copy_items': patient_copy_items,
    })


@role_required('accountant', 'admin')
def billing_dashboard(request):
    from decimal import Decimal
    from django.utils import timezone
    from django.db.models import Exists, OuterRef
    from patients.models import VisitStatus
    payments = Payment.objects.filter(is_deleted=False)
    total_revenue = sum(p.amount_paid for p in payments.filter(status=PaymentStatus.PAID))
    pending_count = payments.filter(status=PaymentStatus.PENDING).count()
    today_revenue = sum(
        p.amount_paid for p in payments.filter(
            status=PaymentStatus.PAID, created_at__date=timezone.now().date()
        )
    )
    # Visits that don't yet have a paid consultation payment (or combined payment)
    paid_consult = Payment.objects.filter(
        visit=OuterRef('pk'),
        payment_type__in=[PaymentType.CONSULTATION, PaymentType.COMBINED],
        status=PaymentStatus.PAID, is_deleted=False
    )
    visits_awaiting_payment = Visit.objects.filter(
        is_deleted=False, status=VisitStatus.PENDING
    ).exclude(Exists(paid_consult)).select_related('patient', 'doctor').order_by('-created_at')[:15]

    ctx = {
        'total_revenue': total_revenue,
        'pending_count': pending_count,
        'today_revenue': today_revenue,
        'recent_payments': payments.order_by('-created_at')[:20],
        'visits_awaiting_payment': visits_awaiting_payment,
    }
    return render(request, 'billing/dashboard.html', ctx)


@role_required('accountant', 'admin')
def payment_revoke(request, pk):
    from django.utils import timezone
    payment = get_object_or_404(Payment, pk=pk, is_deleted=False)
    if payment.status != PaymentStatus.PAID:
        messages.error(request, "Only paid payments can be revoked.")
        return redirect('payment_list')
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        action = request.POST.get('revoke_action', '')
        if not reason:
            messages.error(request, "A reason is required.")
            return render(request, 'billing/payment_revoke.html', {'payment': payment})
        if action not in ('delete', 'return_to_queue'):
            messages.error(request, "Please choose what to do with this payment.")
            return render(request, 'billing/payment_revoke.html', {'payment': payment})

        payment.revoked_by = request.user
        payment.revoked_at = timezone.now()
        payment.revoke_reason = reason

        if action == 'delete':
            payment.status = PaymentStatus.REVOKED
            payment.is_deleted = True
            payment.save()
            AuditLog.objects.create(
                user=request.user, action='REVOKE_DELETE_PAYMENT', model_name='Payment',
                object_id=str(payment.id),
                description=f"Payment {payment.receipt_number} revoked and deleted by {request.user.get_full_name()}. Reason: {reason}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Payment {payment.receipt_number} has been revoked and permanently removed.")
        else:
            payment.status = PaymentStatus.PENDING
            payment.amount_paid = 0
            payment.save()
            # If this was a lab payment, revert associated lab requests back to REQUESTED
            # so they re-appear in the lab billing queue.
            # We revert any status except CANCELLED — lab results (LabResult model) are
            # stored separately so reverting the request status loses no result data.
            if payment.payment_type == PaymentType.LAB:
                reverted = LabRequest.objects.filter(
                    visit=payment.visit,
                    is_deleted=False,
                ).exclude(
                    status=LabRequestStatus.CANCELLED
                ).update(status=LabRequestStatus.REQUESTED)
            else:
                reverted = 0
            AuditLog.objects.create(
                user=request.user, action='REVOKE_RETURN_PAYMENT', model_name='Payment',
                object_id=str(payment.id),
                description=f"Payment {payment.receipt_number} revoked and returned to pending queue by {request.user.get_full_name()}. Reason: {reason}"
                            + (f" ({reverted} lab request(s) returned to billing queue)" if reverted else ""),
                ip_address=request.META.get('REMOTE_ADDR')
            )
            msg = f"Payment {payment.receipt_number} returned to the pending queue."
            if reverted:
                msg += f" {reverted} lab test(s) returned to the lab billing queue."
            messages.success(request, msg)

        return redirect('payment_list')
    return render(request, 'billing/payment_revoke.html', {'payment': payment})


@role_required('admin')
def revoked_payments_admin(request):
    from django.db.models import Q
    from django.core.paginator import Paginator

    q = request.GET.get('q', '').strip()
    tab = request.GET.get('tab', 'revoked')  # 'revoked' | 'deleted'

    if tab == 'deleted':
        payments = Payment.objects.filter(
            is_deleted=True
        ).select_related('visit__patient', 'processed_by', 'revoked_by').order_by('-revoked_at', '-updated_at')
    else:
        payments = Payment.objects.filter(
            status=PaymentStatus.REVOKED, is_deleted=False
        ).select_related('visit__patient', 'processed_by', 'revoked_by').order_by('-revoked_at')

    if q:
        payments = payments.filter(
            Q(receipt_number__icontains=q) |
            Q(visit__patient__full_name__icontains=q) |
            Q(visit__patient__patient_id__icontains=q)
        )

    revoked_count = Payment.objects.filter(status=PaymentStatus.REVOKED, is_deleted=False).count()
    deleted_count = Payment.objects.filter(is_deleted=True).count()

    paginator = Paginator(payments, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'billing/revoked_payments_admin.html', {
        'page_obj': page_obj,
        'q': q,
        'tab': tab,
        'revoked_count': revoked_count,
        'deleted_count': deleted_count,
    })


@role_required('accountant', 'admin')
def supplies_billing_list(request):
    """Visits with at least one unbilled consumable."""
    from core.models import VisitConsumable
    from django.db.models import Sum, Count

    visit_ids = VisitConsumable.objects.filter(
        is_billed=False
    ).values_list('visit_id', flat=True).distinct()

    visits = Visit.objects.filter(
        pk__in=visit_ids, is_deleted=False
    ).select_related('patient').order_by('-created_at')

    for v in visits:
        items = VisitConsumable.objects.filter(visit=v, is_billed=False).select_related('consumable')
        v.unbilled_items = items
        v.unbilled_count = len(items)
        from decimal import Decimal
        v.estimated_total = sum(
            Decimal(str(i.quantity)) * Decimal(str(i.unit_price)) for i in items
        )

    return render(request, 'billing/supplies_billing.html', {'visits': visits})


@role_required('accountant', 'admin')
def supplies_billing_visit(request, visit_pk):
    """Show unbilled consumables for a visit, ready to process payment."""
    from core.models import VisitConsumable
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    unbilled = VisitConsumable.objects.filter(
        visit=visit, is_billed=False
    ).select_related('consumable', 'administered_by').order_by('created_at')

    if not unbilled.exists():
        messages.info(request, "No unbilled supplies for this patient.")
        return redirect('supplies_billing_list')

    from core.models import HospitalSettings
    try:
        hs = HospitalSettings.objects.first()
        currency = hs.currency if hs else 'RWF'
    except Exception:
        currency = 'RWF'

    return render(request, 'billing/supplies_billing_visit.html', {
        'visit': visit,
        'unbilled': unbilled,
        'payment_methods': PaymentMethod.choices,
        'currency': currency,
    })


@role_required('accountant', 'admin')
def supplies_bulk_payment_create(request, visit_pk):
    """POST: create one payment for selected consumables and mark them billed."""
    from core.models import VisitConsumable
    from decimal import Decimal
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    if request.method != 'POST':
        return redirect('supplies_billing_visit', visit_pk=visit_pk)

    selected_ids = request.POST.getlist('item_ids')
    if not selected_ids:
        messages.error(request, "Please select at least one item to bill.")
        return redirect('supplies_billing_visit', visit_pk=visit_pk)

    items = list(VisitConsumable.objects.filter(
        pk__in=selected_ids, visit=visit, is_billed=False
    ).select_related('consumable'))

    if not items:
        messages.error(request, "No valid items found.")
        return redirect('supplies_billing_visit', visit_pk=visit_pk)

    try:
        total = Decimal('0')
        for item in items:
            raw = str(request.POST.get(f'amount_{item.pk}', '') or '').replace(',', '').strip()
            if raw:
                total += Decimal(raw)
            else:
                total += Decimal(str(item.quantity)) * Decimal(str(item.unit_price))

        insurance = visit.patient.insurance
        if insurance:
            patient_pct = (Decimal('100') - Decimal(str(insurance.coverage_percentage))) / Decimal('100')
            patient_pays = total * patient_pct
            insurance_covered = total - patient_pays
        else:
            patient_pays = total
            insurance_covered = Decimal('0')

        raw_paid = str(request.POST.get('amount_paid', '') or '').replace(',', '').strip()
        amount_paid = Decimal(raw_paid) if raw_paid else patient_pays

        payment = Payment(
            visit=visit,
            payment_type=PaymentType.SUPPLIES,
            payment_method=request.POST.get('payment_method', PaymentMethod.CASH),
            total_amount=total,
            patient_pays=patient_pays,
            insurance_covered=insurance_covered,
            amount_paid=amount_paid,
            status=PaymentStatus.PAID,
            notes=request.POST.get('notes', ''),
            processed_by=request.user,
        )
        payment.save()

        item_ids = [i.pk for i in items]
        VisitConsumable.objects.filter(pk__in=item_ids).update(is_billed=True, billed_payment=payment)

        item_names = ', '.join(f"{i.consumable.name} x{i.quantity}" for i in items)
        AuditLog.objects.create(
            user=request.user, action='CREATE_SUPPLIES_PAYMENT', model_name='Payment',
            object_id=str(payment.id),
            description=f"Supplies payment {payment.receipt_number} for: {item_names} (visit {visit_pk})",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, f"{len(items)} item(s) billed. Receipt: {payment.receipt_number}")
        return redirect('payment_receipt', pk=payment.pk)
    except Exception as e:
        messages.error(request, f"Error: {e}")
        return redirect('supplies_billing_visit', visit_pk=visit_pk)


@role_required('accountant', 'admin')
def lab_billing_list(request):
    """Step 1 — list of patients/visits that have at least one unpaid lab request."""
    from django.db.models import Prefetch, Q
    pending_qs = LabRequest.objects.filter(
        status=LabRequestStatus.REQUESTED, is_deleted=False
    ).select_related('lab_test')

    visits = Visit.objects.filter(
        is_deleted=False,
        lab_requests__status=LabRequestStatus.REQUESTED,
        lab_requests__is_deleted=False,
    ).distinct().select_related('patient').prefetch_related(
        Prefetch('lab_requests', queryset=pending_qs, to_attr='pending_labs')
    ).order_by('-created_at')

    for v in visits:
        v.pending_count = len(v.pending_labs)
        v.estimated_total = sum(
            (lab.lab_test.default_price if lab.lab_test else Decimal('0'))
            for lab in v.pending_labs
        )

    return render(request, 'billing/lab_billing.html', {'visits': visits})


@role_required('accountant', 'admin')
def lab_billing_visit(request, visit_pk):
    """Step 2 — show all pending labs for a visit; accountant selects which to bill."""
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    pending_labs = LabRequest.objects.filter(
        visit=visit, status=LabRequestStatus.REQUESTED, is_deleted=False
    ).select_related('lab_test__category', 'requested_by').order_by('created_at')

    if not pending_labs.exists():
        messages.info(request, "No pending lab tests for this patient.")
        return redirect('lab_billing_list')

    return render(request, 'billing/lab_billing_visit.html', {
        'visit': visit,
        'pending_labs': pending_labs,
        'payment_methods': PaymentMethod.choices,
    })


@role_required('accountant', 'admin')
def lab_bulk_payment_create(request, visit_pk):
    """Step 3 — POST: create one payment for selected labs and mark them PAID."""
    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    if request.method != 'POST':
        return redirect('lab_billing_visit', visit_pk=visit_pk)

    selected_ids = request.POST.getlist('lab_ids')
    if not selected_ids:
        messages.error(request, "Please select at least one lab test to bill.")
        return redirect('lab_billing_visit', visit_pk=visit_pk)

    labs = list(LabRequest.objects.filter(
        pk__in=selected_ids, visit=visit,
        status=LabRequestStatus.REQUESTED, is_deleted=False
    ).select_related('lab_test'))

    if not labs:
        messages.error(request, "No valid lab tests found.")
        return redirect('lab_billing_visit', visit_pk=visit_pk)

    try:
        # Sum amounts: use per-lab price overrides from POST, else default_price
        total = Decimal('0')
        for lab in labs:
            raw = str(request.POST.get(f'amount_{lab.pk}', '') or '').replace(',', '').strip()
            if raw:
                total += Decimal(raw)
            elif lab.lab_test and lab.lab_test.default_price:
                total += lab.lab_test.default_price

        insurance = visit.patient.insurance
        if insurance:
            patient_pct = (Decimal('100') - Decimal(str(insurance.coverage_percentage))) / Decimal('100')
            patient_pays = total * patient_pct
            insurance_covered = total - patient_pays
        else:
            patient_pays = total
            insurance_covered = Decimal('0')

        raw_paid = str(request.POST.get('amount_paid', '') or '').replace(',', '').strip()
        amount_paid = Decimal(raw_paid) if raw_paid else patient_pays

        payment = Payment(
            visit=visit,
            payment_type=PaymentType.LAB,
            payment_method=request.POST.get('payment_method', PaymentMethod.CASH),
            total_amount=total,
            patient_pays=patient_pays,
            insurance_covered=insurance_covered,
            amount_paid=amount_paid,
            status=PaymentStatus.PAID,
            notes=request.POST.get('notes', ''),
            processed_by=request.user
        )
        payment.save()

        # Mark selected labs as PAID
        lab_ids = [lab.pk for lab in labs]
        LabRequest.objects.filter(pk__in=lab_ids).update(status=LabRequestStatus.PAID)

        lab_names = ', '.join(lab.test_name for lab in labs)
        AuditLog.objects.create(
            user=request.user, action='CREATE_LAB_BULK_PAYMENT', model_name='Payment',
            object_id=str(payment.id),
            description=f"Lab payment {payment.receipt_number} for: {lab_names} (visit {visit_pk})",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, f"{len(labs)} lab test(s) billed. Receipt: {payment.receipt_number}")
        return redirect('payment_receipt', pk=payment.pk)
    except Exception as e:
        messages.error(request, f"Error: {e}")
        return redirect('lab_billing_visit', visit_pk=visit_pk)


# ─── PENDING BILLING — unified patient view ──────────────────────────────────

@role_required('accountant', 'admin')
def pending_billing_list(request):
    from django.core.paginator import Paginator
    from django.db.models import Q, Exists, OuterRef
    from patients.models import Visit, VisitStatus
    from laboratory.models import LabRequest, LabRequestStatus
    from core.models import VisitConsumable, HospitalSettings

    PER_PAGE_OPTS = [10, 25, 50]
    per_page = int(request.GET.get('per_page', 25))
    if per_page not in PER_PAGE_OPTS:
        per_page = 25
    q = request.GET.get('q', '').strip()

    paid_consult_sq = Payment.objects.filter(
        visit=OuterRef('pk'), payment_type__in=[PaymentType.CONSULTATION, PaymentType.COMBINED],
        status=PaymentStatus.PAID, is_deleted=False
    )
    unpaid_labs_sq = LabRequest.objects.filter(
        visit=OuterRef('pk'), is_deleted=False, status=LabRequestStatus.REQUESTED
    )
    unbilled_supplies_sq = VisitConsumable.objects.filter(
        visit=OuterRef('pk'), is_billed=False
    )

    visits = Visit.objects.filter(
        is_deleted=False,
        status__in=[VisitStatus.PENDING, VisitStatus.IN_PROGRESS]
    ).filter(
        ~Exists(paid_consult_sq) | Exists(unpaid_labs_sq) | Exists(unbilled_supplies_sq)
    ).annotate(
        has_paid_consult=Exists(paid_consult_sq),
        has_unpaid_labs=Exists(unpaid_labs_sq),
        has_unbilled_supplies=Exists(unbilled_supplies_sq),
    ).select_related('patient', 'doctor').order_by('-created_at')

    if q:
        visits = visits.filter(
            Q(patient__full_name__icontains=q) | Q(patient__patient_id__icontains=q)
        )

    paginator = Paginator(visits, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)

    settings = HospitalSettings.get()
    return render(request, 'billing/pending_billing_list.html', {
        'page_obj': page_obj,
        'q': q,
        'per_page': per_page,
        'per_page_options': PER_PAGE_OPTS,
        'base_qs': params.urlencode(),
        'currency': settings.currency,
    })


@role_required('accountant', 'admin')
def pending_billing_visit(request, visit_pk):
    from patients.models import Visit, VisitStatus
    from laboratory.models import LabRequest, LabRequestStatus
    from core.models import VisitConsumable, HospitalSettings, SpecialistConsultationFee

    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)

    paid_consultation = Payment.objects.filter(
        visit=visit,
        payment_type__in=[PaymentType.CONSULTATION, PaymentType.COMBINED],
        status=PaymentStatus.PAID, is_deleted=False
    ).exists()

    unpaid_labs = LabRequest.objects.filter(
        visit=visit, is_deleted=False, status=LabRequestStatus.REQUESTED
    ).select_related('lab_test')

    unbilled_supplies = VisitConsumable.objects.filter(
        visit=visit, is_billed=False
    ).select_related('consumable')

    unbilled_supplies_total = sum(s.total_price for s in unbilled_supplies)

    other_pending = Payment.objects.filter(
        visit=visit, status=PaymentStatus.PENDING, is_deleted=False
    ).exclude(payment_type__in=[PaymentType.CONSULTATION, PaymentType.COMBINED])

    hs = HospitalSettings.get()
    consultation_fee, specialist_label = consultation_fee_for_visit(visit)

    return render(request, 'billing/pending_billing_visit.html', {
        'visit': visit,
        'paid_consultation': paid_consultation,
        'unpaid_labs': unpaid_labs,
        'unbilled_supplies': unbilled_supplies,
        'unbilled_supplies_total': unbilled_supplies_total,
        'other_pending': other_pending,
        'currency': hs.currency,
        'consultation_fee': consultation_fee,
        'specialist_label': specialist_label,
        'payment_methods': PaymentMethod.choices,
    })


@role_required('accountant', 'admin')
def combined_payment_create(request, visit_pk):
    """POST: pay consultation + selected labs + selected supplies in one transaction."""
    from core.models import VisitConsumable
    from decimal import Decimal

    visit = get_object_or_404(Visit, pk=visit_pk, is_deleted=False)
    if request.method != 'POST':
        return redirect('pending_billing_visit', visit_pk=visit_pk)

    try:
        payment_method = request.POST.get('payment_method', PaymentMethod.CASH)
        extra_notes = request.POST.get('notes', '').strip()
        total = Decimal('0')
        description_parts = []

        # --- Consultation ---
        include_consult = request.POST.get('include_consultation') == '1'
        if include_consult:
            if Payment.objects.filter(
                visit=visit, payment_type__in=[PaymentType.CONSULTATION, PaymentType.COMBINED],
                status=PaymentStatus.PAID, is_deleted=False
            ).exists():
                messages.error(request, "This visit's consultation has already been paid.")
                return redirect('pending_billing_visit', visit_pk=visit_pk)
            consult_amt, _ = consultation_fee_for_visit(visit)
            total += consult_amt
            description_parts.append(f"CONSULT::{consult_amt:.0f}")

        # --- Lab tests ---
        selected_lab_ids = request.POST.getlist('lab_ids')
        labs_to_pay = []
        if selected_lab_ids:
            labs_to_pay = list(LabRequest.objects.filter(
                pk__in=selected_lab_ids, visit=visit,
                status=LabRequestStatus.REQUESTED, is_deleted=False
            ).select_related('lab_test'))
            for lab in labs_to_pay:
                raw = str(request.POST.get(f'lab_amount_{lab.pk}', '') or '').replace(',', '').strip()
                if raw:
                    lab_amt = Decimal(raw)
                elif lab.lab_test and lab.lab_test.default_price:
                    lab_amt = lab.lab_test.default_price
                else:
                    lab_amt = Decimal('0')
                total += lab_amt
                description_parts.append(f"LAB::{lab.test_name}::{lab_amt:.0f}")

        # --- Supplies ---
        selected_supply_ids = request.POST.getlist('supply_ids')
        supplies_to_pay = []
        if selected_supply_ids:
            supplies_to_pay = list(VisitConsumable.objects.filter(
                pk__in=selected_supply_ids, visit=visit, is_billed=False
            ).select_related('consumable'))
            for s in supplies_to_pay:
                raw = str(request.POST.get(f'supply_amount_{s.pk}', '') or '').replace(',', '').strip()
                if raw:
                    total += Decimal(raw)
                else:
                    total += Decimal(str(s.quantity)) * Decimal(str(s.unit_price))
            if supplies_to_pay:
                description_parts.append(f"Supplies: {', '.join(s.consumable.name for s in supplies_to_pay)}")

        if total <= 0:
            messages.error(request, "No items selected or total amount is zero.")
            return redirect('pending_billing_visit', visit_pk=visit_pk)

        insurance = visit.patient.insurance
        if insurance:
            patient_pct = (Decimal('100') - Decimal(str(insurance.coverage_percentage))) / Decimal('100')
            patient_pays = total * patient_pct
            insurance_covered = total - patient_pays
        else:
            patient_pays = total
            insurance_covered = Decimal('0')

        raw_paid = str(request.POST.get('amount_paid', '') or '').replace(',', '').strip()
        amount_paid = Decimal(raw_paid) if raw_paid else patient_pays

        combined_notes = ' | '.join(description_parts)
        if extra_notes:
            combined_notes = f"{combined_notes} | {extra_notes}"

        payment = Payment(
            visit=visit,
            payment_type=PaymentType.COMBINED,
            payment_method=payment_method,
            total_amount=total,
            patient_pays=patient_pays,
            insurance_covered=insurance_covered,
            amount_paid=amount_paid,
            status=PaymentStatus.PAID,
            notes=combined_notes,
            processed_by=request.user,
        )
        with transaction.atomic():
            payment.save()

            if labs_to_pay:
                LabRequest.objects.filter(pk__in=[l.pk for l in labs_to_pay]).update(
                    status=LabRequestStatus.PAID
                )

            if supplies_to_pay:
                VisitConsumable.objects.filter(pk__in=[s.pk for s in supplies_to_pay]).update(
                    is_billed=True, billed_payment=payment
                )

        AuditLog.objects.create(
            user=request.user, action='CREATE_COMBINED_PAYMENT', model_name='Payment',
            object_id=str(payment.id),
            description=f"Combined payment {payment.receipt_number}: {combined_notes} (visit {visit_pk})",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        item_count = (1 if include_consult else 0) + len(labs_to_pay) + len(supplies_to_pay)
        messages.success(request, f"Combined payment confirmed — {item_count} item(s) billed. Receipt: {payment.receipt_number}")
        return redirect('payment_receipt', pk=payment.pk)

    except Exception as e:
        messages.error(request, f"Error: {e}")
        return redirect('pending_billing_visit', visit_pk=visit_pk)
