from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_task_begin_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='schedule',
            name='day_date',
            field=models.DateField(null=True, blank=True),
        ),
    ]