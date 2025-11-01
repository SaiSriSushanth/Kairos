from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_calendarevent_preferences_schedule_task_completed_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='daily_time_minutes',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='task',
            name='time_of_day_pref',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('Any', 'Any'),
                    ('Morning', 'Morning'),
                    ('Noon', 'Noon'),
                    ('Afternoon', 'Afternoon'),
                    ('Evening', 'Evening'),
                    ('Night', 'Night'),
                ],
                default='Any',
            ),
        ),
        migrations.AddField(
            model_name='task',
            name='task_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('General', 'General'),
                    ('Exam', 'Exam'),
                    ('Project', 'Project'),
                    ('Chores', 'Chores'),
                    ('Study', 'Study'),
                    ('Workout', 'Workout'),
                    ('Meeting', 'Meeting'),
                    ('Other', 'Other'),
                ],
                default='General',
            ),
        ),
    ]