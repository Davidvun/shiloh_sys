from django.db import models
from core.models import User
from patients.models import Visit


class AdmissionStatus(models.TextChoices):
    ADMITTED = 'admitted', 'Admitted'
    DISCHARGED = 'discharged', 'Discharged'
    TRANSFERRED = 'transferred', 'Transferred'


class Admission(models.Model):
    visit = models.OneToOneField(Visit, on_delete=models.CASCADE, related_name='admission')
    ward = models.CharField(max_length=100)
    bed_number = models.CharField(max_length=20)
    admission_date = models.DateTimeField(auto_now_add=True)
    discharge_date = models.DateTimeField(null=True, blank=True)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=AdmissionStatus.choices, default=AdmissionStatus.ADMITTED)
    admission_notes = models.TextField(blank=True)
    discharge_notes = models.TextField(blank=True)
    admitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='admissions_created')
    discharged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='admissions_discharged')
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def days_admitted(self):
        from django.utils import timezone
        end = self.discharge_date or timezone.now()
        delta = end - self.admission_date
        return delta.days or 1

    def total_admission_cost(self):
        return self.daily_rate * self.days_admitted()

    def __str__(self):
        return f"Admission: {self.visit.patient} - Ward {self.ward} Bed {self.bed_number}"
