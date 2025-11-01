from typing import Iterable, List
from django.conf import settings
import json

def _format_task(t):
    dur = getattr(t, 'daily_time_minutes', 0) or getattr(t, 'duration_minutes', 30)
    base = f"- {t.title} | priority={t.priority}, planned={dur}m, energy={t.energy_level}"
    if t.deadline:
        base += f", deadline={t.deadline.isoformat()}"
    return base

def build_prompt(tasks: Iterable, mode: str, day_start: str, day_end: str) -> str:
    items = "\n".join(_format_task(t) for t in tasks)
    return (
        "You are Kash AI, an empathetic scheduling assistant for the Kairos app.\n"
        "Create an optimized, conflict-free day plan entirely within the timeframe.\n"
        f"Mode: {mode}. Timeframe: {day_start} to {day_end}.\n"
        "Rules: Respect deadlines, balance energy, cluster deep work, include short breaks, and note assumptions.\n"
        "IMPORTANT OUTPUT FORMAT: Respond ONLY with JSON using this schema:\n"
        "{\n  \"items\": [ { \"title\": \"...\", \"start\": \"HH:MM\", \"end\": \"HH:MM\" }, ... ],\n  \"notes\": \"any brief notes or assumptions\"\n}\n"
        "Ensure all times use 24h format HH:MM, are ordered, non-overlapping, and within the timeframe.\n"
        "Tasks:\n" + (items if items else "(no tasks provided)")
    )

def generate_schedule(tasks: Iterable, mode: str, day_start: str, day_end: str) -> str:
    if not settings.OPENAI_API_KEY:
        return "Missing OPENAI_API_KEY. Set it in environment to enable Kash AI."
    prompt = build_prompt(tasks, mode, day_start, day_end)
    # Prefer modern SDK (v1+) but gracefully fall back to legacy (<=0.28)
    try:
        from openai import OpenAI  # modern SDK
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are Kash AI for Kairos."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
        )
        return resp.choices[0].message.content
    except Exception:
        try:
            import openai  # legacy SDK
            openai.api_key = settings.OPENAI_API_KEY
            legacy_model = getattr(settings, 'OPENAI_MODEL', 'gpt-3.5-turbo')
            resp = openai.ChatCompletion.create(
                model=legacy_model,
                messages=[
                    {"role": "system", "content": "You are Kash AI for Kairos."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
            )
            return resp['choices'][0]['message']['content']
        except Exception as e2:
            return f"Kash AI error: {e2}"


def _summarize_tasks_for_chat(tasks: Iterable) -> str:
    lines: List[str] = []
    for t in tasks:
        dur = int(getattr(t, 'daily_time_minutes', 0) or getattr(t, 'duration_minutes', 30))
        bits = [
            f"title={t.title}",
            f"priority={getattr(t, 'priority', 'Medium')}",
            f"energy={getattr(t, 'energy_level', 'Normal')}",
            f"planned={dur}m",
        ]
        if getattr(t, 'begin_date', None):
            bits.append(f"begin={t.begin_date.isoformat()}")
        if getattr(t, 'deadline', None):
            try:
                bits.append(f"deadline={t.deadline.isoformat()}")
            except Exception:
                pass
        lines.append("- " + ", ".join(bits))
    return "\n".join(lines) if lines else "(no tasks)"


def _summarize_schedules_for_chat(schedules: Iterable) -> str:
    lines: List[str] = []
    for sch in schedules:
        try:
            day = getattr(sch, 'day_date', None)
            day_s = day.isoformat() if day else '(unknown day)'
        except Exception:
            day_s = '(unknown day)'
        lines.append(f"Day {day_s}:")
        idx = 0
        for it in getattr(sch, 'items', []).all() if hasattr(sch, 'items') else []:
            st = getattr(it, 'start_time', None)
            en = getattr(it, 'end_time', None)
            st_s = st.strftime('%H:%M') if st else '??:??'
            en_s = en.strftime('%H:%M') if en else '??:??'
            lines.append(f"  {idx+1}. {st_s}-{en_s} {getattr(it, 'title', '')}")
            idx += 1
        if idx == 0:
            lines.append("  (no items)")
    return "\n".join(lines) if lines else "(no saved schedules)"


def generate_chat_reply(user_message: str, tasks: Iterable, schedules: Iterable, day_start: str = None, day_end: str = None) -> str:
    """Produce a helpful assistant reply using tasks and saved schedules.

    Uses the configured OpenAI API key. Defaults to a fast chat model if none set.
    """
    if not settings.OPENAI_API_KEY:
        return "AI is not configured. Set OPENAI_API_KEY in the environment."
    task_summary = _summarize_tasks_for_chat(tasks)
    schedule_summary = _summarize_schedules_for_chat(schedules)
    timeframe = f"Focus window: {day_start or '09:00'}–{day_end or '18:00'}"
    system = (
        "You are Kash AI, a helpful planning assistant inside the Kairos app. "
        "You can see the user's tasks and saved schedules. Answer clearly, propose plans, "
        "and reference items by title/times when helpful. Keep responses concise and actionable."
    )
    context = (
        f"Context\n{timeframe}\n\nTasks:\n{task_summary}\n\nSaved schedules:\n{schedule_summary}"
    )
    try:
        # Prefer modern SDK (v1+)
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-3.5-turbo')
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": context},
                {"role": "user", "content": user_message},
            ],
            temperature=0.4,
        )
        text = resp.choices[0].message.content
        # Always append a valid schedule block so Apply Plan can detect it
        plan = generate_schedule(list(tasks), 'Balanced', day_start or '09:00', day_end or '18:00')
        try:
            data = json.loads(plan)
            items = data.get('items') or []
            lines = []
            for it in items:
                st = (it or {}).get('start')
                en = (it or {}).get('end')
                title = (it or {}).get('title') or ''
                if st and en and title:
                    lines.append(f"- {st}-{en} {title}")
            if lines:
                text = text + "\n\nPlan:\n" + "\n".join(lines)
        except Exception:
            # If JSON parse fails, keep original text
            pass
        return text
    except Exception:
        try:
            # Fallback legacy SDK
            import openai
            openai.api_key = settings.OPENAI_API_KEY
            legacy_model = getattr(settings, 'OPENAI_MODEL', 'gpt-3.5-turbo')
            resp = openai.ChatCompletion.create(
                model=legacy_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": context},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.4,
            )
            text = resp['choices'][0]['message']['content']
            plan = generate_schedule(list(tasks), 'Balanced', day_start or '09:00', day_end or '18:00')
            try:
                data = json.loads(plan)
                items = data.get('items') or []
                lines = []
                for it in items:
                    st = (it or {}).get('start')
                    en = (it or {}).get('end')
                    title = (it or {}).get('title') or ''
                    if st and en and title:
                        lines.append(f"- {st}-{en} {title}")
                if lines:
                    text = text + "\n\nPlan:\n" + "\n".join(lines)
            except Exception:
                pass
            return text
        except Exception as e2:
            return f"Chat AI error: {e2}"