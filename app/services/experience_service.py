from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone

from app.extensions import db
from app.models import (
    AchievementUnlock,
    ComputerActivityBlock,
    DailyHealthSummary,
    ExperienceEvent,
    HealthImportRun,
    HydrationRecord,
    MealRecord,
    SessionRecord,
    SleepRecord,
    StudyRecord,
    TrainingRecord,
)
from app.services.notification_service import create_notification


XP_RULES = {
    "session_completed": (10, 40),
    "study_record": (5, 25),
    "training_record": (5, 10),
    "sleep_complete": (3, 3),
    "full_day": (15, 15),
}

ACHIEVEMENTS = (
    ("study_first", "Primeira sessão", "Estudos", "book-open", 10, "study_sessions", 1),
    ("study_10h", "10 horas de estudo", "Estudos", "book-open-check", 20, "study_minutes", 600),
    ("study_25h", "25 horas de estudo", "Estudos", "book-open-check", 30, "study_minutes", 1500),
    ("study_50h", "50 horas de estudo", "Estudos", "graduation-cap", 50, "study_minutes", 3000),
    ("study_100h", "100 horas de estudo", "Estudos", "graduation-cap", 100, "study_minutes", 6000),
    ("questions_100", "100 questões", "Estudos", "list-checks", 20, "questions", 100),
    ("questions_500", "500 questões", "Estudos", "list-checks", 50, "questions", 500),
    ("study_days_7", "Sete dias estudando", "Estudos", "calendar-check", 25, "study_days", 7),
    ("study_accuracy", "Evolução de acertos", "Estudos", "trending-up", 25, "accuracy_improved", 1),
    ("study_level_5", "Nível 5 em uma matéria", "Estudos", "badge-check", 35, "max_subject_level", 5),
    ("study_level_10", "Nível 10 em uma matéria", "Estudos", "award", 70, "max_subject_level", 10),
    ("training_first", "Primeiro treino", "Treinos", "dumbbell", 10, "training_sessions", 1),
    ("training_10", "10 treinos", "Treinos", "dumbbell", 20, "training_sessions", 10),
    ("training_25", "25 treinos", "Treinos", "medal", 35, "training_sessions", 25),
    ("training_50", "50 treinos", "Treinos", "trophy", 60, "training_sessions", 50),
    ("training_days_7", "Sete dias ativos", "Treinos", "calendar-check", 25, "training_days", 7),
    ("training_50km", "50 km acumulados", "Treinos", "route", 50, "distance_meters", 50_000),
    ("training_variety", "Diferentes modalidades", "Treinos", "shapes", 30, "training_types", 3),
    ("sleep_week", "Primeira semana registrada", "Sono", "moon-star", 20, "sleep_days", 7),
    ("sleep_complete_7", "Sete noites completas", "Sono", "moon-star", 25, "sleep_complete", 7),
    ("sleep_30", "30 noites acompanhadas", "Sono", "moon-star", 50, "sleep_days", 30),
    ("sleep_schedule", "Consistência de horário", "Sono", "clock-check", 30, "sleep_schedule_consistent", 1),
    ("sleep_subjective_7", "Sete registros subjetivos completos", "Sono", "sunrise", 25, "sleep_complete", 7),
    ("routine_first_full", "Primeiro dia 5/5", "Rotina", "circle-check-big", 20, "full_days", 1),
    ("routine_7_full", "Sete dias completos", "Rotina", "calendar-check-2", 45, "full_days", 7),
    ("routine_30_tracked", "30 dias acompanhados", "Rotina", "calendar-days", 50, "tracked_days", 30),
    ("routine_streak_3", "Sequência de três dias", "Rotina", "flame", 20, "longest_streak", 3),
    ("routine_streak_7", "Sequência de sete dias", "Rotina", "flame", 40, "longest_streak", 7),
    ("routine_streak_30", "Sequência de 30 dias", "Rotina", "flame", 100, "longest_streak", 30),
    ("computer_first_hour", "Primeira hora produtiva", "Computador", "monitor-check", 10, "productive_seconds", 3600),
    ("computer_10h", "10 horas produtivas", "Computador", "monitor-check", 25, "productive_seconds", 36_000),
    ("computer_50h", "50 horas produtivas", "Computador", "monitor-check", 60, "productive_seconds", 180_000),
    ("project_first", "Primeiro projeto", "Computador", "folder-check", 10, "projects", 1),
    ("project_10h", "10 horas em um projeto", "Computador", "folder-clock", 35, "top_project_seconds", 36_000),
    ("focus_7", "Sete sessões de foco", "Computador", "timer", 25, "focused_sessions", 7),
    ("health_first_sync", "Primeira sincronização", "Saúde", "watch", 10, "health_syncs", 1),
    ("health_30_days", "30 dias de dados", "Saúde", "heart-pulse", 40, "health_days", 30),
    ("steps_7_days", "Sete dias com passos", "Saúde", "footprints", 20, "steps_days", 7),
)

ACHIEVEMENT_UNITS = {
    "study_sessions": "sessions",
    "study_minutes": "minutes",
    "questions": "questions",
    "study_days": "days",
    "accuracy_improved": "records",
    "max_subject_level": "level",
    "training_sessions": "sessions",
    "training_days": "days",
    "training_types": "types",
    "distance_meters": "meters",
    "sleep_days": "nights",
    "sleep_complete": "nights",
    "sleep_schedule_consistent": "records",
    "full_days": "days",
    "tracked_days": "days",
    "longest_streak": "days",
    "productive_seconds": "seconds",
    "projects": "projects",
    "top_project_seconds": "seconds",
    "focused_sessions": "sessions",
    "health_syncs": "syncs",
    "health_days": "days",
    "steps_days": "days",
}


def format_achievement_value(value: int | float, unit: str) -> str:
    """Format achievement progress without guessing the unit from its value."""
    numeric = max(float(value or 0), 0)
    whole = int(round(numeric))
    if unit == "seconds":
        hours, remainder = divmod(whole, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes} min")
        if seconds and not hours:
            parts.append(f"{seconds} s")
        return " ".join(parts) or "0 s"
    if unit == "minutes":
        hours, minutes = divmod(whole, 60)
        if not hours:
            return f"{minutes} min"
        return f"{hours}h{minutes:02d}" if minutes else f"{hours}h"
    if unit == "meters":
        if numeric >= 1000:
            kilometers = numeric / 1000
            return f"{kilometers:g} km"
        return f"{whole} m"
    labels = {
        "days": ("dia", "dias"),
        "nights": ("noite", "noites"),
        "sessions": ("sessão", "sessões"),
        "questions": ("questão", "questões"),
        "records": ("registro", "registros"),
        "projects": ("projeto", "projetos"),
        "syncs": ("sincronização", "sincronizações"),
        "types": ("modalidade", "modalidades"),
        "level": ("nível", "níveis"),
        "xp": ("XP", "XP"),
    }
    singular, plural = labels.get(unit, ("registro", "registros"))
    return f"{whole} {singular if whole == 1 else plural}"


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _award(
    event_key: str,
    event_type: str,
    source_type: str,
    source_id: int | None,
    record_date: date,
    earned_at: datetime | None,
    xp_amount: int,
    *,
    daily_cap: int | None = None,
) -> bool:
    if db.session.scalar(
        db.select(ExperienceEvent.id).where(
            ExperienceEvent.event_key == event_key
        )
    ):
        return False
    if daily_cap is not None:
        earned = int(
            db.session.scalar(
                db.select(db.func.sum(ExperienceEvent.xp_amount)).where(
                    ExperienceEvent.event_type == event_type,
                    ExperienceEvent.record_date == record_date,
                )
            )
            or 0
        )
        if earned + xp_amount > daily_cap:
            return False
    db.session.add(
        ExperienceEvent(
            event_key=event_key,
            event_type=event_type,
            source_type=source_type,
            source_id=source_id,
            xp_amount=xp_amount,
            earned_at=_aware(earned_at),
            record_date=record_date,
            metadata_json=json.dumps({}, separators=(",", ":")),
        )
    )
    return True


def _metrics() -> dict[str, int]:
    studies = list(db.session.scalars(db.select(StudyRecord)))
    trainings = list(db.session.scalars(db.select(TrainingRecord)))
    sleeps = list(db.session.scalars(db.select(SleepRecord)))
    blocks = list(db.session.scalars(db.select(ComputerActivityBlock)))
    sessions = list(
        db.session.scalars(
            db.select(SessionRecord).where(SessionRecord.status == "completed")
        )
    )
    health_days = list(db.session.scalars(db.select(DailyHealthSummary)))
    health_syncs = int(
        db.session.scalar(
            db.select(db.func.count(HealthImportRun.id)).where(
                HealthImportRun.status.in_(
                    ("completed", "completed_with_warnings")
                )
            )
        )
        or 0
    )
    study_dates = {item.record_date for item in studies}
    training_dates = {item.record_date for item in trainings}
    sleep_dates = {item.record_date for item in sleeps}
    nutrition_dates = set(
        db.session.scalars(db.select(MealRecord.record_date))
    ) | set(db.session.scalars(db.select(HydrationRecord.record_date)))
    computer_dates = {
        item.record_date for item in blocks if not item.was_idle
    }
    full_dates = (
        study_dates
        & training_dates
        & sleep_dates
        & nutrition_dates
        & computer_dates
    )
    tracked_dates = (
        study_dates
        | training_dates
        | sleep_dates
        | nutrition_dates
        | computer_dates
    )
    longest_streak = 0
    current_streak = 0
    previous = None
    for tracked_date in sorted(tracked_dates):
        current_streak = (
            current_streak + 1
            if previous and (tracked_date - previous).days == 1
            else 1
        )
        longest_streak = max(longest_streak, current_streak)
        previous = tracked_date
    project_totals = Counter()
    for block in blocks:
        if block.project_key and not block.was_idle:
            project_totals[block.project_key] += block.duration_seconds or 0
    subject_xp = Counter()
    for item in studies:
        subject_xp[item.subject.casefold()] += min(
            max(int(item.duration_minutes or 0), 0),
            120,
        )
    max_subject_level = 1
    for xp in subject_xp.values():
        level = 1
        remaining = xp
        while remaining >= 100 + (level - 1) * 50:
            remaining -= 100 + (level - 1) * 50
            level += 1
        max_subject_level = max(max_subject_level, level)
    chronological = sorted(studies, key=lambda item: (item.record_date, item.id))
    midpoint = len(chronological) // 2
    accuracy = []
    for group in (chronological[:midpoint], chronological[midpoint:]):
        questions = sum(item.questions_count or 0 for item in group)
        correct = sum(item.correct_answers or 0 for item in group)
        accuracy.append(correct / questions if questions else None)
    sleep_starts = [
        item.sleep_start.hour * 60 + item.sleep_start.minute
        for item in sleeps
        if item.sleep_start is not None
    ]
    return {
        "study_sessions": len(studies),
        "study_minutes": sum(item.duration_minutes or 0 for item in studies),
        "questions": sum(item.questions_count or 0 for item in studies),
        "study_days": len({item.record_date for item in studies}),
        "accuracy_improved": int(
            len(chronological) >= 4
            and accuracy[0] is not None
            and accuracy[1] is not None
            and accuracy[1] > accuracy[0]
        ),
        "max_subject_level": max_subject_level,
        "training_sessions": len(trainings),
        "training_days": len({item.record_date for item in trainings}),
        "training_types": len({item.training_type for item in trainings}),
        "distance_meters": round(sum(item.distance_meters or 0 for item in trainings)),
        "sleep_days": len({item.record_date for item in sleeps}),
        "sleep_complete": sum(
            item.perceived_quality is not None and item.woke_restored is not None
            for item in sleeps
        ),
        "sleep_schedule_consistent": int(
            len(sleep_starts) >= 7
            and max(sleep_starts) - min(sleep_starts) <= 60
        ),
        "full_days": len(full_dates),
        "tracked_days": len(tracked_dates),
        "longest_streak": longest_streak,
        "productive_seconds": sum(
            item.duration_seconds or 0
            for item in blocks
            if not item.was_idle and item.classification == "productive"
        ),
        "projects": len(
            {item.project_key for item in blocks if item.project_key}
        ),
        "top_project_seconds": max(project_totals.values(), default=0),
        "focused_sessions": len(sessions),
        "health_syncs": health_syncs,
        "health_days": len(health_days),
        "steps_days": sum(item.steps is not None for item in health_days),
    }


def sync_experience_ledger() -> None:
    for record in db.session.scalars(db.select(StudyRecord).order_by(StudyRecord.id)):
        amount, cap = XP_RULES["study_record"]
        _award(
            f"study:{record.id}",
            "study_record",
            "study",
            record.id,
            record.record_date,
            record.created_at,
            amount,
            daily_cap=cap,
        )
    for record in db.session.scalars(db.select(TrainingRecord).order_by(TrainingRecord.id)):
        if record.intensity is None or record.perceived_performance is None:
            continue
        amount, cap = XP_RULES["training_record"]
        _award(
            f"training:{record.id}",
            "training_record",
            "training",
            record.id,
            record.record_date,
            record.created_at,
            amount,
            daily_cap=cap,
        )
    for record in db.session.scalars(db.select(SleepRecord).order_by(SleepRecord.id)):
        if record.perceived_quality is None or record.woke_restored is None:
            continue
        amount, cap = XP_RULES["sleep_complete"]
        _award(
            f"sleep:{record.id}",
            "sleep_complete",
            "sleep",
            record.id,
            record.record_date,
            record.created_at,
            amount,
            daily_cap=cap,
        )
    for record in db.session.scalars(
        db.select(SessionRecord)
        .where(SessionRecord.status == "completed")
        .order_by(SessionRecord.id)
    ):
        amount, cap = XP_RULES["session_completed"]
        _award(
            f"session:{record.id}",
            "session_completed",
            "session",
            record.id,
            record.record_date,
            record.finished_at or record.created_at,
            amount,
            daily_cap=cap,
        )
    full_dates = (
        set(db.session.scalars(db.select(StudyRecord.record_date)))
        & set(db.session.scalars(db.select(TrainingRecord.record_date)))
        & set(db.session.scalars(db.select(SleepRecord.record_date)))
        & (
            set(db.session.scalars(db.select(MealRecord.record_date)))
            | set(db.session.scalars(db.select(HydrationRecord.record_date)))
        )
        & set(
            db.session.scalars(
                db.select(ComputerActivityBlock.record_date).where(
                    ComputerActivityBlock.was_idle.is_(False)
                )
            )
        )
    )
    for complete_date in sorted(full_dates):
        amount, cap = XP_RULES["full_day"]
        awarded = _award(
            f"full-day:{complete_date.isoformat()}",
            "full_day",
            "daily_coverage",
            None,
            complete_date,
            datetime.combine(
                complete_date,
                datetime.min.time(),
                timezone.utc,
            ),
            amount,
            daily_cap=cap,
        )
        if awarded:
            create_notification(
                notification_key=f"daily-goal:{complete_date.isoformat()}",
                type="daily_goal_completed",
                title="Dia completo",
                message="Você registrou as cinco áreas do dia.",
                action_url="/",
                severity="success",
                source_type="daily_coverage",
                commit=False,
            )
    db.session.flush()
    metrics = _metrics()
    existing = {
        item.achievement_key: item
        for item in db.session.scalars(db.select(AchievementUnlock))
    }
    for key, title, category, icon, xp, metric_key, requirement in ACHIEVEMENTS:
        progress = int(metrics.get(metric_key, 0))
        if progress < requirement:
            continue
        unlocked = existing.get(key)
        if unlocked is None:
            unlocked = AchievementUnlock(
                achievement_key=key,
                unlocked_at=datetime.now(timezone.utc),
                progress_value=progress,
            )
            db.session.add(unlocked)
            existing[key] = unlocked
            create_notification(
                notification_key=f"achievement:{key}",
                type="achievement_unlocked",
                title="Nova conquista",
                message=f"Você desbloqueou “{title}”.",
                action_url="/perfil",
                severity="success",
                source_type="achievement",
                commit=False,
            )
        else:
            unlocked.progress_value = max(unlocked.progress_value, progress)
        _award(
            f"achievement:{key}",
            "achievement",
            "achievement",
            None,
            unlocked.unlocked_at.date(),
            unlocked.unlocked_at,
            xp,
        )
    db.session.commit()


def level_progress(total_xp: int) -> dict:
    remaining = max(int(total_xp), 0)
    level = 1
    while remaining >= 100 + (level - 1) * 50:
        remaining -= 100 + (level - 1) * 50
        level += 1
    needed = 100 + (level - 1) * 50
    return {
        "level": level,
        "total_xp": total_xp,
        "current_xp": remaining,
        "next_level_xp": needed,
        "progress_percent": round(remaining / needed * 100),
    }


def get_experience_summary(*, sync: bool = True) -> dict:
    if sync:
        sync_experience_ledger()
    total = int(
        db.session.scalar(db.select(db.func.sum(ExperienceEvent.xp_amount)))
        or 0
    )
    recent = list(
        db.session.scalars(
            db.select(ExperienceEvent)
            .order_by(ExperienceEvent.earned_at.desc(), ExperienceEvent.id.desc())
            .limit(8)
        )
    )
    labels = {
        "session_completed": "Sessão concluída",
        "study_record": "Estudo válido",
        "training_record": "Treino válido",
        "sleep_complete": "Sono completo",
        "full_day": "Dia completo",
        "achievement": "Conquista",
    }
    return {
        **level_progress(total),
        "recent": [
            {
                "label": labels.get(item.event_type, "Progresso"),
                "xp": item.xp_amount,
                "record_date": item.record_date.isoformat(),
            }
            for item in recent
        ],
    }


def get_achievements(*, sync: bool = True) -> list[dict]:
    if sync:
        sync_experience_ledger()
    metrics = _metrics()
    unlocked = {
        item.achievement_key: item
        for item in db.session.scalars(db.select(AchievementUnlock))
    }
    result = []
    for key, title, category, icon, xp, metric_key, requirement in ACHIEVEMENTS:
        progress = int(metrics.get(metric_key, 0))
        unlock = unlocked.get(key)
        unit = ACHIEVEMENT_UNITS[metric_key]
        current_label = format_achievement_value(progress, unit)
        target_label = format_achievement_value(requirement, unit)
        result.append(
            {
                "achievement_key": key,
                "name": title,
                "description": (
                    f"{current_label} de {target_label}"
                    if unlock is None
                    else f"Concluída · {current_label}"
                ),
                "category": category,
                "icon": icon,
                "xp": xp,
                "requirement": requirement,
                "unit": unit,
                "current_label": current_label,
                "target_label": target_label,
                "progress": progress,
                "progress_percent": min(100, round(progress / requirement * 100)),
                "unlocked": unlock is not None,
                "unlocked_at": (
                    unlock.unlocked_at.isoformat() if unlock else None
                ),
            }
        )
    return result
