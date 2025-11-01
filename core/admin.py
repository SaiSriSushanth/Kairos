from django.contrib import admin
from .models import Task, Schedule, ScheduleItem, Preferences, CalendarEvent


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'priority', 'duration_minutes', 'energy_level', 'daily_time_minutes',
        'time_of_day_pref', 'task_type', 'begin_date', 'deadline', 'completed', 'created_at'
    )
    list_filter = ('priority', 'energy_level', 'time_of_day_pref', 'task_type', 'completed')
    search_fields = ('title',)
    date_hierarchy = 'begin_date'
    ordering = ('-created_at',)


class ScheduleItemInline(admin.TabularInline):
    model = ScheduleItem
    extra = 0
    fields = ('title', 'start_time', 'end_time', 'position', 'task')
    ordering = ('position',)


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('id', 'mode', 'day_date', 'day_start', 'day_end', 'created_at')
    list_filter = ('mode', 'day_date')
    search_fields = ('plan_text',)
    date_hierarchy = 'day_date'
    ordering = ('-day_date', '-created_at')
    inlines = [ScheduleItemInline]


@admin.register(ScheduleItem)
class ScheduleItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'schedule', 'start_time', 'end_time', 'position', 'task')
    list_filter = ('schedule',)
    search_fields = ('title',)
    ordering = ('schedule', 'position')


@admin.register(Preferences)
class PreferencesAdmin(admin.ModelAdmin):
    list_display = ('focus_window_start', 'focus_window_end', 'break_cadence_minutes', 'working_days')


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_time', 'end_time', 'source')
    list_filter = ('source',)
    search_fields = ('title',)
    date_hierarchy = 'start_time'
