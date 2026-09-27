from django.db import models
from core.models import User
from patients.models import Visit


class Triage(models.Model):
    visit = models.OneToOneField(Visit, on_delete=models.CASCADE, related_name='triage')
    temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="°C")
    blood_pressure = models.CharField(max_length=20, blank=True, help_text="e.g. 120/80")
    pulse_rate = models.PositiveIntegerField(null=True, blank=True, help_text="bpm")
    respiratory_rate = models.PositiveIntegerField(null=True, blank=True, help_text="breaths/min")
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="kg")
    height = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="cm")
    oxygen_saturation = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="%")
    chief_complaint = models.TextField()
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='triages_recorded')
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Triage for {self.visit}"


class Consultation(models.Model):
    visit = models.OneToOneField(Visit, on_delete=models.CASCADE, related_name='consultation')
    presenting_complaint = models.TextField(blank=True)
    history = models.TextField(blank=True)          # History of Present Illness
    past_history = models.TextField(blank=True)     # Past Medical / Family / Social History
    examination_findings = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    treatment_plan = models.TextField(blank=True)
    prescription = models.TextField(blank=True)
    follow_up_notes = models.TextField(blank=True)
    admit_patient = models.BooleanField(default=False)
    discharge_patient = models.BooleanField(default=False)
    doctor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='consultations')
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Consultation: {self.visit}"
