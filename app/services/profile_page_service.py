from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean

from flask import current_app

from app.extensions import db
from app.models import (
    AchievementUnlock,
    BodyMeasurement,
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
    UserProfile,
)
from app.services.analytics_utils import (
    format_duration,
    get_app_timezone,
    get_local_today,
)
from app.services.catalog_service import exercise_catalog_item, subject_catalog_item
from app.services.experience_service import (
    ACHIEVEMENTS,
    get_achievements,
    get_experience_summary,
    level_progress,
)
from app.services.profile_service import FOCUS_PERCENT, PERIOD_DAYS, xp_for_record
from app.services.watch_service import sleep_stage_data


PROFILE_TABS = (
    ("overview", "Visão geral"),
    ("study", "Estudos"),
    ("health", "Corpo e saúde"),
    ("training", "Treinos"),
    ("sleep", "Sono"),
    ("computer", "Computador"),
    ("achievements", "Conquistas"),
    ("goals", "Metas"),
)
PERIOD_LABELS = {
    "7d": "7 dias",
    "30d": "30 dias",
    "90d": "90 dias",
    "6m": "6 meses",
    "1y": "1 ano",
    "all": "Todo o período",
}
ACHIEVEMENT_FILTERS = (
    ("all", "Geral"),
    ("Estudos", "Estudos"),
    ("Treinos", "Treinos"),
    ("Sono", "Sono"),
    ("Computador", "Computador"),
    ("Saúde", "Saúde"),
    ("Rotina", "Rotina"),
)


def normalize_tab(value: str | None) -> str:
    keys = {item[0] for item in PROFILE_TABS}
    return value if value in keys else "overview"


def normalize_period(value: str | None) -> str:
    return value if value in PERIOD_LABELS else "30d"


def _ensure_profile() -> UserProfile:
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
    return profile


def _range(period: str) -> tuple[date, date, int]:
    end = get_local_today()
    if period != "all":
        days = PERIOD_DAYS.get(period, 30)
        return end - timedelta(days=days - 1), end, days
    candidates = []
    for model in (
        StudyRecord,
        TrainingRecord,
        SleepRecord,
        ComputerActivityBlock,
        MealRecord,
        HydrationRecord,
        DailyHealthSummary,
    ):
        first = db.session.scalar(db.select(db.func.min(model.record_date)))
        if first:
            candidates.append(first)
    first_measurement = db.session.scalar(
        db.select(db.func.min(BodyMeasurement.measured_at))
    )
    if first_measurement:
        candidates.append(first_measurement.date())
    start = min(candidates, default=end)
    return start, end, max((end - start).days + 1, 1)


def _windows(period: str) -> tuple[date, date, date, date, int]:
    start, end, days = _range(period)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    return start, end, previous_start, previous_end, days


def _current_streak() -> int:
    tracked = set()
    for model in (
        StudyRecord,
        TrainingRecord,
        SleepRecord,
        ComputerActivityBlock,
        MealRecord,
        HydrationRecord,
    ):
        tracked.update(db.session.scalars(db.select(model.record_date)))
    if not tracked:
        return 0
    cursor = get_local_today()
    if cursor not in tracked:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor in tracked:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _comparison(current, previous, direction: str | None = None) -> dict:
    if current is None or previous is None:
        return {
            "current": current,
            "previous": previous,
            "difference": None,
            "percentage": None,
            "trend": "insufficient_data",
        }
    difference = round(float(current) - float(previous), 2)
    percentage = round(difference / abs(float(previous)) * 100, 1) if previous else None
    if abs(difference) < 0.01 or direction is None:
        trend = "variation"
    elif (direction == "higher" and difference > 0) or (
        direction == "lower" and difference < 0
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


def _count_label(value: int, singular: str, plural: str | None = None) -> str:
    return f"{value} {singular if value == 1 else (plural or singular + 's')}"


def _datetime_label(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(get_app_timezone()).strftime("%d/%m/%Y às %H:%M")


def get_profile_header(period: str) -> dict:
    profile = _ensure_profile()
    experience = get_experience_summary()
    name = " ".join((profile.name or "").split()) or "Usuário"
    initials = (
        (profile.avatar_initials or "").strip().upper()
        or "".join(part[0] for part in name.split()[:2]).upper()
        or "U"
    )
    return {
        "name": name,
        "initials": initials,
        "academic_goal": profile.academic_goal,
        "physical_goal": profile.physical_goal,
        "level": experience["level"],
        "total_xp": experience["total_xp"],
        "current_xp": experience["current_xp"],
        "next_level_xp": experience["next_level_xp"],
        "progress_percent": experience["progress_percent"],
        "current_streak": _current_streak(),
        "period": period,
        "period_label": PERIOD_LABELS[period],
    }


def _tracked_dates(start: date, end: date) -> dict[str, set[date]]:
    data = {}
    for key, model in (
        ("study", StudyRecord),
        ("training", TrainingRecord),
        ("sleep", SleepRecord),
        ("nutrition", MealRecord),
        ("computer", ComputerActivityBlock),
    ):
        data[key] = set(
            db.session.scalars(
                db.select(model.record_date).where(model.record_date.between(start, end))
            )
        )
    data["nutrition"].update(
        db.session.scalars(
            db.select(HydrationRecord.record_date).where(
                HydrationRecord.record_date.between(start, end)
            )
        )
    )
    return data


def _coverage(start: date, end: date) -> dict[str, int]:
    days = max((end - start).days + 1, 1)
    dates = _tracked_dates(start, end)
    return {key: round(len(value) / days * 100) for key, value in dates.items()}


def get_experience_timeline(limit: int = 5) -> list[dict]:
    events = list(
        db.session.scalars(
            db.select(ExperienceEvent)
            .order_by(ExperienceEvent.earned_at.desc(), ExperienceEvent.id.desc())
            .limit(max(1, min(limit, 50)))
        )
    )
    achievement_names = {item[0]: item[1] for item in ACHIEVEMENTS}
    source_ids: dict[str, set[int]] = defaultdict(set)
    for event in events:
        if event.source_id:
            source_ids[event.source_type].add(event.source_id)
    studies = {
        item.id: item
        for item in db.session.scalars(
            db.select(StudyRecord).where(StudyRecord.id.in_(source_ids["study"]))
        )
    } if source_ids["study"] else {}
    trainings = {
        item.id: item
        for item in db.session.scalars(
            db.select(TrainingRecord).where(TrainingRecord.id.in_(source_ids["training"]))
        )
    } if source_ids["training"] else {}
    sessions = {
        item.id: item
        for item in db.session.scalars(
            db.select(SessionRecord).where(SessionRecord.id.in_(source_ids["session"]))
        )
    } if source_ids["session"] else {}
    result = []
    for event in events:
        icon = "sparkles"
        label = "Progresso registrado"
        if event.event_type == "achievement":
            key = event.event_key.removeprefix("achievement:")
            label = f"Conquista: {achievement_names.get(key, 'Conquista desbloqueada')}"
            icon = "trophy"
        elif event.event_type == "study_record":
            record = studies.get(event.source_id)
            label = f"Sessão de {record.subject}" if record else "Sessão de estudo"
            icon = "book-open"
        elif event.event_type == "training_record":
            record = trainings.get(event.source_id)
            catalog = (
                exercise_catalog_item(
                    code=record.source_exercise_type,
                    key=record.manual_training_type or record.training_type,
                )
                if record
                else None
            )
            label = f"Treino: {catalog['display_name']}" if catalog else "Treino concluído"
            icon = "dumbbell"
        elif event.event_type == "sleep_complete":
            label, icon = "Registro de sono completo", "moon-star"
        elif event.event_type == "session_completed":
            record = sessions.get(event.source_id)
            label = record.title if record else "Sessão de foco concluída"
            icon = "timer"
        elif event.event_type == "full_day":
            label, icon = "Dia completo", "circle-check-big"
        result.append(
            {
                "label": label,
                "icon": icon,
                "xp": event.xp_amount,
                "date": event.record_date.isoformat(),
                "date_label": event.record_date.strftime("%d/%m/%Y"),
            }
        )
    return result


def get_overview_data(period: str) -> dict:
    start, end, previous_start, previous_end, days = _windows(period)
    current_dates = _tracked_dates(start, end)
    previous_dates = _tracked_dates(previous_start, previous_end)
    study_minutes = int(
        db.session.scalar(
            db.select(db.func.sum(StudyRecord.duration_minutes)).where(
                StudyRecord.record_date.between(start, end)
            )
        )
        or 0
    )
    training_count = int(
        db.session.scalar(
            db.select(db.func.count(TrainingRecord.id)).where(
                TrainingRecord.record_date.between(start, end)
            )
        )
        or 0
    )
    productive = int(
        db.session.scalar(
            db.select(db.func.sum(ComputerActivityBlock.duration_seconds)).where(
                ComputerActivityBlock.record_date.between(start, end),
                ComputerActivityBlock.was_idle.is_(False),
                ComputerActivityBlock.classification == "productive",
            )
        )
        or 0
    )
    coverage = _coverage(start, end)
    previous_coverage = _coverage(previous_start, previous_end)
    deltas = {
        key: coverage[key] - previous_coverage[key]
        for key in coverage
    }
    strongest = max(deltas, key=deltas.get) if deltas and max(deltas.values()) > 0 else None
    regular = max(coverage, key=coverage.get) if coverage and max(coverage.values()) > 0 else None
    labels = {
        "study": "Estudos",
        "training": "Treinos",
        "sleep": "Sono",
        "nutrition": "Alimentação",
        "computer": "Computador",
    }
    tracked_union = set().union(*current_dates.values())
    previous_union = set().union(*previous_dates.values())
    average_coverage = round(mean(coverage.values())) if coverage else 0
    previous_average = round(mean(previous_coverage.values())) if previous_coverage else 0
    sleep_days = len(current_dates["sleep"])
    summary = (
        f"Nos últimos {days} dias: estudou em "
        f"{_count_label(len(current_dates['study']), 'dia')}; concluiu "
        f"{_count_label(training_count, 'treino')}; teve "
        f"{_count_label(sleep_days, 'noite')} "
        f"{'acompanhada' if sleep_days == 1 else 'acompanhadas'}; registrou "
        f"{_count_label(len(tracked_union), 'dia')}; teve média de "
        f"{format_duration(round(productive / max(len(current_dates['computer']), 1) / 60))} "
        "produtivas por dia monitorado."
    )
    highlights = []
    if strongest:
        highlights.append(
            {
                "label": "Maior evolução",
                "value": labels[strongest],
                "detail": f"{deltas[strongest]:+d} p.p. de cobertura",
            }
        )
    if regular:
        highlights.append(
            {
                "label": "Categoria mais regular",
                "value": labels[regular],
                "detail": f"{coverage[regular]}% de cobertura",
            }
        )
    top_project = db.session.execute(
        db.select(
            ComputerActivityBlock.project_display_name,
            ComputerActivityBlock.project_key,
            db.func.sum(ComputerActivityBlock.duration_seconds).label("seconds"),
        )
        .where(
            ComputerActivityBlock.record_date.between(start, end),
            ComputerActivityBlock.project_key.is_not(None),
            ComputerActivityBlock.was_idle.is_(False),
        )
        .group_by(
            ComputerActivityBlock.project_display_name,
            ComputerActivityBlock.project_key,
        )
        .order_by(db.desc("seconds"))
        .limit(1)
    ).first()
    if top_project:
        highlights.append(
            {
                "label": "Projeto mais trabalhado",
                "value": top_project.project_display_name or top_project.project_key,
                "detail": format_duration(round((top_project.seconds or 0) / 60)),
            }
        )
    return {
        "has_data": bool(tracked_union),
        "metrics": [
            {"label": "Dias acompanhados", "value": str(len(tracked_union)), "detail": f"de {days} dias"},
            {"label": "Tempo estudado", "value": format_duration(study_minutes), "detail": _count_label(len(current_dates["study"]), "dia")},
            {"label": "Treinos", "value": str(training_count), "detail": f"{len(current_dates['training'])} dias ativos"},
            {"label": "Sono acompanhado", "value": f"{len(current_dates['sleep'])} noites", "detail": "registros no período"},
            {"label": "Média produtiva", "value": format_duration(round(productive / max(len(current_dates['computer']), 1) / 60)), "detail": "por dia monitorado"},
            {"label": "Consistência geral", "value": f"{average_coverage}%", "detail": "cobertura média"},
            {"label": "Maior evolução", "value": labels.get(strongest, "Dados insuficientes"), "detail": "versus período anterior"},
            {"label": "Mais regular", "value": labels.get(regular, "Dados insuficientes"), "detail": "no período"},
        ],
        "summary": summary if tracked_union else "Dados insuficientes para comparar este período.",
        "coverage": {
            "labels": [labels[key] for key in coverage],
            "current": list(coverage.values()),
            "previous": [previous_coverage[key] for key in coverage],
        },
        "comparison": _comparison(average_coverage, previous_average, "higher"),
        "highlights": highlights[:3],
        "xp_timeline": get_experience_timeline(5),
    }


def _study_summary(start: date, end: date) -> dict:
    records = list(
        db.session.scalars(
            db.select(StudyRecord).where(StudyRecord.record_date.between(start, end))
        )
    )
    minutes = sum(item.duration_minutes or 0 for item in records)
    questions = sum(item.questions_count or 0 for item in records)
    correct = sum(item.correct_answers or 0 for item in records)
    focus_values = [
        FOCUS_PERCENT[str(item.focus_quality or "").casefold()]
        for item in records
        if str(item.focus_quality or "").casefold() in FOCUS_PERCENT
    ]
    return {
        "records": records,
        "minutes": minutes,
        "sessions": len(records),
        "days": len({item.record_date for item in records}),
        "focus": round(mean(focus_values)) if focus_values else None,
        "questions": questions,
        "accuracy": round(correct / questions * 100) if questions else None,
    }


def get_study_profile_data(period: str) -> dict:
    start, end, previous_start, previous_end, _ = _windows(period)
    current = _study_summary(start, end)
    previous = _study_summary(previous_start, previous_end)
    all_records = list(
        db.session.scalars(
            db.select(StudyRecord).order_by(StudyRecord.record_date.desc(), StudyRecord.id.desc())
        )
    )
    grouped: dict[str, dict] = {}
    for record in all_records:
        key = record.subject.strip().casefold()
        item = grouped.setdefault(
            key,
            {
                "name": record.subject.strip(),
                "xp": 0,
                "minutes": 0,
                "sessions": 0,
                "questions": 0,
                "correct": 0,
                "last": record.record_date,
            },
        )
        item["xp"] += xp_for_record(record)
        item["minutes"] += record.duration_minutes or 0
        item["sessions"] += 1
        item["questions"] += record.questions_count or 0
        item["correct"] += record.correct_answers or 0
        item["last"] = max(item["last"], record.record_date)
    subjects = []
    for item in grouped.values():
        progress = level_progress(item["xp"])
        catalog = subject_catalog_item(item["name"])
        subjects.append(
            {
                **item,
                "display_name": catalog["display_name"],
                "color": catalog["color"],
                "level": progress["level"],
                "current_xp": progress["current_xp"],
                "next_level_xp": progress["next_level_xp"],
                "progress_percent": progress["progress_percent"],
                "duration": format_duration(item["minutes"]),
                "accuracy": round(item["correct"] / item["questions"] * 100)
                if item["questions"]
                else None,
                "last": item["last"].isoformat(),
            }
        )
    subjects.sort(key=lambda item: (-date.fromisoformat(item["last"]).toordinal(), -item["xp"], item["display_name"]))
    weeks = []
    cursor = start - timedelta(days=start.weekday())
    while cursor <= end:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    by_subject = defaultdict(lambda: defaultdict(int))
    for record in current["records"]:
        week = record.record_date - timedelta(days=record.record_date.weekday())
        by_subject[record.subject.strip().casefold()][week] += record.duration_minutes or 0
    datasets = []
    for item in subjects:
        key = item["name"].casefold()
        values = [by_subject[key][week] for week in weeks]
        if any(values):
            datasets.append(
                {
                    "label": item["display_name"],
                    "data": values,
                    "backgroundColor": item["color"],
                }
            )
    return {
        "has_data": bool(current["records"]),
        "metrics": [
            {"label": "Tempo estudado", "value": format_duration(current["minutes"])},
            {"label": "Sessões", "value": current["sessions"]},
            {"label": "Dias estudados", "value": current["days"]},
            {"label": "Foco médio", "value": f"{current['focus']}%" if current["focus"] is not None else "Sem dados"},
            {"label": "Questões", "value": current["questions"]},
            {"label": "Taxa de acertos", "value": f"{current['accuracy']}%" if current["accuracy"] is not None else "Sem dados"},
        ],
        "comparison": _comparison(current["minutes"], previous["minutes"], "higher"),
        "chart": {
            "labels": [week.strftime("%d/%m") for week in weeks],
            "datasets": datasets,
        },
        "subjects": subjects,
    }


def get_health_profile_data(period: str) -> dict:
    start, end, _, _, _ = _windows(period)
    measurements = list(
        db.session.scalars(
            db.select(BodyMeasurement)
            .where(db.func.date(BodyMeasurement.measured_at).between(start, end))
            .order_by(BodyMeasurement.measured_at)
        )
    )
    summaries = list(
        db.session.scalars(
            db.select(DailyHealthSummary)
            .where(DailyHealthSummary.record_date.between(start, end))
            .order_by(DailyHealthSummary.record_date)
        )
    )
    weights = [item for item in measurements if item.weight_kg is not None]
    weight_points = []
    for index, item in enumerate(weights):
        window = [entry.weight_kg for entry in weights[max(0, index - 6): index + 1]]
        weight_points.append(
            {
                "date": item.measured_at.date().isoformat(),
                "weight": round(item.weight_kg, 2),
                "rolling": round(mean(window), 2),
            }
        )
    def latest(attr, rows):
        return next((getattr(item, attr) for item in reversed(rows) if getattr(item, attr) is not None), None)
    steps = [item.steps for item in summaries if item.steps is not None]
    calories = [item.active_calories for item in summaries if item.active_calories is not None]
    distances = [item.distance_meters for item in summaries if item.distance_meters is not None]
    heart_rates = [item.average_heart_rate for item in summaries if item.average_heart_rate is not None]
    metrics = []
    current_weight = weights[-1].weight_kg if weights else None
    first_weight = weights[0].weight_kg if weights else None
    candidates = (
        ("Peso atual", current_weight, "kg"),
        ("Variação no período", round(current_weight - first_weight, 2) if current_weight is not None and first_weight is not None else None, "kg"),
        ("Gordura corporal", latest("body_fat_percentage", measurements), "%"),
        ("Passos médios", round(mean(steps)) if steps else None, "passos/dia"),
        ("VO₂ máximo", latest("vo2_max", summaries), "ml/kg/min"),
        ("FC de repouso", latest("resting_heart_rate", summaries), "bpm"),
    )
    for label, value, unit in candidates:
        if value is not None:
            metrics.append({"label": label, "value": value, "unit": unit})
    last_import = db.session.scalar(
        db.select(HealthImportRun)
        .where(HealthImportRun.status.in_(("completed", "completed_with_warnings")))
        .order_by(HealthImportRun.finished_at.desc())
        .limit(1)
    )
    return {
        "has_data": bool(measurements or summaries),
        "metrics": metrics,
        "weight": {
            "points": weight_points,
            "first": first_weight,
            "latest": current_weight,
            "difference": round(current_weight - first_weight, 2) if current_weight is not None and first_weight is not None else None,
        },
        "watch": {
            "source": "Galaxy Watch via Health Connect",
            "last_sync": (
                last_import.finished_at.isoformat()
                if last_import and last_import.finished_at
                else None
            ),
            "last_sync_label": (
                _datetime_label(last_import.finished_at) if last_import else None
            ),
            "days": len(summaries),
            "average_steps": round(mean(steps)) if steps else None,
            "average_active_calories": round(mean(calories)) if calories else None,
            "distance_km": round(sum(distances) / 1000, 1) if distances else None,
            "average_heart_rate": round(mean(heart_rates)) if heart_rates else None,
        },
    }


def _training_summary(start: date, end: date) -> dict:
    records = list(
        db.session.scalars(
            db.select(TrainingRecord)
            .where(TrainingRecord.record_date.between(start, end))
            .order_by(TrainingRecord.record_date)
        )
    )
    duration = sum(item.duration_minutes or 0 for item in records)
    return {
        "records": records,
        "sessions": len(records),
        "duration": duration,
        "distance": sum(item.distance_meters or 0 for item in records),
    }


def get_training_profile_data(period: str) -> dict:
    start, end, previous_start, previous_end, days = _windows(period)
    current = _training_summary(start, end)
    previous = _training_summary(previous_start, previous_end)
    modalities: dict[str, dict] = {}
    daily = defaultdict(lambda: {"sessions": 0, "minutes": 0})
    heart_rates = []
    for record in current["records"]:
        catalog = exercise_catalog_item(
            code=record.source_exercise_type,
            key=record.manual_training_type or record.training_type,
        )
        key = catalog["training_key"]
        item = modalities.setdefault(
            key,
            {"name": catalog["display_name"], "color": catalog["color"], "sessions": 0, "minutes": 0, "distance": 0},
        )
        item["sessions"] += 1
        item["minutes"] += record.duration_minutes or 0
        item["distance"] += record.distance_meters or 0
        daily[record.record_date]["sessions"] += 1
        daily[record.record_date]["minutes"] += record.duration_minutes or 0
        if record.average_heart_rate is not None:
            heart_rates.append(record.average_heart_rate)
    ordered_modalities = sorted(modalities.values(), key=lambda item: (-item["sessions"], item["name"]))
    return {
        "has_data": bool(current["records"]),
        "metrics": [
            {"label": "Treinos", "value": current["sessions"]},
            {"label": "Duração total", "value": format_duration(current["duration"])},
            {"label": "Média semanal", "value": f"{current['sessions'] / max(days / 7, 1):.1f}"},
            {"label": "Modalidade principal", "value": ordered_modalities[0]["name"] if ordered_modalities else "Sem dados"},
            {"label": "Distância", "value": f"{current['distance'] / 1000:.1f} km"},
            {"label": "FC média", "value": f"{round(mean(heart_rates))} bpm" if heart_rates else "Sem dados"},
        ],
        "comparison": _comparison(current["sessions"], previous["sessions"], "higher"),
        "daily": [
            {"date": day.isoformat(), **values}
            for day, values in sorted(daily.items())
        ],
        "modalities": ordered_modalities,
    }


def get_sleep_profile_data(period: str) -> dict:
    start, end, previous_start, previous_end, _ = _windows(period)
    records = list(
        db.session.scalars(
            db.select(SleepRecord)
            .where(SleepRecord.record_date.between(start, end))
            .order_by(SleepRecord.record_date)
        )
    )
    previous = list(
        db.session.scalars(
            db.select(SleepRecord).where(SleepRecord.record_date.between(previous_start, previous_end))
        )
    )
    durations = [item.duration_minutes for item in records]
    bedtimes = [item.sleep_start.hour * 60 + item.sleep_start.minute for item in records if item.sleep_start]
    wakes = [item.sleep_end.hour * 60 + item.sleep_end.minute for item in records if item.sleep_end]
    stage_totals = Counter()
    efficiencies = []
    for record in records:
        stage = sleep_stage_data(record)
        if record.sleep_stages_json:
            efficiencies.append(stage["efficiency_percent"])
        for item in stage["items"]:
            stage_totals[item["key"]] += item["minutes"]
    stage_sum = sum(stage_totals.values())
    stages = [
        {"key": key, "label": label, "minutes": stage_totals[key], "percent": round(stage_totals[key] / stage_sum * 100) if stage_sum else 0}
        for key, label in (("light", "Sono leve"), ("deep", "Sono profundo"), ("rem", "Sono REM"), ("awake", "Acordado"))
        if stage_totals[key]
    ]
    def clock_label(values):
        if not values:
            return None
        value = round(mean(values)) % 1440
        return f"{value // 60:02d}:{value % 60:02d}"
    average_minutes = round(mean(durations)) if durations else None
    previous_average = round(mean([item.duration_minutes for item in previous])) if previous else None
    return {
        "has_data": bool(records),
        "metrics": [
            {"label": "Duração média", "value": format_duration(average_minutes) if average_minutes is not None else "Sem dados"},
            {"label": "Horário de dormir", "value": clock_label(bedtimes) or "Sem dados"},
            {"label": "Horário de acordar", "value": clock_label(wakes) or "Sem dados"},
            {"label": "Eficiência média", "value": f"{round(mean(efficiencies))}%" if efficiencies else "Sem dados"},
            {"label": "Noites acompanhadas", "value": len(records)},
            {"label": "Completadas manualmente", "value": sum(item.perceived_quality is not None and item.woke_restored is not None for item in records)},
        ],
        "comparison": _comparison(average_minutes, previous_average),
        "daily": [{"date": item.record_date.isoformat(), "minutes": item.duration_minutes, "start": item.sleep_start.strftime("%H:%M"), "end": item.sleep_end.strftime("%H:%M")} for item in records],
        "stages": stages,
    }


def get_computer_profile_data(period: str) -> dict:
    start, end, previous_start, previous_end, _ = _windows(period)
    blocks = list(
        db.session.scalars(
            db.select(ComputerActivityBlock).where(
                ComputerActivityBlock.record_date.between(start, end),
                ComputerActivityBlock.was_idle.is_(False),
            )
        )
    )
    previous_distracting = int(
        db.session.scalar(
            db.select(db.func.sum(ComputerActivityBlock.duration_seconds)).where(
                ComputerActivityBlock.record_date.between(previous_start, previous_end),
                ComputerActivityBlock.was_idle.is_(False),
                ComputerActivityBlock.classification == "distracting",
            )
        ) or 0
    )
    daily = defaultdict(lambda: {"productive": 0, "distracting": 0})
    categories = Counter()
    apps = {"productive": Counter(), "distracting": Counter()}
    projects = Counter()
    chatgpt = 0
    vscode = 0
    for item in blocks:
        seconds = item.duration_seconds or 0
        if item.classification in daily[item.record_date]:
            daily[item.record_date][item.classification] += seconds
        categories[item.category] += seconds
        if item.classification in apps:
            apps[item.classification][item.friendly_name or item.executable_name] += seconds
        if item.project_key:
            projects[item.project_display_name or item.project_key] += seconds
        if item.executable_name == "chatgpt.exe" or item.site_key == "chatgpt":
            chatgpt += seconds
        if item.executable_name and item.executable_name.casefold() in {"code.exe", "visual studio code.exe"}:
            vscode += seconds
    productive = sum(item["productive"] for item in daily.values())
    distracting = sum(item["distracting"] for item in daily.values())
    total = sum(item.duration_seconds or 0 for item in blocks)
    monitored_days = len(daily)
    focused_sessions = int(
        db.session.scalar(
            db.select(db.func.count(SessionRecord.id)).where(
                SessionRecord.record_date.between(start, end),
                SessionRecord.status == "completed",
            )
        ) or 0
    )
    return {
        "has_data": bool(blocks),
        "metrics": [
            {"label": "Tempo total", "value": format_duration(round(total / 60))},
            {"label": "Média produtiva", "value": format_duration(round(productive / max(monitored_days, 1) / 60))},
            {"label": "Média de distração", "value": format_duration(round(distracting / max(monitored_days, 1) / 60))},
            {"label": "Proporção produtiva", "value": f"{round(productive / max(productive + distracting, 1) * 100)}%"},
            {"label": "Dias monitorados", "value": monitored_days},
            {"label": "Sessões focadas", "value": focused_sessions},
        ],
        "comparison": _comparison(distracting, previous_distracting, "lower"),
        "daily": [{"date": day.isoformat(), **values} for day, values in sorted(daily.items())],
        "categories": [{"name": name, "seconds": seconds} for name, seconds in categories.most_common()],
        "projects": [{"name": name, "seconds": seconds} for name, seconds in projects.most_common(8)],
        "top_project": projects.most_common(1)[0][0] if projects else None,
        "top_productive_app": apps["productive"].most_common(1)[0][0] if apps["productive"] else None,
        "top_distracting_app": apps["distracting"].most_common(1)[0][0] if apps["distracting"] else None,
        "chatgpt_seconds": chatgpt,
        "vscode_seconds": vscode,
    }


def get_achievements_profile_data(
    category: str = "all",
    status: str = "all",
    *,
    sync: bool = True,
) -> dict:
    achievements = get_achievements(sync=sync)
    valid_categories = {item[0] for item in ACHIEVEMENT_FILTERS}
    category = category if category in valid_categories else "all"
    status = status if status in {"all", "unlocked", "next"} else "all"
    filtered = [
        item for item in achievements
        if (category == "all" or item["category"] == category)
        and (status == "all" or (status == "unlocked" and item["unlocked"]) or (status == "next" and not item["unlocked"]))
    ]
    unlocked = [item for item in achievements if item["unlocked"]]
    latest = max(
        unlocked,
        key=lambda item: item["unlocked_at"] or "",
        default=None,
    )
    xp_received = int(
        db.session.scalar(
            db.select(db.func.sum(ExperienceEvent.xp_amount)).where(
                ExperienceEvent.event_type == "achievement"
            )
        ) or 0
    )
    filtered.sort(key=lambda item: (not item["unlocked"], -item["progress_percent"], item["name"]))
    return {
        "has_data": bool(achievements),
        "category": category,
        "status": status,
        "filters": ACHIEVEMENT_FILTERS,
        "summary": {
            "unlocked": len(unlocked),
            "available": len(achievements),
            "xp_received": xp_received,
            "latest": latest["name"] if latest else None,
        },
        "items": filtered,
    }


def get_goals_profile_data() -> dict:
    profile = _ensure_profile()
    today = get_local_today()
    week_start = today - timedelta(days=today.weekday())
    study_minutes = int(
        db.session.scalar(
            db.select(db.func.sum(StudyRecord.duration_minutes)).where(
                StudyRecord.record_date.between(week_start, today)
            )
        ) or 0
    )
    training_count = int(
        db.session.scalar(
            db.select(db.func.count(TrainingRecord.id)).where(
                TrainingRecord.record_date.between(week_start, today)
            )
        ) or 0
    )
    sleep_average = db.session.scalar(
        db.select(db.func.avg(SleepRecord.duration_minutes)).where(
            SleepRecord.record_date.between(week_start, today)
        )
    )
    hydration_today = int(
        db.session.scalar(
            db.select(db.func.sum(HydrationRecord.amount_ml)).where(
                HydrationRecord.record_date == today
            )
        ) or 0
    )
    def progress(actual, target):
        return min(100, round(actual / target * 100)) if target else None
    return {
        "has_data": True,
        "profile_values": {
            "name": profile.name,
            "initials": profile.avatar_initials or "",
            "academic_goal": profile.academic_goal or "",
            "physical_goal": profile.physical_goal or "",
        },
        "goal_values": {
            "weekly_study_minutes": profile.weekly_study_minutes,
            "weekly_training_count": profile.weekly_training_count,
            "sleep_target_minutes": profile.sleep_target_minutes,
            "hydration_target_ml": profile.hydration_target_ml,
        },
        "cards": [
            {"key": "weekly_study_minutes", "title": "Estudo semanal", "target": profile.weekly_study_minutes, "target_label": f"{profile.weekly_study_minutes} min" if profile.weekly_study_minutes else "Não definida", "actual_label": f"{study_minutes} min realizados", "progress": progress(study_minutes, profile.weekly_study_minutes)},
            {"key": "weekly_training_count", "title": "Treinos por semana", "target": profile.weekly_training_count, "target_label": f"{profile.weekly_training_count} treinos" if profile.weekly_training_count else "Não definida", "actual_label": f"{training_count} realizados", "progress": progress(training_count, profile.weekly_training_count)},
            {"key": "sleep_target_minutes", "title": "Sono", "target": profile.sleep_target_minutes, "target_label": format_duration(profile.sleep_target_minutes) if profile.sleep_target_minutes else "Não definida", "actual_label": f"{format_duration(round(sleep_average))} em média" if sleep_average else "Sem noites nesta semana", "progress": progress(float(sleep_average or 0), profile.sleep_target_minutes)},
            {"key": "hydration_target_ml", "title": "Hidratação", "target": profile.hydration_target_ml, "target_label": f"{profile.hydration_target_ml} ml" if profile.hydration_target_ml else "Não definida", "actual_label": f"{hydration_today} ml hoje", "progress": progress(hydration_today, profile.hydration_target_ml)},
            {"key": "academic_goal", "title": "Objetivo acadêmico", "target": profile.academic_goal, "target_label": profile.academic_goal or "Não definido", "actual_label": None, "progress": None},
            {"key": "physical_goal", "title": "Objetivo físico", "target": profile.physical_goal, "target_label": profile.physical_goal or "Não definido", "actual_label": None, "progress": None},
        ],
    }


def get_profile_page_data(
    period: str = "30d",
    tab: str = "overview",
    *,
    achievement_category: str = "all",
    achievement_status: str = "all",
) -> dict:
    period = normalize_period(period)
    tab = normalize_tab(tab)
    header = get_profile_header(period)
    loaders = {
        "overview": lambda: get_overview_data(period),
        "study": lambda: get_study_profile_data(period),
        "health": lambda: get_health_profile_data(period),
        "training": lambda: get_training_profile_data(period),
        "sleep": lambda: get_sleep_profile_data(period),
        "computer": lambda: get_computer_profile_data(period),
        "achievements": lambda: get_achievements_profile_data(
            achievement_category, achievement_status, sync=False
        ),
        "goals": get_goals_profile_data,
    }
    return {
        "tab": tab,
        "period": period,
        "period_label": PERIOD_LABELS[period],
        "tabs": PROFILE_TABS,
        "periods": tuple(PERIOD_LABELS.items()),
        "header": header,
        "content": loaders[tab](),
    }
