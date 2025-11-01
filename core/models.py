from django.db import models
from django.utils import timezone


class Task(models.Model):
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]
    ENERGY_CHOICES = [
        ('Low', 'Low'),
        ('Normal', 'Normal'),
        ('High', 'High'),
    ]
    TIME_OF_DAY_CHOICES = [
        ('Any', 'Any'),
        ('Morning', 'Morning'),
        ('Noon', 'Noon'),
        ('Afternoon', 'Afternoon'),
        ('Evening', 'Evening'),
        ('Night', 'Night'),
    ]
    TASK_TYPE_CHOICES = [
        ('General', 'General'),
        ('Exam', 'Exam'),
        ('Project', 'Project'),
        ('Chores', 'Chores'),
        ('Study', 'Study'),
        ('Workout', 'Workout'),
        ('Meeting', 'Meeting'),
        ('Other', 'Other'),
    ]

    title = models.CharField(max_length=200)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')
    duration_minutes = models.PositiveIntegerField(default=30)
    deadline = models.DateTimeField(null=True, blank=True)
    begin_date = models.DateField(null=True, blank=True)
    energy_level = models.CharField(max_length=10, choices=ENERGY_CHOICES, default='Normal')
    daily_time_minutes = models.PositiveIntegerField(default=0)
    time_of_day_pref = models.CharField(max_length=20, choices=TIME_OF_DAY_CHOICES, default='Any')
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, default='General')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class Schedule(models.Model):
    MODE_CHOICES = [
        ('Balanced', 'Balanced'),
        ('Deep-work', 'Deep-work'),
        ('Quick-win', 'Quick-win'),
    ]
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='Balanced')
    day_start = models.TimeField(default=timezone.datetime.strptime('09:00', '%H:%M').time())
    day_end = models.TimeField(default=timezone.datetime.strptime('18:00', '%H:%M').time())
    plan_text = models.TextField(blank=True, default='')
    # New: the calendar date this schedule applies to
    day_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Schedule {self.id} ({self.mode})"


class ScheduleItem(models.Model):
    schedule = models.ForeignKey(Schedule, related_name='items', on_delete=models.CASCADE)
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=200)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position']

    def __str__(self):
        return f"{self.title} ({self.start_time:%H:%M}-{self.end_time:%H:%M})"


class Preferences(models.Model):
    focus_window_start = models.TimeField(null=True, blank=True)
    focus_window_end = models.TimeField(null=True, blank=True)
    break_cadence_minutes = models.PositiveIntegerField(default=0)
    working_days = models.CharField(max_length=32, default='Mon,Tue,Wed,Thu,Fri')

    def __str__(self):
        return "Preferences"


class CalendarEvent(models.Model):
    title = models.CharField(max_length=200)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    source = models.CharField(max_length=50, default='ICS')

    def __str__(self):
        return f"{self.title}"

# Create your models here.
