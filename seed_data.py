#!/usr/bin/env python
"""
Seed script — creates demo users, insurance providers, and sample patients.
Run with: python manage.py shell < seed_data.py
OR:        python seed_data.py (if DJANGO_SETTINGS_MODULE is set)
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hms.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from core.models import User, Insurance, Role
from patients.models import Patient, Visit

print("🌱 Seeding database...")

# ── Admin ──────────────────────────────────────────────────────────────────
admin, _ = User.objects.get_or_create(username='admin', defaults={
    'first_name': 'System', 'last_name': 'Admin',
    'email': 'admin@medicore.rw', 'role': Role.ADMIN,
    'is_staff': True, 'is_superuser': True,
})
admin.set_password('Admin@1234')
admin.save()
print(f"  ✓ Admin: admin / Admin@1234")

# ── Staff Users ────────────────────────────────────────────────────────────
users_data = [
    ('receptionist1', 'Marie', 'Uwimana',    'receptionist1@medicore.rw', Role.RECEPTIONIST),
    ('accountant1',  'Jean',  'Habimana',    'accountant1@medicore.rw',   Role.ACCOUNTANT),
    ('nurse1',       'Grace', 'Mukamana',    'nurse1@medicore.rw',        Role.NURSE),
    ('doctor1',      'Dr. Eric', 'Nzeyimana','doctor1@medicore.rw',       Role.DOCTOR),
    ('doctor2',      'Dr. Diane','Ingabire', 'doctor2@medicore.rw',       Role.DOCTOR),
    ('labtech1',     'Patrick','Nshimiyimana','labtech1@medicore.rw',     Role.LAB_TECHNICIAN),
]
created_users = {}
for username, first, last, email, role in users_data:
    u, _ = User.objects.get_or_create(username=username, defaults={
        'first_name': first, 'last_name': last,
        'email': email, 'role': role, 'created_by': admin,
    })
    u.set_password('Pass@1234')
    u.save()
    created_users[role] = u
    print(f"  ✓ {role.capitalize()}: {username} / Pass@1234")

# ── Insurance Providers ────────────────────────────────────────────────────
insurances_data = [
    ('RSSB',   10),   # patient pays 10%
    ('Mituel', 15),   # patient pays 15%
    ('MMI',    20),   # patient pays 20%
    ('RADIANT',25),
]
ins_objects = {}
for name, pct in insurances_data:
    ins, _ = Insurance.objects.get_or_create(name=name, defaults={
        'coverage_percentage': pct, 'created_by': admin
    })
    ins_objects[name] = ins
    print(f"  ✓ Insurance: {name} (patient pays {pct}%)")

# ── Sample Patients ────────────────────────────────────────────────────────
receptionist = created_users.get(Role.RECEPTIONIST)
doctor1 = created_users.get(Role.DOCTOR)

patients_data = [
    ('Amina Mukamwezi',  32, 'F', '+250788100001', 'Kigali, Gasabo',    ins_objects['RSSB']),
    ('Jean Paul Habimana',45,'M', '+250788100002', 'Kigali, Nyarugenge', ins_objects['Mituel']),
    ('Claudine Uwera',   28, 'F', '+250788100003', 'Huye, Southern',    None),
    ('Emmanuel Nkurunziza',58,'M','+250788100004', 'Musanze, Northern', ins_objects['MMI']),
    ('Solange Iradukunda',22,'F','+250788100005', 'Rubavu, Western',    None),
]
for full_name, age, gender, phone, address, insurance in patients_data:
    if not Patient.objects.filter(full_name=full_name).exists():
        p = Patient.objects.create(
            full_name=full_name, age=age, gender=gender,
            phone=phone, address=address, insurance=insurance,
            registered_by=receptionist
        )
        # Create a visit for the first 2 patients
        if full_name in ['Amina Mukamwezi', 'Jean Paul Habimana']:
            Visit.objects.create(
                patient=p, doctor=doctor1,
                assigned_by=receptionist,
                status='pending'
            )
        print(f"  ✓ Patient: {p.patient_id} — {full_name}")

print("\n✅ Seed complete!")
print("\n📋 Login credentials:")
print("   Admin:        admin         / Admin@1234")
print("   Receptionist: receptionist1 / Pass@1234")
print("   Accountant:   accountant1   / Pass@1234")
print("   Nurse:        nurse1        / Pass@1234")
print("   Doctor:       doctor1       / Pass@1234")
print("   Lab Tech:     labtech1      / Pass@1234")
