from django.db import models
from core.models import User, Insurance


class Gender(models.TextChoices):
    MALE = 'M', 'Male'
    FEMALE = 'F', 'Female'
    OTHER = 'O', 'Other'


class Patient(models.Model):
    patient_id = models.CharField(max_length=20, unique=True, editable=False)
    full_name = models.CharField(max_length=200)
    age = models.PositiveIntegerField()
    gender = models.CharField(max_length=1, choices=Gender.choices)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    insurance = models.ForeignKey(Insurance, null=True, blank=True, on_delete=models.SET_NULL)
    registered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='registered_patients')
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.patient_id:
            import datetime
            year = datetime.date.today().year
            count = Patient.objects.filter(created_at__year=year).count() + 1
            self.patient_id = f"HMS-{year}-{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient_id} - {self.full_name}"

    class Meta:
        ordering = ['-created_at']


class VisitStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    IN_PROGRESS = 'in_progress', 'In Progress'
    COMPLETED = 'completed', 'Completed'


class Visit(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='visits')
    doctor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assigned_visits',
                                limit_choices_to={'role': 'doctor'})
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_visits')
    status = models.CharField(max_length=20, choices=VisitStatus.choices, default=VisitStatus.PENDING)
    needs_triage = models.BooleanField(default=True, help_text="If True, patient must be seen by a nurse before the doctor.")
    notes = models.TextField(blank=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Visit: {self.patient} → Dr. {self.doctor}"

    class Meta:
        ordering = ['-created_at']
