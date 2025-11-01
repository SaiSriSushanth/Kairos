from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login as auth_login
from django.views.generic import TemplateView, ListView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse
from django.http import JsonResponse
from django.http import HttpResponse
from django.utils import timezone
from .models import Task, Schedule, ScheduleItem, Preferences, CalendarEvent
from .ai import generate_schedule, generate_chat_reply
from datetime import datetime, timedelta, date as date_cls
import json
import re


class HomeView(TemplateView):
    template_name = 'home.html'


class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'tasks/list.html'
    context_object_name = 'tasks'

    def get_queryset(self):
        cleanup_expired_tasks()
        return Task.objects.all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['today'] = timezone.localdate()
        return ctx


@login_required
def create_task(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        priority = request.POST.get('priority') or 'Medium'
        energy = request.POST.get('energy') or 'Normal'
        deadline = request.POST.get('deadline') or None
        begin_date_str = request.POST.get('begin_date') or None
        daily_time = int(request.POST.get('daily_time') or 0)
        time_pref = request.POST.get('time_pref') or 'Any'
        task_type = request.POST.get('task_type') or 'General'
        begin_date = None
        if begin_date_str:
            try:
                begin_date = datetime.strptime(begin_date_str, '%Y-%m-%d').date()
            except Exception:
                begin_date = None
        Task.objects.create(
            title=title,
            priority=priority,
            energy_level=energy,
            deadline=deadline or None,
            begin_date=begin_date,
            daily_time_minutes=daily_time,
            time_of_day_pref=time_pref,
            task_type=task_type,
        )
        # Invalidate saved schedules from today so they regenerate on next view
        _invalidate_schedules_from(timezone.localdate())
        return redirect('tasks:list')
    # Planner summary for warnings
    today = timezone.localdate()
    tasks = Task.objects.filter(completed=False).filter(Q(begin_date__isnull=True) | Q(begin_date__lte=today))
    total_used = sum(int(t.daily_time_minutes or 0) for t in tasks)
    prefs = Preferences.objects.first()
    def minutes_between(a, b):
        try:
            if not a or not b:
                return 540
            dt = datetime.combine(timezone.localdate(), a), datetime.combine(timezone.localdate(), b)
            return int((dt[1] - dt[0]).total_seconds() // 60)
        except Exception:
            return 540
    day_budget = minutes_between(getattr(prefs, 'focus_window_start', None), getattr(prefs, 'focus_window_end', None))
    pref_totals = {}
    for p in ['Any','Morning','Noon','Afternoon','Evening','Night']:
        pref_totals[p] = sum(int(t.daily_time_minutes or 0) for t in tasks if t.time_of_day_pref == p)
    pref_budgets = {
        'Any': day_budget,
        'Morning': 180,
        'Noon': 60,
        'Afternoon': 240,
        'Evening': 120,
        'Night': 240,
    }
    return render(request, 'tasks/create.html', {
        'planner': {
            'day_budget': day_budget,
            'total_used': total_used,
            'pref_totals': pref_totals,
            'pref_budgets': pref_budgets,
        }
    })


@login_required
def edit_task(request, task_id):
    t = Task.objects.get(id=task_id)
    if request.method == 'POST':
        t.title = request.POST.get('title') or t.title
        t.priority = request.POST.get('priority') or t.priority
        t.energy_level = request.POST.get('energy') or t.energy_level
        deadline = request.POST.get('deadline') or None
        t.deadline = deadline or t.deadline
        begin_date_str = request.POST.get('begin_date') or None
        if begin_date_str:
            try:
                t.begin_date = datetime.strptime(begin_date_str, '%Y-%m-%d').date()
            except Exception:
                pass
        t.daily_time_minutes = int(request.POST.get('daily_time') or t.daily_time_minutes)
        t.time_of_day_pref = request.POST.get('time_pref') or t.time_of_day_pref
        t.task_type = request.POST.get('task_type') or t.task_type
        t.save()
        # Invalidate saved schedules from today
        _invalidate_schedules_from(timezone.localdate())
        return redirect('tasks:list')
    # Planner summary for warnings
    today = timezone.localdate()
    tasks = Task.objects.filter(completed=False).filter(Q(begin_date__isnull=True) | Q(begin_date__lte=today)).exclude(id=t.id)
    total_used = sum(int(x.daily_time_minutes or 0) for x in tasks)
    prefs = Preferences.objects.first()
    def minutes_between(a, b):
        try:
            if not a or not b:
                return 540
            dt = datetime.combine(timezone.localdate(), a), datetime.combine(timezone.localdate(), b)
            return int((dt[1] - dt[0]).total_seconds() // 60)
        except Exception:
            return 540
    day_budget = minutes_between(getattr(prefs, 'focus_window_start', None), getattr(prefs, 'focus_window_end', None))
    pref_totals = {}
    for p in ['Any','Morning','Noon','Afternoon','Evening','Night']:
        pref_totals[p] = sum(int(x.daily_time_minutes or 0) for x in tasks if x.time_of_day_pref == p)
    pref_budgets = {
        'Any': day_budget,
        'Morning': 180,
        'Noon': 60,
        'Afternoon': 240,
        'Evening': 120,
        'Night': 240,
    }
    return render(request, 'tasks/create.html', {'task': t, 'planner': {
        'day_budget': day_budget,
        'total_used': total_used,
        'pref_totals': pref_totals,
        'pref_budgets': pref_budgets,
    }})


@login_required
def delete_task(request, task_id):
    t = Task.objects.get(id=task_id)
    if request.method == 'POST':
        t.delete()
        # Invalidate saved schedules from today after deletion
        _invalidate_schedules_from(timezone.localdate())
        return redirect('tasks:list')
    return render(request, 'tasks/delete_confirm.html', {'task': t})


@login_required
def toggle_complete(request, task_id):
    t = Task.objects.get(id=task_id)
    t.completed = not t.completed
    t.save(update_fields=['completed'])
    # Invalidate saved schedules from today after completion toggle
    _invalidate_schedules_from(timezone.localdate())
    return redirect('tasks:list')


@login_required
def preferences_view(request):
    prefs, _ = Preferences.objects.get_or_create(id=1)
    if request.method == 'POST':
        fs = request.POST.get('focus_start') or None
        fe = request.POST.get('focus_end') or None
        # Sanitize time inputs: require HH:MM 24h; fallback to None if invalid/reversed
        def parse_time(s):
            try:
                return datetime.strptime(s, '%H:%M').time()
            except Exception:
                return None
        st = parse_time(fs) if fs else None
        en = parse_time(fe) if fe else None
        if st and en and en > st:
            prefs.focus_window_start = st.strftime('%H:%M')
            prefs.focus_window_end = en.strftime('%H:%M')
        else:
            # Invalid format or end <= start: revert to None to use defaults elsewhere
            prefs.focus_window_start = None
            prefs.focus_window_end = None
        prefs.break_cadence_minutes = int(request.POST.get('break_cadence') or prefs.break_cadence_minutes)
        prefs.working_days = request.POST.get('working_days') or prefs.working_days
        prefs.save()
        return redirect('settings')
    return render(request, 'settings.html', { 'prefs': prefs })


@login_required
def calendar_view(request):
    events = CalendarEvent.objects.order_by('start_time')[:200]
    return render(request, 'calendar.html', {'events': events})


@login_required
def calendar_chat(request):
    """POST endpoint: take a user message and return an assistant reply
    with awareness of tasks and saved schedules.

    Body: {"message": "..."}
    Response: {"reply": "..."}
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = {}
    user_msg = (data.get('message') or '').strip()
    if not user_msg:
        return JsonResponse({'error': 'message required'}, status=400)
    # Gather context
    prefs = Preferences.objects.first()
    def safe_str(s, default):
        try:
            t = datetime.strptime((s or default), '%H:%M').time()
            return t.strftime('%H:%M')
        except Exception:
            return default
    day_start = safe_str(getattr(prefs, 'focus_window_start', None), '09:00')
    day_end = safe_str(getattr(prefs, 'focus_window_end', None), '18:00')
    tasks = Task.objects.filter(completed=False).order_by('-priority', 'title')[:500]
    schedules = Schedule.objects.order_by('-day_date', '-created_at')[:30]
    reply = generate_chat_reply(user_msg, tasks, schedules, day_start, day_end)
    return JsonResponse({'reply': reply})


@login_required
def import_ics(request):
    if request.method == 'POST' and request.FILES.get('ics'):
        f = request.FILES['ics']
        content = f.read().decode('utf-8', errors='ignore')
        lines = [l.strip() for l in content.splitlines()]
        evt = {}
        def parse_dt(val):
            try:
                if val.endswith('Z'):
                    dt = datetime.strptime(val, '%Y%m%dT%H%M%SZ')
                    return timezone.make_aware(dt, timezone.utc)
                else:
                    dt = datetime.strptime(val, '%Y%m%dT%H%M%S')
                    return timezone.make_aware(dt)
            except Exception:
                return None
        for l in lines:
            if l == 'BEGIN:VEVENT':
                evt = {}
            elif l.startswith('SUMMARY:'):
                evt['title'] = l.split(':', 1)[1]
            elif l.startswith('DTSTART'):
                val = l.split(':', 1)[1]
                evt['start'] = parse_dt(val)
            elif l.startswith('DTEND'):
                val = l.split(':', 1)[1]
                evt['end'] = parse_dt(val)
            elif l == 'END:VEVENT':
                if evt.get('start') and evt.get('end'):
                    CalendarEvent.objects.create(title=evt.get('title') or 'Event', start_time=evt['start'], end_time=evt['end'], source='ICS')
        return redirect('tasks:calendar')
    return render(request, 'calendar_import.html')


def _seq_schedule_items(tasks, day_start: str, day_end: str, for_date: date_cls = None):
    """Lay out tasks sequentially within timeframe, skipping calendar conflicts.

    If ``for_date`` is provided, schedule within that date; otherwise uses today.
    """
    target_date = for_date or timezone.localdate()
    # Safely parse focus window; fallback to defaults on invalid inputs
    try:
        start_t = datetime.strptime(day_start or '09:00', '%H:%M').time()
    except Exception:
        start_t = datetime.strptime('09:00', '%H:%M').time()
    try:
        end_t = datetime.strptime(day_end or '18:00', '%H:%M').time()
    except Exception:
        end_t = datetime.strptime('18:00', '%H:%M').time()
    # If reversed window, swap to sensible defaults
    if end_t <= start_t:
        start_t = datetime.strptime('09:00', '%H:%M').time()
        end_t = datetime.strptime('18:00', '%H:%M').time()
    start_dt = timezone.make_aware(datetime.combine(target_date, start_t))
    end_dt = timezone.make_aware(datetime.combine(target_date, end_t))
    busy = list(CalendarEvent.objects.filter(start_time__date=target_date).values_list('start_time', 'end_time'))
    items = []
    cursor = start_dt
    pos = 0
    for t in tasks:
        # Use daily_time_minutes as the effective duration; fallback to existing duration or 30m
        dur_minutes = int(getattr(t, 'daily_time_minutes', 0) or 0)
        if dur_minutes <= 0:
            dur_minutes = int(getattr(t, 'duration_minutes', 30) or 30)
        dur = timedelta(minutes=dur_minutes)
        # advance cursor past any busy interval
        while True:
            overlap = next(((bs, be) for (bs, be) in busy if not (cursor >= be or (cursor + dur) <= bs)), None)
            if overlap:
                cursor = overlap[1]
            else:
                break
        if cursor + dur > end_dt:
            break
        items.append({
            'task': t,
            'title': t.title,
            'start': cursor,
            'end': cursor + dur,
            'position': pos,
        })
        cursor = cursor + dur
        pos += 1
    return items


@login_required
def scheduler(request):
    """Calendar-based scheduler page showing saved schedule for today."""
    cleanup_expired_tasks()
    prefs = Preferences.objects.first()
    def safe_str(s, default):
        try:
            t = datetime.strptime((s or default), '%H:%M').time()
            return t.strftime('%H:%M')
        except Exception:
            return default
    day_start = safe_str(getattr(prefs, 'focus_window_start', None), '09:00')
    day_end = safe_str(getattr(prefs, 'focus_window_end', None), '18:00')
    today = timezone.localdate()
    # Check global tasks and tasks applicable to today
    has_tasks_any = Task.objects.filter(completed=False).exists()
    has_tasks_for_today = Task.objects.filter(completed=False).filter(
        Q(begin_date__isnull=True) | Q(begin_date__lte=today)
    ).filter(
        Q(deadline__isnull=True) | Q(deadline__date__gte=today)
    ).exists()
    # Try to load a saved schedule for today
    schedule = Schedule.objects.filter(day_date=today).order_by('-created_at').first()
    if not schedule and has_tasks_for_today:
        # Generate on-demand and persist for today
        schedule = _generate_day_schedule(today)
    items = []
    if schedule:
        for it in schedule.items.all().order_by('position'):
            items.append({'title': it.title, 'start': it.start_time.strftime('%H:%M'), 'end': it.end_time.strftime('%H:%M')})
    return render(request, 'scheduler.html', {
        'day_start': day_start,
        'day_end': day_end,
        'today': today,
        'items': items,
        'has_tasks_for_date': has_tasks_for_today,
        'has_tasks_any': has_tasks_any,
    })


@login_required
def scheduler_day(request):
    """Return JSON schedule for a given date.

    Prefers saved schedule (Schedule/day_date). Includes calendar events and upcoming tasks.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)
    cleanup_expired_tasks()
    date_str = request.GET.get('date')
    try:
        target = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.localdate()
    except Exception:
        target = timezone.localdate()
    prefs = Preferences.objects.first()
    def safe_str(s, default):
        try:
            t = datetime.strptime((s or default), '%H:%M').time()
            return t.strftime('%H:%M')
        except Exception:
            return default
    day_start = safe_str(getattr(prefs, 'focus_window_start', None), '09:00')
    day_end = safe_str(getattr(prefs, 'focus_window_end', None), '18:00')
    # Check tasks applicable to target date and whether any tasks exist at all
    has_tasks_any = Task.objects.filter(completed=False).exists()
    has_tasks_for_target = Task.objects.filter(completed=False).filter(
        Q(begin_date__isnull=True) | Q(begin_date__lte=target)
    ).filter(
        Q(deadline__isnull=True) | Q(deadline__date__gte=target)
    ).exists()
    # Prefer saved schedule
    schedule = Schedule.objects.filter(day_date=target).order_by('-created_at').first()
    items = []
    if schedule:
        for it in schedule.items.all().order_by('position'):
            items.append({'title': it.title, 'start': it.start_time.strftime('%H:%M'), 'end': it.end_time.strftime('%H:%M')})
    else:
        if has_tasks_for_target:
            # Generate on-demand and persist for target date
            schedule = _generate_day_schedule(target)
            for it in schedule.items.all().order_by('position'):
                items.append({'title': it.title, 'start': it.start_time.strftime('%H:%M'), 'end': it.end_time.strftime('%H:%M')})
        # else: no applicable tasks for this date, return empty items
    # Events for target date
    events = []
    for (st, en, title) in CalendarEvent.objects.filter(start_time__date=target).values_list('start_time', 'end_time', 'title'):
        events.append({'title': title, 'start': st.strftime('%H:%M'), 'end': en.strftime('%H:%M')})
    # Upcoming tasks starting after target
    upcoming = []
    for t in Task.objects.filter(completed=False, begin_date__gt=target).order_by('begin_date')[:20]:
        delta_days = (t.begin_date - target).days if t.begin_date else None
        upcoming.append({'title': t.title, 'begin_date': t.begin_date.strftime('%Y-%m-%d'), 'in_days': delta_days})
    return JsonResponse({
        'date': target.strftime('%Y-%m-%d'),
        'day_start': day_start,
        'day_end': day_end,
        'items': items,
        'events': events,
        'upcoming': upcoming,
        'has_tasks_for_date': has_tasks_for_target,
        'has_tasks_any': has_tasks_any,
    })


@login_required
def scheduler_month_summary(request):
    """Return JSON summary of total scheduled minutes per day for a month.

    Query params: year (YYYY), month (1-12). Defaults to current month.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required'}, status=405)
    today = timezone.localdate()
    try:
        year = int(request.GET.get('year') or today.year)
        month = int(request.GET.get('month') or today.month)
    except Exception:
        year, month = today.year, today.month
    # First and last day of month
    first = date_cls(year, month, 1)
    # compute last day: next month minus one day
    if month == 12:
        next_month = date_cls(year+1, 1, 1)
    else:
        next_month = date_cls(year, month+1, 1)
    last = next_month - timedelta(days=1)
    # Build summary
    minutes_by_day = {}
    for sch in Schedule.objects.filter(day_date__gte=first, day_date__lte=last):
        total = 0
        for it in sch.items.all():
            total += int((it.end_time - it.start_time).total_seconds() // 60)
        if sch.day_date:
            minutes_by_day[sch.day_date.strftime('%Y-%m-%d')] = total
    return JsonResponse({
        'year': year,
        'month': month,
        'minutes_by_day': minutes_by_day,
    })


def _generate_day_schedule(target_date: date_cls):
    """Generate and persist a schedule for a specific date, then return the saved Schedule."""
    prefs = Preferences.objects.first()
    raw_start = getattr(prefs, 'focus_window_start', None)
    raw_end = getattr(prefs, 'focus_window_end', None)
    # Sanitize focus window strings
    def safe_str(s, default):
        try:
            t = datetime.strptime((s or default), '%H:%M').time()
            return t.strftime('%H:%M')
        except Exception:
            return default
    day_start = safe_str(raw_start, '09:00')
    day_end = safe_str(raw_end, '18:00')
    mode = 'Balanced'
    # Active tasks for target_date: begin_date <= target_date, deadline is null or >= target_date
    tasks_qs = Task.objects.filter(completed=False).filter(
        Q(begin_date__isnull=True) | Q(begin_date__lte=target_date)
    ).filter(
        Q(deadline__isnull=True) | Q(deadline__date__gte=target_date)
    )
    pref_order = {'Morning': 0, 'Noon': 1, 'Afternoon': 2, 'Evening': 3, 'Night': 4, 'Any': 5}
    prio_order = {'High': 0, 'Medium': 1, 'Low': 2}
    tasks = sorted(tasks_qs, key=lambda t: (
        pref_order.get(getattr(t, 'time_of_day_pref', 'Any'), 5),
        prio_order.get(t.priority, 1),
        -int((getattr(t, 'daily_time_minutes', 0) or getattr(t, 'duration_minutes', 30))),
    ))
    plan = generate_schedule(list(tasks), mode, day_start, day_end) or ''
    # Replace any existing schedule for this date
    Schedule.objects.filter(day_date=target_date).delete()
    # Safely parse for persistence
    try:
        start_t = datetime.strptime(day_start, '%H:%M').time()
    except Exception:
        start_t = datetime.strptime('09:00', '%H:%M').time()
    try:
        end_t = datetime.strptime(day_end, '%H:%M').time()
    except Exception:
        end_t = datetime.strptime('18:00', '%H:%M').time()
    if end_t <= start_t:
        start_t = datetime.strptime('09:00', '%H:%M').time()
        end_t = datetime.strptime('18:00', '%H:%M').time()
    schedule = Schedule.objects.create(
        mode=mode,
        day_start=start_t,
        day_end=end_t,
        plan_text=plan,
        day_date=target_date,
    )
    ai_items = _parse_ai_schedule(plan, target_date, day_start, day_end)
    # Try to attach tasks by title for AI-produced items
    if ai_items:
        _attach_tasks_by_title(ai_items, list(tasks))
        for s in ai_items:
            ScheduleItem.objects.create(
                schedule=schedule,
                task=s.get('task'),
                title=s['title'],
                start_time=s['start'],
                end_time=s['end'],
                position=s['position'],
            )
    else:
        # Fallback to sequential layout when AI schedule is unavailable or unparsable
        seq = _seq_schedule_items(list(tasks), day_start, day_end, for_date=target_date)
        for s in seq:
            ScheduleItem.objects.create(
                schedule=schedule,
                task=s['task'],
                title=s['title'],
                start_time=s['start'],
                end_time=s['end'],
                position=s['position'],
            )
    return schedule


def _parse_ai_schedule(plan_text: str, target_date: date_cls, day_start: str, day_end: str):
    """Parse AI plan text into concrete schedule items.

    Supports two formats:
    - Strict JSON: {"items": [{"title": "...", "start": "HH:MM", "end": "HH:MM"}], "notes": "..."}
    - Fallback line format: "HH:MM-HH:MM Title" (common separators - – —)
    Returns a list of dicts with keys: title, start (aware dt), end (aware dt), position, task(None)
    All items are clamped to the focus window.
    """
    items = []
    # Parse JSON first
    try:
        data = json.loads(plan_text)
        arr = data.get('items') if isinstance(data, dict) else (data if isinstance(data, list) else None)
        if isinstance(arr, list):
            pos = 0
            for obj in arr:
                title = (obj.get('title') or '').strip()
                st_s = (obj.get('start') or '').strip()
                en_s = (obj.get('end') or '').strip()
                if not title or not st_s or not en_s:
                    continue
                try:
                    st_t = datetime.strptime(st_s, '%H:%M').time()
                    en_t = datetime.strptime(en_s, '%H:%M').time()
                except Exception:
                    continue
                item = _build_item_with_clamp(title, st_t, en_t, target_date, day_start, day_end, pos)
                if item:
                    items.append(item)
                    pos += 1
            # Only return if we parsed at least one item
            if items:
                return items
    except Exception:
        pass

    # Fallback regex parsing from lines like "09:00-10:00 Task name"
    pattern = re.compile(r"(?m)^\s*(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})\s*[|:-]?\s*(.+?)\s*$")
    pos = 0
    for m in re.finditer(pattern, plan_text or ''):
        st_s, en_s, title = m.group(1), m.group(2), m.group(3).strip()
        try:
            st_t = datetime.strptime(st_s, '%H:%M').time()
            en_t = datetime.strptime(en_s, '%H:%M').time()
        except Exception:
            continue
        item = _build_item_with_clamp(title, st_t, en_t, target_date, day_start, day_end, pos)
        if item:
            items.append(item)
            pos += 1
    return items


def _build_item_with_clamp(title: str, st_t, en_t, target_date: date_cls, day_start: str, day_end: str, pos: int):
    # Clamp to focus window and discard invalid/empty ranges
    try:
        window_start = datetime.strptime(day_start, '%H:%M').time()
        window_end = datetime.strptime(day_end, '%H:%M').time()
    except Exception:
        window_start = datetime.strptime('09:00', '%H:%M').time()
        window_end = datetime.strptime('18:00', '%H:%M').time()
    # Clamp times
    st_t = max(st_t, window_start)
    en_t = min(en_t, window_end)
    if en_t <= st_t:
        return None
    start_dt = timezone.make_aware(datetime.combine(target_date, st_t))
    end_dt = timezone.make_aware(datetime.combine(target_date, en_t))
    return {
        'title': title,
        'start': start_dt,
        'end': end_dt,
        'position': pos,
        'task': None,
    }


def _attach_tasks_by_title(items, tasks):
    # Best-effort: exact case-insensitive title match
    title_map = {t.title.strip().lower(): t for t in tasks}
    for it in items:
        t = title_map.get(it['title'].strip().lower())
        if t:
            it['task'] = t


def cleanup_expired_tasks():
    now = timezone.now()
    Task.objects.filter(deadline__isnull=False, deadline__lte=now).delete()


@login_required
def update_schedule_order(request, schedule_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        schedule = Schedule.objects.get(id=schedule_id)
    except Schedule.DoesNotExist:
        return JsonResponse({'error': 'Schedule not found'}, status=404)
    order = request.POST.getlist('item_ids[]')
    # Update positions
    for idx, item_id in enumerate(order):
        ScheduleItem.objects.filter(id=item_id, schedule=schedule).update(position=idx)
    # Recompute times sequentially based on duration
    start_time = timezone.make_aware(datetime.combine(timezone.localdate(), schedule.day_start))
    cursor = start_time
    for item in schedule.items.all().order_by('position'):
        dur = item.end_time - item.start_time
        item.start_time = cursor
        item.end_time = cursor + dur
        item.save(update_fields=['start_time', 'end_time'])
        cursor = item.end_time
    # Return updated items for UI refresh
    updated = []
    for it in schedule.items.all().order_by('position'):
        updated.append({
            'id': str(it.id),
            'title': it.title,
            'start': it.start_time.strftime('%H:%M'),
            'end': it.end_time.strftime('%H:%M'),
            'position': it.position,
        })
    return JsonResponse({'ok': True, 'items': updated})


def _invalidate_schedules_from(date_from: date_cls):
    """Delete ALL saved schedules when tasks change.

    Previously this deleted from a given date onward; per new requirement,
    we remove every saved schedule so views regenerate on demand.
    """
    try:
        Schedule.objects.all().delete()
    except Exception:
        pass


@login_required
def export_schedule_ics(request, schedule_id):
    try:
        schedule = Schedule.objects.get(id=schedule_id)
    except Schedule.DoesNotExist:
        return HttpResponse('Not found', status=404)
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Todou AI//Kash Scheduler//EN',
    ]
    for it in schedule.items.all():
        def fmt(dt):
            return dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        lines += [
            'BEGIN:VEVENT',
            f'SUMMARY:{it.title}',
            f'DTSTART:{fmt(it.start_time)}',
            f'DTEND:{fmt(it.end_time)}',
            'END:VEVENT',
        ]
    lines.append('END:VCALENDAR')
    ics = "\r\n".join(lines)
    resp = HttpResponse(ics, content_type='text/calendar')
    resp['Content-Disposition'] = f'attachment; filename="schedule-{schedule.id}.ics"'
    return resp


def analytics_view(request):
    total_tasks = Task.objects.count()
    completed_tasks = Task.objects.filter(completed=True).count()
    latest = Schedule.objects.order_by('-created_at').first()
    total_minutes = 0
    if latest:
        for it in latest.items.all():
            total_minutes += int((it.end_time - it.start_time).total_seconds() // 60)

    # Charts data
    # Completion chart
    completion_labels = ['Completed', 'Incomplete']
    completion_data = [completed_tasks, max(total_tasks - completed_tasks, 0)]

    # Priority distribution (incomplete tasks)
    priority_labels = ['High', 'Medium', 'Low']
    priority_data = [
        Task.objects.filter(completed=False, priority='High').count(),
        Task.objects.filter(completed=False, priority='Medium').count(),
        Task.objects.filter(completed=False, priority='Low').count(),
    ]

    # Energy distribution (incomplete tasks)
    energy_labels = ['High', 'Normal', 'Low']
    energy_data = [
        Task.objects.filter(completed=False, energy_level='High').count(),
        Task.objects.filter(completed=False, energy_level='Normal').count(),
        Task.objects.filter(completed=False, energy_level='Low').count(),
    ]

    # Schedule minutes per day (last 14 schedules)
    scheds = list(Schedule.objects.exclude(day_date__isnull=True).order_by('-day_date')[:14])
    schedule_labels = [s.day_date.strftime('%Y-%m-%d') for s in reversed(scheds)]
    schedule_data = []
    for s in reversed(scheds):
        mins = 0
        for it in s.items.all():
            mins += int((it.end_time - it.start_time).total_seconds() // 60)
        schedule_data.append(mins)

    # Additional analytics
    # Tasks created per day (last 14 days)
    today = timezone.localdate()
    last_days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    tasks_created_labels = [d.strftime('%Y-%m-%d') for d in last_days]
    tasks_created_data = [Task.objects.filter(created_at__date=d).count() for d in last_days]

    # Task type distribution (all tasks)
    task_type_labels = [c[0] for c in Task.TASK_TYPE_CHOICES]
    task_type_data = [Task.objects.filter(task_type=label).count() for label in task_type_labels]

    # Time-of-day preference distribution (incomplete tasks)
    time_pref_labels = [c[0] for c in Task.TIME_OF_DAY_CHOICES]
    time_pref_data = [Task.objects.filter(completed=False, time_of_day_pref=label).count() for label in time_pref_labels]

    # Schedule mode distribution (recent schedules)
    mode_labels = [c[0] for c in Schedule.MODE_CHOICES]
    recent_scheds = Schedule.objects.order_by('-created_at')[:50]
    mode_counts = {m: 0 for m in mode_labels}
    for sch in recent_scheds:
        mode_counts[sch.mode] = mode_counts.get(sch.mode, 0) + 1
    schedule_mode_labels = mode_labels
    schedule_mode_data = [mode_counts[m] for m in mode_labels]

    return render(request, 'analytics.html', {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'latest_schedule': latest,
        'total_minutes': total_minutes,
        'completion_labels': completion_labels,
        'completion_data': completion_data,
        'priority_labels': priority_labels,
        'priority_data': priority_data,
        'energy_labels': energy_labels,
        'energy_data': energy_data,
        'schedule_labels': schedule_labels,
        'schedule_data': schedule_data,
        'tasks_created_labels': tasks_created_labels,
        'tasks_created_data': tasks_created_data,
        'task_type_labels': task_type_labels,
        'task_type_data': task_type_data,
        'time_pref_labels': time_pref_labels,
        'time_pref_data': time_pref_data,
        'schedule_mode_labels': schedule_mode_labels,
        'schedule_mode_data': schedule_mode_data,
    })


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        # Style widgets to match the login page inputs
        try:
            form.fields['username'].widget.attrs.update({'class': 'input', 'autocomplete': 'username', 'placeholder': 'Choose a username'})
            form.fields['password1'].widget.attrs.update({'class': 'input', 'autocomplete': 'new-password', 'placeholder': 'Create a password'})
            form.fields['password2'].widget.attrs.update({'class': 'input', 'autocomplete': 'new-password', 'placeholder': 'Confirm password'})
        except Exception:
            pass
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect('tasks:home')
    else:
        form = UserCreationForm()
        try:
            form.fields['username'].widget.attrs.update({'class': 'input', 'autocomplete': 'username', 'placeholder': 'Choose a username'})
            form.fields['password1'].widget.attrs.update({'class': 'input', 'autocomplete': 'new-password', 'placeholder': 'Create a password'})
            form.fields['password2'].widget.attrs.update({'class': 'input', 'autocomplete': 'new-password', 'placeholder': 'Confirm password'})
        except Exception:
            pass
    return render(request, 'auth/register.html', {'form': form})

# Create your views here.
