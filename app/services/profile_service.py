from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite
from typing import Any

from flask import current_app

from app.extensions import db
from app.models import (
    BodyMeasurement,
    ComputerActivityBlock,
    DailyHealthSummary,
    HealthImportRun,
    SessionRecord,
    SleepRecord,
    StudyRecord,
    StudySubjectProgress,
    TrainingRecord,
    UserProfile,
)
from app.services.analytics_utils import get_local_today
from app.services.experience_service import (
    get_achievements,
    get_experience_summary,
)


PERIOD_DAYS = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "6m": 183,
    "1y": 365,
}
_PROFILE_UNSET = object()
FOCUS_PERCENT = {
    "baixa": 20,
    "regular": 40,
    "boa": 65,
    "muito boa": 85,
    "excelente": 100,
}


def xp_for_record(record: StudyRecord) -> int:
    minutes = min(max(int(record.duration_minutes or 0), 0), 120)
    questions = max(int(record.questions_count or 0), 0)
    correct = max(int(record.correct_answers or 0), 0)
    focus = FOCUS_PERCENT.get(str(record.focus_quality or "").casefold(), 0)
    focus_bonus = min(20, round(minutes / 6)) if focus >= 70 else 0
    return minutes + questions * 2 + correct + focus_bonus


def level_from_xp(xp: int) -> int:
    level = 1
    remaining = max(int(xp), 0)
    while remaining >= 100 + (level - 1) * 50:
        remaining -= 100 + (level - 1) * 50
        level += 1
    return level


def rebuild_study_subject_progress() -> list[StudySubjectProgress]:
    records = list(
        db.session.scalars(
            db.select(StudyRecord).order_by(StudyRecord.created_at, StudyRecord.id)
        )
    )
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        key = record.subject.strip().casefold()
        item = grouped.setdefault(
            key,
            {
                "subject_name": record.subject.strip(),
                "xp": 0,
                "minutes": 0,
                "questions": 0,
                "correct": 0,
                "sessions": 0,
                "last": None,
            },
        )
        item["xp"] += xp_for_record(record)
        item["minutes"] += int(record.duration_minutes or 0)
        item["questions"] += int(record.questions_count or 0)
        item["correct"] += int(record.correct_answers or 0)
        item["sessions"] += 1
        studied_at = datetime.combine(record.record_date, time.min, timezone.utc)
        item["last"] = max(filter(None, (item["last"], studied_at)), default=studied_at)
    existing = {
        item.subject_name.casefold(): item
        for item in db.session.scalars(db.select(StudySubjectProgress))
    }
    keep = set()
    for key, values in grouped.items():
        progress = existing.get(key) or StudySubjectProgress(
            subject_name=values["subject_name"]
        )
        progress.xp = values["xp"]
        progress.level = level_from_xp(values["xp"])
        progress.total_minutes = values["minutes"]
        progress.total_questions = values["questions"]
        progress.correct_questions = values["correct"]
        progress.sessions_count = values["sessions"]
        progress.last_studied_at = values["last"]
        db.session.add(progress)
        keep.add(key)
    for key, progress in existing.items():
        if key not in keep:
            db.session.delete(progress)
    db.session.commit()
    return list(
        db.session.scalars(
            db.select(StudySubjectProgress).order_by(
                StudySubjectProgress.xp.desc(),
                StudySubjectProgress.subject_name,
            )
        )
    )


def _range(period: str) -> tuple[date, date, int | None]:
    today = get_local_today()
    if period == "all":
        first_dates = [
            db.session.scalar(db.select(db.func.min(model.record_date)))
            for model in (StudyRecord, TrainingRecord, SleepRecord, ComputerActivityBlock)
        ]
        start = min((item for item in first_dates if item), default=today)
        return start, today, None
    days = PERIOD_DAYS.get(period, 30)
    return today - timedelta(days=days - 1), today, days


def _comparison(current: float | int | None, previous: float | int | None, direction=None):
    if current is None or previous is None:
        trend = "insufficient_data"
        difference = None
        percentage = None
    else:
        difference = round(float(current) - float(previous), 2)
        percentage = (
            round(difference / abs(float(previous)) * 100, 1) if previous else None
        )
        if direction is None or abs(difference) < 0.01:
            trend = "stable"
        elif (difference > 0 and direction == "higher") or (
            difference < 0 and direction == "lower"
        ):
            trend = "improving"
        else:
            trend = "declining"
    return {
        "current": current,
        "previous": previous,
        "difference": difference,
        "percentage": percentage,
        "trend": trend,
    }


def _study_between(start: date, end: date) -> dict:
    records = list(
        db.session.scalars(
            db.select(StudyRecord).where(StudyRecord.record_date.between(start, end))
        )
    )
    total_minutes = sum(item.duration_minutes or 0 for item in records)
    questions = sum(item.questions_count or 0 for item in records)
    correct = sum(item.correct_answers or 0 for item in records)
    days = {item.record_date for item in records}
    focuses = [
        FOCUS_PERCENT.get(str(item.focus_quality or "").casefold())
        for item in records
    ]
    focuses = [item for item in focuses if item is not None]
    subjects = Counter(item.subject for item in records)
    return {
        "total_minutes": total_minutes,
        "hours": round(total_minutes / 60, 1),
        "daily_average_minutes": round(total_minutes / max((end - start).days + 1, 1)),
        "days_studied": len(days),
        "sessions": len(records),
        "focus_average": round(sum(focuses) / len(focuses)) if focuses else None,
        "questions": questions,
        "correct": correct,
        "accuracy": round(correct / questions * 100) if questions else None,
        "top_subjects": [
            {"name": name, "sessions": count} for name, count in subjects.most_common(5)
        ],
    }


def get_study_evolution(period_days: int = 30) -> dict:
    end = get_local_today()
    start = end - timedelta(days=period_days - 1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    current = _study_between(start, end)
    previous = _study_between(previous_start, previous_end)
    current["comparison"] = _comparison(
        current["total_minutes"], previous["total_minutes"], "higher"
    )
    current["subjects"] = [
        {
            "subject": item.subject_name,
            "level": item.level,
            "xp": item.xp,
            "minutes": item.total_minutes,
            "questions": item.total_questions,
            "accuracy": (
                round(item.correct_questions / item.total_questions * 100)
                if item.total_questions
                else None
            ),
            "sessions": item.sessions_count,
        }
        for item in rebuild_study_subject_progress()
    ]
    return current


def get_physical_evolution(period_days: int = 30) -> dict:
    end = get_local_today()
    start = end - timedelta(days=period_days - 1)
    measurements = list(
        db.session.scalars(
            db.select(BodyMeasurement)
            .where(
                db.func.date(BodyMeasurement.measured_at).between(start, end),
            )
            .order_by(BodyMeasurement.measured_at)
        )
    )
    weights = [item for item in measurements if item.weight_kg is not None]
    latest_weight = weights[-1].weight_kg if weights else None
    first_weight = weights[0].weight_kg if weights else None
    rolling = []
    for index, item in enumerate(weights):
        window = [entry.weight_kg for entry in weights[max(0, index - 6) : index + 1]]
        rolling.append(
            {
                "date": item.measured_at.date().isoformat(),
                "value": round(sum(window) / len(window), 2),
            }
        )
    summaries = list(
        db.session.scalars(
            db.select(DailyHealthSummary)
            .where(DailyHealthSummary.record_date.between(start, end))
            .order_by(DailyHealthSummary.record_date)
        )
    )
    steps = [item.steps for item in summaries if item.steps is not None]
    latest_vo2 = next((item.vo2_max for item in reversed(summaries) if item.vo2_max), None)
    latest_resting = next(
        (item.resting_heart_rate for item in reversed(summaries) if item.resting_heart_rate),
        None,
    )
    latest_fat = next(
        (
            item.body_fat_percentage
            for item in reversed(measurements)
            if item.body_fat_percentage is not None
        ),
        None,
    )
    return {
        "weight_current": latest_weight,
        "weight_first": first_weight,
        "weight_change": (
            round(latest_weight - first_weight, 2)
            if latest_weight is not None and first_weight is not None
            else None
        ),
        "weight_rolling_7d": rolling,
        "body_fat": latest_fat,
        "average_steps": round(sum(steps) / len(steps)) if steps else None,
        "vo2_max": latest_vo2,
        "resting_heart_rate": latest_resting,
        "measurements": len(measurements),
        "trend": "descriptive_only",
    }


def get_computer_evolution(period_days: int = 30) -> dict:
    end = get_local_today()
    start = end - timedelta(days=period_days - 1)
    rows = list(
        db.session.execute(
            db.select(
                ComputerActivityBlock.record_date,
                ComputerActivityBlock.classification,
                db.func.sum(ComputerActivityBlock.duration_seconds).label("seconds"),
            )
            .where(
                ComputerActivityBlock.record_date.between(start, end),
                ComputerActivityBlock.was_idle.is_(False),
            )
            .group_by(
                ComputerActivityBlock.record_date,
                ComputerActivityBlock.classification,
            )
        )
    )
    daily: dict = defaultdict(lambda: defaultdict(int))
    for row in rows:
        daily[row.record_date][row.classification] = int(row.seconds or 0)
    productive = sum(item["productive"] for item in daily.values())
    distracted = sum(item["distracting"] for item in daily.values())
    denominator = productive + distracted
    project_rows = list(
        db.session.execute(
            db.select(
                ComputerActivityBlock.project_display_name,
                ComputerActivityBlock.project_key,
                db.func.sum(ComputerActivityBlock.duration_seconds).label("seconds"),
            )
            .where(
                ComputerActivityBlock.record_date.between(start, end),
                ComputerActivityBlock.project_key.is_not(None),
            )
            .group_by(
                ComputerActivityBlock.project_display_name,
                ComputerActivityBlock.project_key,
            )
            .order_by(db.desc("seconds"))
        )
    )
    chatgpt_seconds = int(
        db.session.scalar(
            db.select(db.func.sum(ComputerActivityBlock.duration_seconds)).where(
                ComputerActivityBlock.record_date.between(start, end),
                db.or_(
                    ComputerActivityBlock.executable_name == "chatgpt.exe",
                    ComputerActivityBlock.site_key == "chatgpt",
                ),
            )
        )
        or 0
    )
    return {
        "productive_daily_average_seconds": round(productive / max(period_days, 1)),
        "distracted_daily_average_seconds": round(distracted / max(period_days, 1)),
        "productive_ratio": round(productive / denominator * 100) if denominator else 0,
        "projects": [
            {
                "key": row.project_key,
                "name": row.project_display_name or row.project_key,
                "seconds": int(row.seconds or 0),
            }
            for row in project_rows[:10]
        ],
        "top_project": (
            (project_rows[0].project_display_name or project_rows[0].project_key)
            if project_rows
            else None
        ),
        "chatgpt_seconds": chatgpt_seconds,
        "daily": [
            {
                "date": day.isoformat(),
                "productive_seconds": values["productive"],
                "distracted_seconds": values["distracting"],
            }
            for day, values in sorted(daily.items())
        ],
    }


def get_sleep_evolution(period_days: int = 30) -> dict:
    end = get_local_today()
    start = end - timedelta(days=period_days - 1)
    records = list(
        db.session.scalars(
            db.select(SleepRecord)
            .where(SleepRecord.record_date.between(start, end))
            .order_by(SleepRecord.record_date)
        )
    )
    durations = [item.duration_minutes for item in records if item.duration_minutes]
    imported = sum(item.record_origin in {"health_connect", "merged"} for item in records)
    return {
        "average_minutes": round(sum(durations) / len(durations)) if durations else None,
        "tracked_days": len(records),
        "watch_days": imported,
        "regularity_minutes": (
            round(max(durations) - min(durations)) if len(durations) > 1 else None
        ),
    }


def get_training_evolution(period_days: int = 30) -> dict:
    end = get_local_today()
    start = end - timedelta(days=period_days - 1)
    records = list(
        db.session.scalars(
            db.select(TrainingRecord).where(
                TrainingRecord.record_date.between(start, end)
            )
        )
    )
    duration = sum(item.duration_minutes or 0 for item in records)
    return {
        "sessions": len(records),
        "weekly_average": round(len(records) / max(period_days / 7, 1), 1),
        "duration_minutes": duration,
        "average_duration": round(duration / len(records)) if records else None,
        "distance_meters": round(sum(item.distance_meters or 0 for item in records), 1),
        "types": [
            {"name": name, "count": count}
            for name, count in Counter(item.training_type for item in records).most_common()
        ],
    }


def get_user_identity(profile: UserProfile | None | object = _PROFILE_UNSET) -> dict:
    if profile is _PROFILE_UNSET:
        profile = db.session.scalar(db.select(UserProfile).limit(1))
    name = " ".join((profile.name if profile else "").split()) or "Usuário"
    initials = (
        (profile.avatar_initials or "").strip().upper()
        if profile
        else ""
    ) or "".join(part[0] for part in name.split()[:2]).upper() or "U"
    return {"name": name, "initials": initials}


def update_user_profile(data: dict) -> UserProfile:
    allowed = {
        "name",
        "avatar_initials",
        "academic_goal",
        "physical_goal",
        "weekly_study_minutes",
        "weekly_training_count",
        "sleep_target_minutes",
        "hydration_target_ml",
        "hydration_reminders_enabled",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Campos não reconhecidos: {', '.join(sorted(unknown))}.")
    profile = db.session.scalar(db.select(UserProfile).limit(1))
    if profile is None:
        profile = UserProfile(name="Usuário")
        db.session.add(profile)
    if "name" in data:
        name = " ".join(str(data.get("name") or "").split())
        if not name or len(name) > 120:
            raise ValueError("Informe um nome entre 1 e 120 caracteres.")
        profile.name = name
    if "avatar_initials" in data:
        initials = "".join(str(data.get("avatar_initials") or "").split()).upper()
        if initials and (len(initials) > 4 or not initials.isalnum()):
            raise ValueError("Use até 4 letras ou números nas iniciais.")
        profile.avatar_initials = initials or None
    for field in ("academic_goal", "physical_goal"):
        if field in data:
            value = str(data.get(field) or "").strip()
            if len(value) > 500:
                raise ValueError("Use no máximo 500 caracteres nas metas.")
            setattr(profile, field, value or None)
    for field in (
        "weekly_study_minutes",
        "weekly_training_count",
        "sleep_target_minutes",
        "hydration_target_ml",
    ):
        if field not in data:
            continue
        raw = data.get(field)
        if raw in (None, ""):
            setattr(profile, field, None)
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError("As metas numéricas devem ser números inteiros.") from None
        if value <= 0:
            raise ValueError("As metas numéricas devem ser maiores que zero.")
        setattr(profile, field, value)
    if "hydration_reminders_enabled" in data:
        raw_enabled = data.get("hydration_reminders_enabled")
        if not isinstance(raw_enabled, bool):
            raise ValueError(
                "A preferência de lembrete deve ser verdadeira ou falsa."
            )
        profile.hydration_reminders_enabled = raw_enabled
    db.session.commit()
    db.session.refresh(profile)
    return profile


def get_profile_page_data(period: str = "30d") -> dict:
    start, end, configured_days = _range(period)
    period_days = configured_days or max((end - start).days + 1, 1)
    profile = db.session.scalar(db.select(UserProfile).limit(1))
    if profile is None:
        profile = UserProfile(
            name="Usuário",
            sleep_target_minutes=current_app.config.get(
                "DEFAULT_SLEEP_TARGET_MINUTES", 480
            ),
            hydration_target_ml=current_app.config.get(
                "DEFAULT_HYDRATION_TARGET_ML", 2000
            ),
        )
        db.session.add(profile)
        db.session.commit()
    study = get_study_evolution(period_days)
    physical = get_physical_evolution(period_days)
    training = get_training_evolution(period_days)
    sleep = get_sleep_evolution(period_days)
    computer = get_computer_evolution(period_days)
    first_created = db.session.scalar(
        db.select(db.func.min(StudyRecord.created_at))
    )
    days_using = (
        (datetime.now(timezone.utc).date() - first_created.date()).days + 1
        if first_created
        else 0
    )
    last_import = db.session.scalar(
        db.select(HealthImportRun)
        .where(HealthImportRun.status.in_(("completed", "completed_with_warnings")))
        .order_by(HealthImportRun.finished_at.desc())
        .limit(1)
    )
    dates_with_data = set()
    for model in (StudyRecord, TrainingRecord, SleepRecord, ComputerActivityBlock):
        dates_with_data.update(
            db.session.scalars(
                db.select(model.record_date).where(model.record_date.between(start, end))
            )
        )
    experience = get_experience_summary()
    achievements = get_achievements()
    return {
        "period": period,
        "period_days": period_days,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "profile": {
            "name": profile.name,
            "initials": (
                (profile.avatar_initials or "").upper()
                or "".join(part[0] for part in profile.name.split()[:2]).upper()
            ),
            "academic_goal": profile.academic_goal,
            "physical_goal": profile.physical_goal,
            "days_using": days_using,
            "days_with_data": len(dates_with_data),
            "last_health_sync": (
                last_import.finished_at.isoformat() if last_import else None
            ),
        },
        "study": study,
        "physical": physical,
        "training": training,
        "sleep": sleep,
        "computer": computer,
        "experience": experience,
        "achievements": achievements,
        "goals": {
            "weekly_study_minutes": profile.weekly_study_minutes,
            "weekly_training_count": profile.weekly_training_count,
            "sleep_target_minutes": profile.sleep_target_minutes,
            "hydration_target_ml": profile.hydration_target_ml,
        },
    }


def get_profile_overview() -> dict:
    return get_profile_page_data("30d")


def get_period_comparison(current_start, current_end) -> dict:
    days = (current_end - current_start).days + 1
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    current = _study_between(current_start, current_end)
    previous = _study_between(previous_start, previous_end)
    return {
        "study_minutes": _comparison(
            current["total_minutes"], previous["total_minutes"], "higher"
        ),
        "study_accuracy": _comparison(
            current["accuracy"], previous["accuracy"], "higher"
        ),
    }


def get_routine_evolution(period_days: int = 30) -> dict:
    data = get_profile_page_data(f"{period_days}d" if period_days in (7, 30, 90) else "30d")
    return {
        "days_with_data": data["profile"]["days_with_data"],
        "period_days": data["period_days"],
        "coverage": round(
            data["profile"]["days_with_data"] / max(data["period_days"], 1) * 100
        ),
    }
