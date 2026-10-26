from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.health_import.deduplication import normalized_hash, source_id
from app.health_import.health_connect_reader import (
    HealthConnectReader,
    epoch_millis_to_datetime,
)
from app.services.catalog_service import exercise_catalog_item


LOGGER = logging.getLogger("condution_time.health_import")
AWAKE_STAGE_TYPES = {1, 3, 7}
SLEEPING_STAGE_TYPES = {2, 4, 5, 6}


def _mass_kg(value: float | int | None) -> float | None:
    if value is None:
        return None
    result = float(value)
    return round(result / 1000 if result > 500 else result, 3)


def _energy_kcal(value: float | int | None) -> float | None:
    if value is None:
        return None
    result = float(value)
    # O SQLite nativo exporta energia em calorias; a interface trabalha em
    # quilocalorias. Valores antigos já normalizados continuam aceitos.
    return round(result / 1000 if result > 10_000 else result, 2)


def grouped_awakenings(
    stages: list[dict],
    *,
    session_start_ms: int,
    session_end_ms: int,
    merge_gap_seconds: int = 300,
    minimum_awake_seconds: int = 120,
) -> int:
    """Conta despertares internos relevantes, agrupados em uma janela de 5 min."""
    awake = []
    for stage in stages:
        if int(stage.get("type", 0)) not in AWAKE_STAGE_TYPES:
            continue
        try:
            start_ms = round(datetime.fromisoformat(stage["start"]).timestamp() * 1000)
            end_ms = round(datetime.fromisoformat(stage["end"]).timestamp() * 1000)
        except (KeyError, TypeError, ValueError):
            continue
        # O período acordado antes do primeiro sono e o despertar final não são
        # interrupções internas.
        if start_ms <= session_start_ms + merge_gap_seconds * 1000:
            continue
        if end_ms >= session_end_ms - merge_gap_seconds * 1000:
            continue
        awake.append((start_ms, end_ms))
    awake.sort()
    merged: list[list[int]] = []
    gap_ms = merge_gap_seconds * 1000
    for start_ms, end_ms in awake:
        if merged and start_ms - merged[-1][1] <= gap_ms:
            merged[-1][1] = max(merged[-1][1], end_ms)
            merged[-1][2] += max(0, end_ms - start_ms)
        else:
            merged.append([start_ms, end_ms, max(0, end_ms - start_ms)])
    return sum(
        item[2] >= minimum_awake_seconds * 1000
        for item in merged
    )


def map_sleep(
    row: Any,
    reader: HealthConnectReader,
    *,
    is_primary: bool = True,
) -> dict:
    start_ms, end_ms = int(row["start_time"]), int(row["end_time"])
    start = epoch_millis_to_datetime(start_ms)
    end = epoch_millis_to_datetime(end_ms)
    stages = reader.stages_for(int(row["row_id"]))
    heart = reader.series_stats("heart", start_ms, end_ms)
    spo2 = reader.series_stats("spo2", start_ms, end_ms)
    awakenings = grouped_awakenings(
        stages,
        session_start_ms=start_ms,
        session_end_ms=end_ms,
    )
    stable_id = source_id(
        row["uuid"],
        fallback_parts=("sleep", start_ms, end_ms),
    )
    payload = {
        "record_date": end.astimezone(reader.timezone).date(),
        "sleep_started_at": start,
        "sleep_ended_at": end,
        "duration_minutes": max(1, round((end_ms - start_ms) / 60000)),
        "awakenings_count": awakenings,
        "sleep_stages_json": json.dumps(stages, separators=(",", ":")),
        "average_heart_rate": heart.get("average"),
        "minimum_heart_rate": heart.get("minimum"),
        "maximum_heart_rate": heart.get("maximum"),
        "average_spo2": spo2.get("average"),
        "minimum_spo2": spo2.get("minimum"),
        "is_primary": is_primary,
        "source_record_id": stable_id,
        "last_source_update_at": epoch_millis_to_datetime(
            int(row["last_modified_time"])
        ),
    }
    payload["source_hash"] = normalized_hash(payload)
    return payload


def map_training(row: Any, reader: HealthConnectReader) -> dict:
    start_ms, end_ms = int(row["start_time"]), int(row["end_time"])
    start = epoch_millis_to_datetime(start_ms)
    end = epoch_millis_to_datetime(end_ms)
    distance = reader.overlapping_sum(
        "distance_record_table", "distance", start_ms, end_ms
    )
    calories = reader.overlapping_sum(
        "total_calories_burned_record_table", "energy", start_ms, end_ms
    )
    steps = reader.overlapping_sum("steps_record_table", "count", start_ms, end_ms)
    heart = reader.series_stats("heart", start_ms, end_ms)
    speed = (
        reader.speed_stats(start_ms, end_ms)
        if hasattr(reader, "speed_stats")
        else {}
    )
    vo2_max = (
        reader.point_average(
            "vo2_max_record_table",
            "time",
            "vo2_milliliters_per_minute_kilogram",
            start_ms,
            end_ms,
        )
        if hasattr(reader, "point_average")
        else None
    )
    stable_id = source_id(
        row["uuid"],
        fallback_parts=("training", start_ms, end_ms, row["exercise_type"]),
    )
    exercise_type = int(row["exercise_type"] or 0)
    exercise = exercise_catalog_item(code=exercise_type)
    if not exercise["recognized"]:
        LOGGER.warning(
            "Tipo de exercício não reconhecido no Health Connect: code=%s",
            exercise_type,
        )
    activity = exercise["display_name"] or str(row["title"] or "").strip() or "Exercício"
    duration_minutes = max(1, round((end_ms - start_ms) / 60000))
    payload = {
        "record_date": start.astimezone(reader.timezone).date(),
        "training_type": exercise["training_key"],
        "source_exercise_type": exercise_type,
        "activity_name": activity[:150],
        "training_started_at": start,
        "training_ended_at": end,
        "duration_minutes": duration_minutes,
        "distance_meters": distance,
        "calories": _energy_kcal(calories),
        "average_heart_rate": heart.get("average"),
        "maximum_heart_rate": heart.get("maximum"),
        "average_pace_seconds_per_km": (
            round(duration_minutes * 60 / (distance / 1000), 2)
            if distance and distance > 0
            else None
        ),
        "average_speed_mps": speed.get("average"),
        "vo2_max": vo2_max,
        "steps": round(steps) if steps is not None else None,
        "segments_summary_json": json.dumps(
            reader.segments_for(int(row["row_id"])),
            separators=(",", ":"),
        ),
        "source_record_id": stable_id,
        "last_source_update_at": epoch_millis_to_datetime(
            int(row["last_modified_time"])
        ),
    }
    payload["source_hash"] = normalized_hash(payload)
    return payload


def map_body(row: Any, *, kind: str, height_cm: float | None = None) -> dict:
    measured_at = epoch_millis_to_datetime(int(row["time"]))
    stable_id = source_id(
        row["uuid"],
        fallback_parts=(kind, row["time"]),
    )
    payload: dict[str, Any] = {
        "measured_at": measured_at,
        "source_record_id": f"{kind}:{stable_id}",
        "last_source_update_at": epoch_millis_to_datetime(
            int(row["last_modified_time"])
        ),
    }
    if kind == "weight":
        payload["weight_kg"] = _mass_kg(row["weight"])
        if height_cm and payload["weight_kg"]:
            payload["bmi"] = round(
                payload["weight_kg"] / ((height_cm / 100) ** 2),
                2,
            )
    else:
        percentage = float(row["percentage"])
        payload["body_fat_percentage"] = (
            round(percentage * 100, 2) if 0 < percentage <= 1 else round(percentage, 2)
        )
    payload["source_hash"] = normalized_hash(payload)
    return payload
