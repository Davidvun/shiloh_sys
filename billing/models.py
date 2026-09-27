from django.db import models
from django.db.models import Sum
from core.models import User, Insurance
from patients.models import Visit


class PaymentType(models.TextChoices):
    CONSULTATION = 'consultation', 'Consultation'
    LAB = 'lab', 'Lab Test'
    ADMISSION = 'admission', 'Admission'
    FINAL = 'final', 'Final / Discharge'
    SUPPLIES = 'supplies', 'Supplies & Medication'
    COMBINED = 'combined', 'Combined Payment'
    OTHER = 'other', 'Other'


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PAID = 'paid', 'Paid'
    PARTIAL = 'partial', 'Partial'
    WAIVED = 'waived', 'Waived'
    REVOKED = 'revoked', 'Revoked'


class PaymentMethod(models.TextChoices):
    CASH = 'cash', 'Cash'
    MOBILE_MONEY = 'mobile_money', 'Mobile Money'
    INSURANCE = 'insurance', 'Insurance'
    BANK = 'bank', 'Bank Transfer'


class Payment(models.Model):
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='payments')
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    insurance_covered = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    patient_pays = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    receipt_number = models.CharField(max_length=30, unique=True, blank=True)
    notes = models.TextField(blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='processed_payments')
    revoked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='revoked_payments')
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.TextField(blank=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            import datetime, random, string
            ts = datetime.datetime.now().strftime('%Y%m%d%H%M')
            rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            self.receipt_number = f"RCP-{ts}-{rand}"

        from decimal import Decimal
        # Safely convert to Decimal regardless of input type (str, float, int, Decimal)
        raw = str(self.total_amount).replace(',', '').strip() or '0'
        total = Decimal(raw)
        insurance = self.visit.patient.insurance
        if insurance:
            patient_pct = (Decimal('100') - Decimal(str(insurance.coverage_percentage))) / Decimal('100')
            self.patient_pays = total * patient_pct
            self.insurance_covered = total - self.patient_pays
        else:
            self.patient_pays = total
            self.insurance_covered = Decimal('0')
        self.total_amount = total

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.receipt_number} - {self.payment_type} ({self.status})"

    class Meta:
        ordering = ['-created_at']
