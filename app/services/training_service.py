from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from app.extensions import db
from app.models import TrainingRecord
from app.services.analytics_utils import (
    build_metric_comparison,
    build_score_comparison,
    calendar_metadata,
    format_duration,
    format_local_date_label,
    get_app_timezone,
    get_local_today,
    weekday_label,
)
from app.services.scoring_service import calculate_training_score, get_score_message
from app.services.catalog_service import (
    EXERCISE_TYPES,
    TRAINING_ALIASES,
    exercise_catalog_item,
)


TRAINING_TYPE_LABELS = {
    "strength": "Musculação",
    "running": "Corrida",
    "walking": "Caminhada",
    "swimming": "Natação",
    "cycling": "Ciclismo",
    "sport": "Esporte",
    "mobility": "Mobilidade",
    "other": "Outro",
}
TRAINING_TYPE_LABELS.update(
    {value[0]: value[1] for value in EXERCISE_TYPES.values()}
)
TRAINING_TYPE_LABELS.update({label: label for label in TRAINING_ALIASES})
PERFORMANCE_LABELS = {
    "bad": "Ruim",
    "regular": "Regular",
    "good": "Bom",
    "very_good": "Muito bom",
    "excellent": "Excelente",
}
DISCOMFORT_LABELS = {
    "none": "Nenhum",
    "mild": "Leve",
    "moderate": "Moderado",
    "strong": "Forte",
}
TRAINING_TYPE_ICONS = {
    "strength": ("dumbbell", "blue"),
    "running": ("footprints", "green"),
    "walking": ("footprints", "green"),
    "swimming": ("waves", "blue"),
    "cycling": ("bike", "green"),
    "sport": ("trophy", "orange"),
    "mobility": ("person-standing", "purple"),
    "other": ("activity", "blue"),
}
MODALITY_THEMES = ("blue", "green", "orange", "purple", "teal", "lilac")


def _record_catalog(record: TrainingRecord) -> dict:
    if record.manual_training_type:
        return exercise_catalog_item(key=record.manual_training_type)
    return exercise_catalog_item(
        code=record.source_exercise_type,
        key=record.training_type,
    )


def calculate_provisional_training_score(
    records: Iterable[TrainingRecord],
    weekly_records: Iterable[TrainingRecord] | None = None,
) -> int:
    """Adaptador compatível; a regra oficial vive em scoring_service."""
    return calculate_training_score(records, weekly_records)["score"]


def get_training_records_for_date(target_date: date) -> list[TrainingRecord]:
    return list(
        db.session.scalars(
            db.select(TrainingRecord)
            .where(TrainingRecord.record_date == target_date)
            .order_by(TrainingRecord.created_at.desc())
        )
    )


def _records_for_period(start_date: date, end_date: date) -> list[TrainingRecord]:
    if end_date < start_date:
        raise ValueError("A data final deve ser igual ou posterior à inicial.")
    return list(
        db.session.scalars(
            db.select(TrainingRecord)
            .where(TrainingRecord.record_date.between(start_date, end_date))
            .order_by(
                TrainingRecord.record_date.desc(),
                TrainingRecord.created_at.desc(),
            )
        )
    )


def _summarize_records(
    records: list[TrainingRecord],
    weekly_records: list[TrainingRecord] | None = None,
) -> dict:
    total_minutes = sum(record.duration_minutes for record in records)
    measured_intensities = [
        record.intensity for record in records if record.intensity is not None
    ]
    intensity_average = None
    if measured_intensities:
        intensity_average = round(
            sum(measured_intensities) / len(measured_intensities),
            1,
        )
    return {
        "sessions": len(records),
        "total_minutes": total_minutes,
        "duration": format_duration(total_minutes),
        "intensity_average": intensity_average,
        "score": calculate_provisional_training_score(records, weekly_records),
    }


def get_training_summary_for_date(target_date: date) -> dict:
    return _summarize_records(get_training_records_for_date(target_date))


def _weekly_data_from_records(
    records: list[TrainingRecord],
    reference_date: date,
) -> list[dict]:
    grouped: dict[date, list[TrainingRecord]] = defaultdict(list)
    for record in records:
        grouped[record.record_date].append(record)

    weekly = []
    start_date = reference_date - timedelta(days=6)
    for offset in range(7):
        target_date = start_date + timedelta(days=offset)
        day_records = grouped[target_date]
        consistency_records = [
            record
            for record in records
            if target_date - timedelta(days=6)
            <= record.record_date
            <= target_date
        ]
        raw_score = calculate_provisional_training_score(
            day_records,
            consistency_records,
        )
        total_minutes = sum(record.duration_minutes for record in day_records)
        session_count = len(day_records)
        training_label = "treino" if session_count == 1 else "treinos"
        weekly.append(
            {
                "date": target_date.isoformat(),
                "date_label": target_date.strftime("%d/%m"),
                "label": weekday_label(target_date),
                "score": raw_score * 5,
                "raw_score": raw_score,
                "total_minutes": total_minutes,
                "duration": format_duration(total_minutes),
                "sessions": session_count,
                "tooltip_lines": [
                    format_duration(total_minutes),
                    f"{session_count} {training_label}",
                ],
                "is_today": target_date == reference_date,
            }
        )
    return weekly


def _training_datasets(
    records: list[TrainingRecord],
    weekly: list[dict],
) -> list[dict]:
    dates = [item["date"] for item in weekly]
    grouped = defaultdict(lambda: defaultdict(int))
    styles = {}
    for record in records:
        style = _record_catalog(record)
        key = style["training_key"]
        grouped[key][record.record_date.isoformat()] += record.duration_minutes
        styles[key] = style
    return [
        {
            "key": key,
            "label": styles[key]["display_name"],
            "backgroundColor": styles[key]["color"],
            "data": [grouped[key][target] for target in dates],
            "sessionCounts": [
                sum(
                    1
                    for record in records
                    if record.record_date.isoformat() == target
                    and _record_catalog(record)["training_key"] == key
                )
                for target in dates
            ],
            "origins": [
                sorted(
                    {
                        "Relógio"
                        if record.record_origin in {"health_connect", "merged"}
                        else "Manual"
                        for record in records
                        if record.record_date.isoformat() == target
                        and _record_catalog(record)["training_key"] == key
                    }
                )
                for target in dates
            ],
        }
        for key in sorted(
            grouped,
            key=lambda item: styles[item]["display_name"].casefold(),
        )
    ]


def get_weekly_training_data(
    reference_date: date | None = None,
) -> list[dict]:
    reference_date = reference_date or get_local_today()
    return _weekly_data_from_records(
        _records_for_period(
            reference_date - timedelta(days=12),
            reference_date,
        ),
        reference_date,
    )


def _modality_distribution_from_records(
    records: list[TrainingRecord],
) -> list[dict]:
    grouped: dict[str, dict] = {}
    for record in records:
        catalog = _record_catalog(record)
        modality = (
            "Não classificados"
            if catalog["training_key"] == "other"
            else catalog["display_name"]
        )
        if modality not in grouped:
            grouped[modality] = {
                "name": modality,
                "minutes": 0,
                "sessions": 0,
                "color": catalog["color"],
            }
        grouped[modality]["minutes"] += record.duration_minutes
        grouped[modality]["sessions"] += 1

    ordered = sorted(
        grouped.values(),
        key=lambda item: (-item["minutes"], item["name"]),
    )
    maximum = ordered[0]["minutes"] if ordered else 0
    for item in ordered:
        session_label = "sessão" if item["sessions"] == 1 else "sessões"
        item.update(
            {
                "score": round(item["minutes"] / maximum * 100) if maximum else 0,
                "value": (
                    f"{format_duration(item['minutes'])} • "
                    f"{item['sessions']} {session_label}"
                ),
                "bar_label": f"Tempo relativo de {item['name']}",
                "theme": MODALITY_THEMES[ordered.index(item) % len(MODALITY_THEMES)],
                "color": item["color"],
            }
        )
    return ordered


def get_training_area_distribution(
    start_date: date,
    end_date: date,
) -> list[dict]:
    return _modality_distribution_from_records(
        _records_for_period(start_date, end_date)
    )


def _training_heatmap_level(minutes: int) -> int:
    if minutes == 0:
        return 0
    if minutes < 20:
        return 1
    if minutes < 40:
        return 2
    if minutes < 60:
        return 3
    if minutes < 90:
        return 4
    return 5


def _monthly_heatmap_from_records(
    records: list[TrainingRecord],
    year: int,
    month: int,
    reference_date: date,
) -> dict:
    calendar_data = calendar_metadata(year, month)
    grouped: dict[int, list[TrainingRecord]] = defaultdict(list)
    for record in records:
        if record.record_date.year == year and record.record_date.month == month:
            grouped[record.record_date.day].append(record)

    days = []
    for day in range(1, calendar_data["total_days"] + 1):
        day_records = grouped[day]
        total_minutes = sum(record.duration_minutes for record in day_records)
        type_labels = sorted(
            {
                _record_catalog(record)["display_name"]
                for record in day_records
            },
            key=str.casefold,
        )
        target_date = date(year, month, day)
        type_text = ", ".join(type_labels) if type_labels else "nenhum tipo"
        training_label = "treino" if len(day_records) == 1 else "treinos"
        days.append(
            {
                "day": day,
                "date": target_date.isoformat(),
                "level": _training_heatmap_level(total_minutes),
                "is_highlighted": target_date == reference_date,
                "title": (
                    f"{target_date.strftime('%d/%m/%Y')} • "
                    f"{format_duration(total_minutes)} • "
                    f"{len(day_records)} {training_label} • {type_text}"
                ),
            }
        )
    return {**calendar_data, "days": days}


def get_monthly_training_heatmap(
    year: int,
    month: int,
    reference_date: date | None = None,
) -> dict:
    reference_date = reference_date or get_local_today()
    last_day = calendar_metadata(year, month)["total_days"]
    return _monthly_heatmap_from_records(
        _records_for_period(
            date(year, month, 1),
            date(year, month, last_day),
        ),
        year,
        month,
        reference_date,
    )


def _local_time_label(created_at: datetime) -> str:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    local_time = created_at.astimezone(get_app_timezone())
    return local_time.strftime("%H:%M")


def _session_item(record: TrainingRecord) -> dict:
    catalog = _record_catalog(record)
    icon, theme = TRAINING_TYPE_ICONS.get(
        catalog["training_key"],
        TRAINING_TYPE_ICONS["other"],
    )
    origin = (
        "Relógio"
        if record.record_origin in {"health_connect", "merged"}
        else "Manual"
    )
    started_at = record.training_started_at or record.created_at
    details = [
        catalog["display_name"],
        format_duration(record.duration_minutes),
        _local_time_label(started_at),
        origin,
    ]
    if record.intensity is not None:
        details.append(f"Intensidade {record.intensity}/10")
    if record.perceived_performance is not None:
        performance = PERFORMANCE_LABELS.get(
            record.perceived_performance,
            "Não informado",
        )
        details.append(f"Desempenho {performance.casefold()}")
    metrics = []
    for label, value in (
        ("FC média", f"{round(record.average_heart_rate)} bpm" if record.average_heart_rate is not None else None),
        ("FC máxima", f"{round(record.maximum_heart_rate)} bpm" if record.maximum_heart_rate is not None else None),
        ("Calorias", f"{round(record.calories)} kcal" if record.calories is not None else None),
        ("Distância", f"{record.distance_meters / 1000:.2f} km".replace(".", ",") if record.distance_meters is not None else None),
        ("Ritmo", f"{round(record.average_pace_seconds_per_km / 60, 1)} min/km".replace(".", ",") if record.average_pace_seconds_per_km is not None else None),
        ("Velocidade", f"{record.average_speed_mps * 3.6:.1f} km/h".replace(".", ",") if record.average_speed_mps is not None else None),
        ("VO₂ máx.", f"{record.vo2_max:.1f} ml/kg/min".replace(".", ",") if record.vo2_max is not None else None),
    ):
        if value is not None:
            metrics.append(f"{label}: {value}")
    if record.discomfort_level and record.discomfort_level != "none":
        discomfort = DISCOMFORT_LABELS.get(record.discomfort_level, "Não informado")
        if record.discomfort_location:
            discomfort = f"{discomfort} em {record.discomfort_location}"
        metrics.append(f"Desconforto: {discomfort}")
        details.append(f"Desconforto {discomfort.casefold()}")
    pending = catalog["training_key"] == "other" and not record.manual_training_type
    return {
        "name": (
            "Treino não classificado"
            if pending
            else record.activity_name
            if record.source_record_id is None
            else catalog["display_name"]
        ),
        "meta": " • ".join(details),
        "value": "Classificar" if pending else origin,
        "icon": icon,
        "theme": theme,
        "details": metrics,
        "action_href": (
            f"/registrar?categoria=treino&watch_id={record.id}"
            if pending
            else None
        ),
    }


def _score_message(score: int) -> str:
    return get_score_message(score, 20)


def _intensity_status(value: float | None) -> str:
    if value is None:
        return "Nenhum treino registrado nesta data."
    if value <= 3:
        return "Leve"
    if value <= 6:
        return "Moderada"
    if value <= 8:
        return "Alta"
    return "Muito alta"


def _consistency_status(days: int) -> str:
    if days <= 1:
        return "Baixa"
    if days <= 3:
        return "Regular"
    if days <= 5:
        return "Boa"
    return "Excelente"


def _session_count_label(value: int) -> str:
    return f"{value} sessão" if value == 1 else f"{value} sessões"


def _day_count_label(value: int) -> str:
    return f"{value} dia" if value == 1 else f"{value} dias"


def get_training_page_data(reference_date: date | None = None) -> dict:
    reference_date = reference_date or get_local_today()
    viewing_today = reference_date == get_local_today()
    yesterday = reference_date - timedelta(days=1)
    last_30_start = reference_date - timedelta(days=29)
    weekly_start = reference_date - timedelta(days=6)
    month_start = reference_date.replace(day=1)
    query_start = min(yesterday, last_30_start, month_start)

    records = _records_for_period(query_start, reference_date)
    records_by_date: dict[date, list[TrainingRecord]] = defaultdict(list)
    for record in records:
        records_by_date[record.record_date].append(record)

    today_records = records_by_date[reference_date]
    yesterday_records = records_by_date[yesterday]
    today_consistency_records = [
        record
        for record in records
        if weekly_start <= record.record_date <= reference_date
    ]
    yesterday_consistency_records = [
        record
        for record in records
        if yesterday - timedelta(days=6) <= record.record_date <= yesterday
    ]
    today_summary = _summarize_records(
        today_records,
        today_consistency_records,
    )
    yesterday_summary = _summarize_records(
        yesterday_records,
        yesterday_consistency_records,
    )
    score_comparison = build_score_comparison(
        today_summary["score"],
        yesterday_summary["score"],
        bool(yesterday_records),
    )
    sessions_helper, sessions_tone = build_metric_comparison(
        today_summary["sessions"],
        yesterday_summary["sessions"],
        unit="sessions",
        has_previous=bool(yesterday_records),
    )
    has_today_records = bool(today_records)
    if not has_today_records:
        score_comparison = {
            "text": "Sem avaliação nesta data",
            "tone": "neutral",
            "icon": "minus",
        }
        sessions_helper, sessions_tone = (
            "Nenhum treino registrado nesta data.",
            "neutral",
        )
        duration_helper, duration_tone = (
            "Nenhum treino registrado nesta data.",
            "neutral",
        )
    duration_helper, duration_tone = build_metric_comparison(
        today_summary["total_minutes"],
        yesterday_summary["total_minutes"],
        unit="min",
        has_previous=bool(yesterday_records),
    )

    weekly_records = [
        record for record in records if record.record_date >= weekly_start
    ]
    weekly_chart_records = [
        record
        for record in records
        if record.record_date >= reference_date - timedelta(days=12)
    ]
    weekly = _weekly_data_from_records(weekly_chart_records, reference_date)
    consistency_days = len(
        {record.record_date for record in weekly_records}
    )
    area_records = [
        record for record in records if record.record_date >= last_30_start
    ]
    month_records = [
        record for record in records if record.record_date >= month_start
    ]
    intensity_average = today_summary["intensity_average"]

    return {
        "reference_label": format_local_date_label(reference_date),
        "reference_date": reference_date.isoformat(),
        "is_today": viewing_today,
        "score": {
            "evaluated": has_today_records,
            "value": today_summary["score"] * 5,
            "raw_value": today_summary["score"],
            "previous_raw_value": yesterday_summary["score"],
            "comparison": score_comparison["text"],
            "comparison_tone": score_comparison["tone"],
            "comparison_icon": score_comparison["icon"],
            "helper": (
                (
                    f"{today_summary['score']} de 20 pontos da categoria. "
                    f"{_score_message(today_summary['score'])}"
                )
                if has_today_records
                else "Nenhum treino registrado nesta data."
            ),
        },
        "metrics": [
            {
                "title": "Treino de hoje" if viewing_today else "Treino na data",
                "value": _session_count_label(today_summary["sessions"]),
                "helper": sessions_helper,
                "helper_tone": sessions_tone,
                "icon": "dumbbell",
                "theme": "green",
            },
            {
                "title": "Duração",
                "value": today_summary["duration"],
                "helper": duration_helper,
                "helper_tone": duration_tone,
                "icon": "clock-3",
                "theme": "blue",
            },
            {
                "title": "Intensidade",
                "value": (
                    f"{intensity_average:.1f}".replace(".", ",") + " / 10"
                    if intensity_average is not None
                    else "—"
                ),
                "helper": _intensity_status(intensity_average),
                "helper_tone": "neutral",
                "icon": "zap",
                "theme": "orange",
            },
            {
                "title": "Consistência",
                "value": _day_count_label(consistency_days),
                "helper": _consistency_status(consistency_days),
                "helper_tone": "neutral",
                "icon": "calendar-check-2",
                "theme": "purple",
            },
        ],
        "sessions": [_session_item(record) for record in today_records[:4]],
        "sessions_empty": {
            "title": (
                "Nenhum treino registrado hoje"
                if viewing_today
                else "Nenhum treino registrado nesta data"
            ),
            "description": (
                "Registre seu primeiro treino para acompanhar sua evolução."
            ),
            "link_label": "Registrar treino",
            "link_href": (
                f"/registrar?categoria=treino&date={reference_date.isoformat()}"
            ),
        },
        "weekly": {
            "labels": [item["label"] for item in weekly],
            "scores": [item["score"] for item in weekly],
            "details": weekly,
            "datasets": _training_datasets(weekly_records, weekly),
            "filter": "Últimos 7 dias",
        },
        "areas": _modality_distribution_from_records(area_records),
        "areas_empty": "Nenhum treino registrado nos últimos 30 dias.",
        "next_training": {
            "title": "Próximo treino",
            "subtitle": "Nenhum treino planejado.",
            "plan": "Inicie uma sessão quando estiver pronto.",
            "subject": "Sem modalidade definida",
            "duration": "—",
            "schedule": "Sem horário",
            "status": "Não planejado",
            "is_demonstrative": False,
        },
        "heatmap": _monthly_heatmap_from_records(
            month_records,
            reference_date.year,
            reference_date.month,
            reference_date,
        ),
    }
