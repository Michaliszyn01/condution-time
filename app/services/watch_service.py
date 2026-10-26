from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from app.extensions import db
from app.models import SleepRecord, TrainingRecord
from app.services.analytics_utils import format_duration, get_app_timezone
from app.services.catalog_service import exercise_catalog_item


SLEEP_STAGE_META = {
    0: ("unknown", "Sem classificação", "#94A3B8"),
    1: ("awake", "Acordado", "#F59E0B"),
    2: ("unknown_sleep", "Sono sem classificação", "#94A3B8"),
    3: ("out_of_bed", "Fora da cama", "#F97316"),
    4: ("light", "Sono leve", "#60A5FA"),
    5: ("deep", "Sono profundo", "#4338CA"),
    6: ("rem", "Sono REM", "#A855F7"),
    7: ("awake_in_bed", "Acordado na cama", "#FBBF24"),
}


def _local_label(value: datetime | None, pattern: str = "%H:%M") -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        from datetime import timezone

        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(get_app_timezone()).strftime(pattern)


def sleep_stage_data(record: SleepRecord) -> dict:
    totals = defaultdict(int)
    timeline = []
    try:
        stages = json.loads(record.sleep_stages_json or "[]")
    except (TypeError, ValueError):
        stages = []
    for stage in stages:
        try:
            started = datetime.fromisoformat(stage["start"])
            ended = datetime.fromisoformat(stage["end"])
            duration_seconds = max(0, round((ended - started).total_seconds()))
            stage_type = int(stage["type"])
        except (KeyError, TypeError, ValueError):
            continue
        key, label, color = SLEEP_STAGE_META.get(
            stage_type,
            SLEEP_STAGE_META[0],
        )
        totals[key] += duration_seconds
        timeline.append(
            {
                "key": key,
                "label": label,
                "color": color,
                "started_at": _local_label(started),
                "ended_at": _local_label(ended),
                "duration_minutes": round(duration_seconds / 60),
                "duration": format_duration(round(duration_seconds / 60)),
            }
        )
    total_session_seconds = max(record.duration_minutes * 60, 1)
    awake_seconds = totals["awake"] + totals["awake_in_bed"] + totals["out_of_bed"]
    sleeping_seconds = (
        totals["unknown_sleep"] + totals["light"] + totals["deep"] + totals["rem"]
    )
    summaries = []
    for key, label, color in (
        ("awake", "Tempo acordado", "#F59E0B"),
        ("light", "Sono leve", "#60A5FA"),
        ("deep", "Sono profundo", "#4338CA"),
        ("rem", "Sono REM", "#A855F7"),
    ):
        seconds = awake_seconds if key == "awake" else totals[key]
        minutes = round(seconds / 60)
        summaries.append(
            {
                "key": key,
                "label": label,
                "color": color,
                "minutes": minutes,
                "duration": format_duration(minutes),
                "percentage": round(seconds / total_session_seconds * 100),
            }
        )
    unclassified = round(
        (totals["unknown"] + totals["unknown_sleep"]) / 60
    )
    return {
        "items": summaries,
        "timeline": timeline,
        "unclassified_minutes": unclassified,
        "unclassified": format_duration(unclassified),
        "sleeping_minutes": round(sleeping_seconds / 60),
        "awake_minutes": round(awake_seconds / 60),
        "efficiency_percent": round(sleeping_seconds / total_session_seconds * 100),
    }


def serialize_training_suggestion(record: TrainingRecord) -> dict:
    catalog = (
        exercise_catalog_item(key=record.manual_training_type)
        if record.manual_training_type
        else exercise_catalog_item(
            code=record.source_exercise_type,
            key=record.training_type,
        )
    )
    return {
        "id": record.id,
        "record_date": record.record_date.isoformat(),
        "date_label": record.record_date.strftime("%d/%m/%Y"),
        "training_type": catalog["training_key"],
        "training_type_label": catalog["display_name"],
        "activity_name": record.activity_name,
        "started_at": _local_label(record.training_started_at),
        "ended_at": _local_label(record.training_ended_at),
        "duration_minutes": record.duration_minutes,
        "duration": format_duration(record.duration_minutes),
        "distance_meters": record.distance_meters,
        "distance_km": (
            round(record.distance_meters / 1000, 2)
            if record.distance_meters is not None
            else None
        ),
        "calories": round(record.calories) if record.calories is not None else None,
        "average_heart_rate": (
            round(record.average_heart_rate)
            if record.average_heart_rate is not None
            else None
        ),
        "maximum_heart_rate": (
            round(record.maximum_heart_rate)
            if record.maximum_heart_rate is not None
            else None
        ),
        "steps": record.steps,
        "origin": "Galaxy Watch via Health Connect",
        "status": record.suggestion_status or "available",
        "status_label": (
            "Informações manuais completas"
            if record.suggestion_status == "completed"
            else "Disponível para completar"
        ),
    }


def serialize_sleep_suggestion(record: SleepRecord) -> dict:
    return {
        "id": record.id,
        "record_date": record.record_date.isoformat(),
        "date_label": record.record_date.strftime("%d/%m/%Y"),
        "sleep_start": record.sleep_start.strftime("%H:%M"),
        "sleep_end": record.sleep_end.strftime("%H:%M"),
        "duration_minutes": record.duration_minutes,
        "duration": format_duration(record.duration_minutes),
        "awakenings_count": record.awakenings_count,
        "average_heart_rate": (
            round(record.average_heart_rate)
            if record.average_heart_rate is not None
            else None
        ),
        "average_spo2": (
            round(record.average_spo2, 1)
            if record.average_spo2 is not None
            else None
        ),
        "origin": "Galaxy Watch via Health Connect",
        "status": record.suggestion_status or "available",
        "stages": sleep_stage_data(record),
    }


def get_watch_suggestions(kind: str, *, include_completed: bool = False) -> list[dict]:
    if kind == "training":
        model = TrainingRecord
        serializer = serialize_training_suggestion
        incomplete = (
            TrainingRecord.intensity.is_(None)
            | TrainingRecord.perceived_performance.is_(None)
            | TrainingRecord.discomfort_level.is_(None)
        )
    elif kind == "sleep":
        model = SleepRecord
        serializer = serialize_sleep_suggestion
        incomplete = (
            SleepRecord.perceived_quality.is_(None)
            | SleepRecord.woke_restored.is_(None)
        )
    else:
        return []
    query = db.select(model).where(
        model.source_record_id.is_not(None),
        model.suggestion_status != "ignored",
    )
    if not include_completed:
        query = query.where(
            (model.suggestion_status == "available") | incomplete
        )
    records = db.session.scalars(
        query.order_by(model.record_date.desc(), model.id.desc()).limit(100)
    )
    return [serializer(record) for record in records]
