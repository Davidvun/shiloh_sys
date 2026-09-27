from django.db import migrations


SEED = [
    ("HEMATOLOGY", ["FBC", "ESR", "Blood group", "Total Glycated Hb", "Coombs Indirect"]),
    ("HEMOSTASIS", ["Bleeding time", "Clotting time", "PT", "PTT", "Fibrinogen", "Thrombin time", "INR"]),
    ("URINE BIO-CHEMISTRY", ["Albuminuria", "Glucosuria", "Urobilinogen", "Urinary Density", "Ketones", "PH", "Pregnancy test"]),
    ("BACTERIOLOGY", ["Urine Microscopy", "Urine Gram Stain", "Vaginal Swab", "Urethral Swab", "CSF (Cerebral Spinal Fluid)", "Punction Fluid/Direct", "Other Swab"]),
    ("PARASITOLOGY", ["Malaria Parasite", "Direct Stool analysis", "Stool Gram"]),
    ("IMMUNO-SEROLOGY", [
        "C Reactive Protein", "ALSO", "H. Pylori Ab", "Arthri-test", "Rheumatoid Factor",
        "Waaler Rose test", "PRP/VDRL", "TPHA", "Widal Test", "HIV 1&2 Rapid test",
        "Toxoplasmosis IgM", "Toxoplasmosis IgG", "Rubeole IgG", "Rubeole IgM",
    ]),
    ("BLOOD BIOCHEMISTRY", [
        "GPT - ALAT", "GOT - ASAT", "GGT (Gamma-glutamyl transferase)", "Amylase", "PAL",
        "Lipase", "LDH", "Urea", "Creatinin", "Uric Acid", "Albumin", "Total Proteins",
        "Direct Bilirubin", "Total Bilirubin", "Triglycerides", "LDL - Cholesterol",
        "HDL - Cholesterol", "Total - Cholesterol", "Glucose Fasting", "Glucose Random",
        "Ferritin", "Iron", "Creatinine Kinase MB",
    ]),
    ("IONOGRAMME", ["Sodium", "Potassium", "Chloride", "Magnesium", "Phosphorus", "Calcium iron", "Calcium Total", "Blood PH"]),
    ("HORMONOLOGY", ["TSH", "FT4", "TT4", "FT3", "TT3", "FSH", "LH", "Prolactine", "Progesterone", "Estradiol", "Testosterone"]),
    ("HEPATITIS", ["HBs Ag", "HBS Ab", "HBE Ag", "HCVAb"]),
    ("TUMOR MARKERS TESTS", [
        "AFP (Alpha Foeto Protein)", "Total PSA", "Free PSA", "CEA", "Beta HCG Quantitative",
    ]),
    ("OTHERS TESTS", [
        "Spermogram", "Chlamidia test Ag", "H. Pyori Ag in stool", "Fecal occult blood test",
        "CMV Test", "Cardiac Troponin I", "Myoglobin", "Rotavirus Test", "D. Dimer",
        "Cystatin C", "NT - proBNP", "HCV Viral load", "HBS Viral load", "HIV Viral load",
        "CD4", "Folic Acid", "Oestradiol", "CA 125", "CA 15 - 3", "CA 19 - 9",
        "Sputum Analysis", "Cardiac Troponin T", "CRP", "Micro Albumin test",
        "Electrophoresis d'HB", "Electrophoresis Protein", "Chlamydia blood test",
        "Pap Smear", "Hemoculture", "Coproculture", "Urinoculture", "Antibiogramme",
        "CSF Culture", "Ponction Fluid Culture", "Other Culture", "Biopsy",
        "Immunoglobiline IG G", "Immunoglobiline IG A", "Immunoglobiline IG M",
        "Immunoglobiline IG E", "Immunoglobiline IG D",
    ]),
]


def seed(apps, schema_editor):
    Category = apps.get_model('laboratory', 'LabTestCategory')
    Test = apps.get_model('laboratory', 'LabTest')
    for order, (cat_name, tests) in enumerate(SEED, start=1):
        cat, _ = Category.objects.get_or_create(name=cat_name, defaults={'order': order})
        if cat.order != order:
            cat.order = order
            cat.save()
        for tname in tests:
            Test.objects.get_or_create(category=cat, name=tname)


def unseed(apps, schema_editor):
    apps.get_model('laboratory', 'LabTestCategory').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('laboratory', '0002_add_lab_catalog')]
    operations = [migrations.RunPython(seed, unseed)]
