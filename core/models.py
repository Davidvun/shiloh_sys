from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMIN = 'admin', 'Admin'
    RECEPTIONIST = 'receptionist', 'Receptionist'
    ACCOUNTANT = 'accountant', 'Accountant'
    NURSE = 'nurse', 'Nurse'
    DOCTOR = 'doctor', 'Doctor'
    LAB_TECHNICIAN = 'lab_technician', 'Lab Technician'


class Specialty(models.TextChoices):
    GENERALIST = 'generalist', 'Generalist'
    DENTIST = 'dentist', 'Dentist'
    DERMATOLOGIST = 'dermatologist', 'Dermatologist'
    PEDIATRICIAN = 'pediatrician', 'Pediatrician'
    CARDIOLOGIST = 'cardiologist', 'Cardiologist'
    NEUROLOGIST = 'neurologist', 'Neurologist'
    SURGEON = 'surgeon', 'Surgeon'
    ORTHOPEDIST = 'orthopedist', 'Orthopedist'
    GYNECOLOGIST = 'gynecologist', 'Gynecologist'
    OPHTHALMOLOGIST = 'ophthalmologist', 'Ophthalmologist'
    ENT = 'ent', 'ENT (Ear, Nose & Throat)'
    PSYCHIATRIST = 'psychiatrist', 'Psychiatrist'
    RADIOLOGIST = 'radiologist', 'Radiologist'
    ANESTHESIOLOGIST = 'anesthesiologist', 'Anesthesiologist'
    UROLOGIST = 'urologist', 'Urologist'
    ONCOLOGIST = 'oncologist', 'Oncologist'
    ENDOCRINOLOGIST = 'endocrinologist', 'Endocrinologist'
    OTHER = 'other', 'Other'


class Language(models.TextChoices):
    ENGLISH = 'en', 'English'
    FRENCH = 'fr', 'Français'


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RECEPTIONIST)
    specialty = models.CharField(
        max_length=30, choices=Specialty.choices, blank=True, default='',
        help_text="Only applicable for doctors"
    )
    phone = models.CharField(max_length=20, blank=True)
    is_deleted = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    preferred_language = models.CharField(
        max_length=5, choices=Language.choices, blank=True, default='',
        help_text="If blank, the hospital's default system language is used."
    )
    created_by = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='created_users'
    )

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_doctor(self):
        return self.role == Role.DOCTOR

    @property
    def is_nurse(self):
        return self.role == Role.NURSE

    @property
    def is_receptionist(self):
        return self.role == Role.RECEPTIONIST

    @property
    def is_accountant(self):
        return self.role == Role.ACCOUNTANT

    @property
    def is_lab_technician(self):
        return self.role == Role.LAB_TECHNICIAN


class LogoSize(models.TextChoices):
    SMALL  = 'small',  'Small (48 px)'
    MEDIUM = 'medium', 'Medium (80 px)'
    LARGE  = 'large',  'Large (128 px)'


class HospitalSettings(models.Model):
    hospital_name = models.CharField(
        max_length=200, default='Hospital',
        help_text="Hospital name shown on receipts and the login page"
    )
    logo = models.ImageField(
        upload_to='hospital_logo/', null=True, blank=True,
        help_text="Logo shown on login page, receipts, and as favicon"
    )
    logo_size = models.CharField(
        max_length=10, choices=LogoSize.choices, default=LogoSize.MEDIUM,
        help_text="Display size of the logo on the login page and sidebar"
    )
    consultation_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Standard consultation fee in CDF"
    )
    fixed_fee = models.DecimalField(
        max_digits=14, decimal_places=2, default=46136.71,
        help_text="Fixed administrative fee in CDF added to every bill"
    )
    currency = models.CharField(
        max_length=10, default='CDF',
        help_text="Primary currency code or symbol (e.g. CDF, RWF, KES)"
    )
    language = models.CharField(
        max_length=10,
        choices=[('en', 'English'), ('fr', 'Français')],
        default='en',
        help_text="System-wide display language for all users"
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        'User', null=True, blank=True, on_delete=models.SET_NULL, related_name='settings_updated'
    )

    class Meta:
        verbose_name = "Hospital Settings"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Hospital Settings"


class SpecialistConsultationFee(models.Model):
    specialty = models.CharField(
        max_length=30, choices=Specialty.choices, unique=True,
        help_text="Specialist type this fee applies to"
    )
    fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Consultation fee for this specialist in CDF"
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        'User', null=True, blank=True, on_delete=models.SET_NULL, related_name='specialist_fees_updated'
    )

    class Meta:
        ordering = ['specialty']
        verbose_name = "Specialist Consultation Fee"

    def __str__(self):
        return f"{self.get_specialty_display()} — {self.fee}"


class FormCategory(models.TextChoices):
    GENERAL = 'general', 'General'
    CLINICAL = 'clinical', 'Clinical'
    REGISTRATION = 'registration', 'Patient Registration'
    CONSENT = 'consent', 'Consent & Legal'
    LABORATORY = 'laboratory', 'Laboratory'
    BILLING = 'billing', 'Billing & Insurance'
    ADMISSION = 'admission', 'Admission & Discharge'
    OTHER = 'other', 'Other'


class HospitalForm(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=30, choices=FormCategory.choices, default=FormCategory.GENERAL)
    file = models.FileField(upload_to='hospital_forms/')
    is_active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(
        'User', null=True, blank=True, on_delete=models.SET_NULL, related_name='uploaded_forms'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'title']
        verbose_name = "Hospital Form"

    def __str__(self):
        return self.title

    @property
    def filename(self):
        import os
        return os.path.basename(self.file.name)

    @property
    def file_extension(self):
        import os
        _, ext = os.path.splitext(self.file.name)
        return ext.lower().lstrip('.')


class ConsumableCategory(models.TextChoices):
    MEDICATION  = 'medication',   'Medication'
    CONSUMABLES = 'consumables',  'Consumables'
    ACT         = 'act',          'Act'


class Consumable(models.Model):
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=ConsumableCategory.choices, default=ConsumableCategory.ACT)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=50, default='unit', help_text="e.g. tablet, ml, piece, roll")
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'User', null=True, blank=True, on_delete=models.SET_NULL, related_name='consumables_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.unit})"

    class Meta:
        ordering = ['category', 'name']
        verbose_name = "Consumable / Supply"


class VisitConsumable(models.Model):
    visit = models.ForeignKey(
        'patients.Visit', on_delete=models.CASCADE, related_name='consumables'
    )
    consumable = models.ForeignKey(
        Consumable, on_delete=models.PROTECT, related_name='visit_uses'
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    administered_by = models.ForeignKey(
        'User', null=True, blank=True, on_delete=models.SET_NULL, related_name='administered_consumables'
    )
    notes = models.TextField(blank=True)
    is_billed = models.BooleanField(default=False)
    billed_payment = models.ForeignKey(
        'billing.Payment', null=True, blank=True, on_delete=models.SET_NULL, related_name='billed_consumables'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_price(self):
        from decimal import Decimal
        return Decimal(str(self.quantity)) * Decimal(str(self.unit_price))

    def __str__(self):
        return f"{self.consumable.name} x{self.quantity}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Visit Consumable"


class Insurance(models.Model):
    name = models.CharField(max_length=100, unique=True)
    coverage_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Percentage the INSURANCE covers (e.g. 90 means insurance pays 90%, patient pays 10%)"
    )
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='insurances_created')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (covers {self.coverage_percentage}%)"
