from django.db import models
from core.models import User
from patients.models import Visit


class LabRequestStatus(models.TextChoices):
    REQUESTED = 'requested', 'Requested'
    PAID = 'paid', 'Payment Confirmed'
    IN_PROGRESS = 'in_progress', 'In Progress'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'


class LabTestCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'Lab test categories'

    def __str__(self):
        return self.name


class LabTest(models.Model):
    category = models.ForeignKey(LabTestCategory, on_delete=models.CASCADE, related_name='tests')
    name = models.CharField(max_length=200)
    default_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category__order', 'category__name', 'name']
        unique_together = [('category', 'name')]

    def __str__(self):
        return f"{self.name} ({self.category.name})"


class LabTestParameter(models.Model):
    """A sub-component of a lab test (e.g. Hemoglobin, WBC within a Full Blood Count panel)."""
    lab_test = models.ForeignKey(LabTest, on_delete=models.CASCADE, related_name='parameters')
    name = models.CharField(max_length=150)
    unit = models.CharField(max_length=30, blank=True)
    reference_range = models.CharField(max_length=100, blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'name']
        unique_together = [('lab_test', 'name')]

    def __str__(self):
        return f"{self.name} ({self.lab_test.name})"


class LabRequest(models.Model):
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='lab_requests')
    lab_test = models.ForeignKey(LabTest, on_delete=models.SET_NULL, null=True, blank=True, related_name='requests')
    test_name = models.CharField(max_length=200)
    test_description = models.TextField(blank=True)
    urgency = models.CharField(max_length=20, choices=[
        ('routine', 'Routine'), ('urgent', 'Urgent'), ('stat', 'STAT')
    ], default='routine')
    status = models.CharField(max_length=20, choices=LabRequestStatus.choices, default=LabRequestStatus.REQUESTED)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lab_requests_made')
    selected_parameters = models.ManyToManyField(LabTestParameter, blank=True, related_name='requests')
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.test_name} - {self.visit.patient}"


class LabResult(models.Model):
    lab_request = models.OneToOneField(LabRequest, on_delete=models.CASCADE, related_name='result')
    result_text = models.TextField()
    result_file = models.FileField(upload_to='lab_results/', null=True, blank=True)
    reference_range = models.TextField(blank=True)
    interpretation = models.TextField(blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='lab_results_performed')
    reviewed_by_doctor = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Result: {self.lab_request}"


class LabResultValue(models.Model):
    """Structured value for a single parameter within a lab result (e.g. Hemoglobin = 13.5 g/dL)."""
    result = models.ForeignKey(LabResult, on_delete=models.CASCADE, related_name='values')
    parameter = models.ForeignKey(LabTestParameter, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=100, blank=True)
    is_abnormal = models.BooleanField(default=False)

    class Meta:
        ordering = ['parameter__order', 'parameter__name']
        unique_together = [('result', 'parameter')]

    def __str__(self):
        return f"{self.parameter.name}: {self.value}"
