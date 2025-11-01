from django.urls import path
from django.contrib.auth import views as auth_views
from .views import HomeView, TaskListView, create_task, scheduler, scheduler_day, scheduler_month_summary, update_schedule_order, edit_task, delete_task, toggle_complete, preferences_view, calendar_view, calendar_chat, import_ics, export_schedule_ics, analytics_view, register

app_name = 'tasks'

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    # Auth
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    # Use namespaced route for logout redirect to avoid NoReverseMatch in production
    path('logout/', auth_views.LogoutView.as_view(next_page='tasks:home'), name='logout'),
    path('register/', register, name='register'),
    path('tasks/', TaskListView.as_view(), name='list'),
    path('tasks/create/', create_task, name='create'),
    path('tasks/<int:task_id>/edit/', edit_task, name='edit'),
    path('tasks/<int:task_id>/delete/', delete_task, name='delete'),
    path('tasks/<int:task_id>/toggle/', toggle_complete, name='toggle'),
    path('scheduler/', scheduler, name='scheduler'),
    path('scheduler/day/', scheduler_day, name='scheduler-day'),
    path('scheduler/month/', scheduler_month_summary, name='scheduler-month'),
    path('scheduler/<int:schedule_id>/order/', update_schedule_order, name='schedule-order'),
    path('calendar/', calendar_view, name='calendar'),
    path('calendar/chat/', calendar_chat, name='calendar-chat'),
    path('calendar/import/', import_ics, name='calendar-import'),
    path('analytics/', analytics_view, name='analytics'),
    path('schedule/<int:schedule_id>/export.ics', export_schedule_ics, name='schedule-export'),
    path('settings/', preferences_view, name='settings'),
]