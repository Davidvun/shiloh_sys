from django.db import migrations, models


def convert_forward(apps, schema_editor):
    Insurance = apps.get_model('core', 'Insurance')
    for ins in Insurance.objects.filter(coverage_percentage__lt=100):
        ins.coverage_percentage = 100 - ins.coverage_percentage
        ins.save()


def convert_backward(apps, schema_editor):
    Insurance = apps.get_model('core', 'Insurance')
    for ins in Insurance.objects.filter(coverage_percentage__gt=0, coverage_percentage__lte=100):
        ins.coverage_percentage = 100 - ins.coverage_percentage
        ins.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_add_logo_and_hospital_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='insurance',
            name='coverage_percentage',
            field=models.DecimalField(
                max_digits=5, decimal_places=2,
                help_text='Percentage the INSURANCE covers (e.g. 90 means insurance pays 90%, patient pays 10%)'
            ),
        ),
        migrations.RunPython(convert_forward, convert_backward),
    ]
