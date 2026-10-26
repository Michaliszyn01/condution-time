from __future__ import annotations

from collections import defaultdict
from datetime import date, time, timedelta

from flask import current_app

from app.extensions import db
from app.models import SleepRecord
from app.services.analytics_utils import (
    build_metric_comparison,
    build_score_comparison,
    calendar_metadata,
    format_duration,
    format_local_date_label,
    get_local_today,
    weekday_label,
)
from app.services.scoring_service import calculate_sleep_score, get_score_message
from app.services.watch_service import sleep_stage_data


SLEEP_QUALITY_LABELS = {
    "terrible": "Péssima",
    "bad": "Ruim",
    "regular": "Regular",
    "good": "Boa",
    "excellent": "Excelente",
}
SLEEP_QUALITY_PERCENT = {
    "terrible": 20,
    "bad": 40,
    "regular": 60,
    "good": 80,
    "excellent": 100,
}
RESTORED_LABELS = {
    "yes": "Sim",
    "partially": "Parcialmente",
    "no": "Não",
}
RESTORED_PERCENT = {
    "yes": 100,
    "partially": 60,
    "no": 25,
}


def calculate_provisional_sleep_score(record: SleepRecord | None) -> int:
    """Adaptador compatível; a regra oficial vive em scoring_service."""
    return calculate_sleep_score(record)["score"]


def get_sleep_record_for_date(target_date: date) -> SleepRecord | None:
    return db.session.scalar(
        db.select(SleepRecord)
        .where(
            SleepRecord.record_date == target_date,
            SleepRecord.is_primary.is_(True),
        )
        .order_by(SleepRecord.duration_minutes.desc())
    )


def _records_for_period(start_date: date, end_date: date) -> list[SleepRecord]:
    if end_date < start_date:
        raise ValueError("A data final deve ser igual ou posterior à inicial.")
    return list(
        db.session.scalars(
            db.select(SleepRecord)
            .where(SleepRecord.record_date.between(start_date, end_date))
            .order_by(SleepRecord.record_date.desc())
        )
    )


def _time_label(value: time | None) -> str:
    return value.strftime("%H:%M") if value is not None else "—"


def _sleep_summary(record: SleepRecord | None) -> dict:
    if record is None:
        return {
            "record": None,
            "duration_minutes": 0,
            "duration": "—",
            "sleep_window": "—",
            "wake_time": "—",
            "score": 0,
        }
    return {
        "record": record,
        "duration_minutes": record.duration_minutes,
        "duration": format_duration(record.duration_minutes),
        "sleep_window": (
            f"{_time_label(record.sleep_start)} – "
            f"{_time_label(record.sleep_end)}"
        ),
        "wake_time": _time_label(record.sleep_end),
        "score": calculate_provisional_sleep_score(record),
    }


def get_sleep_summary_for_date(target_date: date) -> dict:
    return _sleep_summary(get_sleep_record_for_date(target_date))


def _wake_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _wake_comparison(
    current: SleepRecord | None,
    previous: SleepRecord | None,
) -> tuple[str, str]:
    if current is None:
        return "Nenhum sono registrado nesta data.", "neutral"
    if previous is None:
        return "Sem registro ontem", "neutral"
    difference = _wake_minutes(current.sleep_end) - _wake_minutes(previous.sleep_end)
    if difference > 720:
        difference -= 1440
    elif difference < -720:
        difference += 1440
    if difference == 0:
        return "Mesmo horário de ontem", "neutral"
    direction = "mais tarde" if difference > 0 else "mais cedo"
    return f"{abs(difference)} min {direction} que ontem", "neutral"


def _weekly_data_from_records(
    records: list[SleepRecord],
    reference_date: date,
) -> list[dict]:
    by_date = {
        record.record_date: record
        for record in records
        if record.is_primary
    }
    weekly = []
    start_date = reference_date - timedelta(days=6)
    for offset in range(7):
        target_date = start_date + timedelta(days=offset)
        record = by_date.get(target_date)
        raw_score = calculate_provisional_sleep_score(record)
        quality = (
            SLEEP_QUALITY_LABELS.get(record.perceived_quality, "Não informada")
            if record
            else "Sem registro"
        )
        restored = (
            RESTORED_LABELS.get(record.woke_restored, "Não informado")
            if record
            else "Sem registro"
        )
        duration = format_duration(record.duration_minutes) if record else "0 min"
        weekly.append(
            {
                "date": target_date.isoformat(),
                "date_label": target_date.strftime("%d/%m"),
                "label": weekday_label(target_date),
                "score": raw_score * 5,
                "raw_score": raw_score,
                "duration": duration,
                "quality": quality,
                "restored": restored,
                "tooltip_lines": [
                    duration,
                    f"Qualidade {quality.casefold()}",
                    f"Descansado: {restored}",
                ],
                "is_today": target_date == reference_date,
            }
        )
    return weekly


def get_weekly_sleep_data(reference_date: date | None = None) -> list[dict]:
    reference_date = reference_date or get_local_today()
    return _weekly_data_from_records(
        _records_for_period(
            reference_date - timedelta(days=6),
            reference_date,
        ),
        reference_date,
    )


def _sleep_heatmap_level(score: int) -> int:
    if score == 0:
        return 0
    if score <= 4:
        return 1
    if score <= 8:
        return 2
    if score <= 12:
        return 3
    if score <= 16:
        return 4
    return 5


def _monthly_heatmap_from_records(
    records: list[SleepRecord],
    year: int,
    month: int,
    reference_date: date,
) -> dict:
    calendar_data = calendar_metadata(year, month)
    by_day = {
        record.record_date.day: record
        for record in records
        if record.is_primary
        if record.record_date.year == year and record.record_date.month == month
    }
    days = []
    for day in range(1, calendar_data["total_days"] + 1):
        record = by_day.get(day)
        score = calculate_provisional_sleep_score(record)
        target_date = date(year, month, day)
        duration = format_duration(record.duration_minutes) if record else "0 min"
        quality = (
            SLEEP_QUALITY_LABELS.get(record.perceived_quality, "Não informada")
            if record
            else "Sem registro"
        )
        days.append(
            {
                "day": day,
                "date": target_date.isoformat(),
                "level": _sleep_heatmap_level(score),
                "is_highlighted": target_date == reference_date,
                "title": (
                    f"{target_date.strftime('%d/%m/%Y')} • "
                    f"{duration} • Qualidade {quality.casefold()} • "
                    f"{score} de 20 pontos"
                ),
            }
        )
    return {**calendar_data, "days": days}


def get_monthly_sleep_heatmap(
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


def _night_summary_items(record: SleepRecord | None) -> list[dict]:
    if record is None:
        return []
    interruption_label = (
        "Nenhuma"
        if record.awakenings_count == 0
        else (
            "1 vez"
            if record.awakenings_count == 1
            else f"{record.awakenings_count} vezes"
        )
    )
    items = [
        {
            "name": "Dormiu às",
            "meta": "Início do sono",
            "value": _time_label(record.sleep_start),
            "icon": "bed",
            "theme": "purple",
        },
        {
            "name": "Acordou às",
            "meta": "Fim do sono",
            "value": _time_label(record.sleep_end),
            "icon": "sun",
            "theme": "orange",
        },
        {
            "name": "Duração",
            "meta": "Tempo total registrado",
            "value": format_duration(record.duration_minutes),
            "icon": "clock-3",
            "theme": "blue",
        },
        {
            "name": "Despertares detectados",
            "meta": "Eventos internos agrupados; início e despertar final ignorados",
            "value": interruption_label,
            "icon": "activity",
            "theme": "blue",
        },
        {
            "name": "Qualidade percebida",
            "meta": "Avaliação manual",
            "value": SLEEP_QUALITY_LABELS.get(
                record.perceived_quality,
                "Não informada",
            ),
            "icon": "badge-check",
            "theme": "purple",
        },
        {
            "name": "Acordou descansado",
            "meta": "Percepção ao despertar",
            "value": RESTORED_LABELS.get(
                record.woke_restored,
                "Não informado",
            ),
            "icon": "sunrise",
            "theme": "orange",
        },
    ]
    if record.notes:
        items.append(
            {
                "name": "Observações",
                "meta": record.notes,
                "value": "",
                "icon": "notebook-pen",
                "theme": "purple",
            }
        )
    return items


def _continuity_percent(awakenings: int) -> int:
    if awakenings == 0:
        return 100
    if awakenings == 1:
        return 85
    if awakenings == 2:
        return 70
    if awakenings == 3:
        return 50
    return 30


def _manual_indicators(record: SleepRecord | None, stages: dict | None = None) -> list[dict]:
    """Indicadores manuais; não representam estágios fisiológicos do sono."""
    if record is None:
        return []
    sleep_target = current_app.config["DEFAULT_SLEEP_TARGET_MINUTES"]
    duration_percent = min(
        round(record.duration_minutes / sleep_target * 100),
        100,
    )
    quality_percent = SLEEP_QUALITY_PERCENT.get(record.perceived_quality, 0)
    restored_percent = RESTORED_PERCENT.get(record.woke_restored, 0)
    continuity_percent = _continuity_percent(record.awakenings_count)
    indicators = [
        {
            "name": "Duração",
            "score": duration_percent,
            "value": f"{format_duration(record.duration_minutes)} • {duration_percent}%",
            "bar_label": (
                "Duração em relação à meta configurada de "
                f"{format_duration(sleep_target)}"
            ),
            "theme": "purple",
        },
        {
            "name": "Qualidade percebida",
            "score": quality_percent,
            "value": (
                f"{SLEEP_QUALITY_LABELS.get(record.perceived_quality, 'Não informada')} "
                f"• {quality_percent}%"
            ),
            "bar_label": "Indicador manual de qualidade percebida",
            "theme": "lilac",
        },
        {
            "name": "Descanso ao acordar",
            "score": restored_percent,
            "value": (
                f"{RESTORED_LABELS.get(record.woke_restored, 'Não informado')} "
                f"• {restored_percent}%"
            ),
            "bar_label": "Indicador manual de descanso ao acordar",
            "theme": "blue",
        },
        {
            "name": "Continuidade",
            "score": continuity_percent,
            "value": f"{continuity_percent}%",
            "bar_label": "Continuidade baseada nos despertares internos agrupados",
            "theme": "teal",
        },
    ]
    stage_items = (
        (stages or {}).get("items", [])
        if (stages or {}).get("timeline")
        else []
    )
    for stage in stage_items:
        indicators.append(
            {
                "name": stage["label"],
                "score": stage["percentage"],
                "value": f"{stage['duration']} • {stage['percentage']}%",
                "bar_label": (
                    f"{stage['label']}: {stage['duration']}, "
                    f"{stage['percentage']}% da sessão"
                ),
                "theme": {
                    "light": "blue",
                    "deep": "purple",
                    "rem": "lilac",
                    "awake": "orange",
                }.get(stage["key"], "purple"),
            }
        )
    return indicators


def _score_message(score: int) -> str:
    return get_score_message(score, 20)


def _next_goal_message(record: SleepRecord | None) -> str:
    if record is None:
        return "Registre seu sono para receber uma orientação."
    if record.awakenings_count >= 3:
        return "Prepare uma rotina noturna mais tranquila."
    if record.duration_minutes < 420:
        return "Procure dormir um pouco mais cedo hoje."
    if (
        record.duration_minutes <= 540
        and record.perceived_quality in {"good", "excellent"}
    ):
        return "Mantenha sua rotina atual."
    return "Observe como você se sente e mantenha seus registros."


def get_sleep_page_data(reference_date: date | None = None) -> dict:
    reference_date = reference_date or get_local_today()
    viewing_today = reference_date == get_local_today()
    yesterday = reference_date - timedelta(days=1)
    last_30_start = reference_date - timedelta(days=29)
    month_start = reference_date.replace(day=1)
    query_start = min(yesterday, last_30_start, month_start)

    records = _records_for_period(query_start, reference_date)
    sessions_by_date: dict[date, list[SleepRecord]] = defaultdict(list)
    for record in records:
        sessions_by_date[record.record_date].append(record)
    today_sessions = sessions_by_date.get(reference_date, [])
    today_record = next(
        (record for record in today_sessions if record.is_primary),
        max(today_sessions, key=lambda record: record.duration_minutes, default=None),
    )
    yesterday_sessions = sessions_by_date.get(yesterday, [])
    yesterday_record = next(
        (record for record in yesterday_sessions if record.is_primary),
        max(yesterday_sessions, key=lambda record: record.duration_minutes, default=None),
    )
    today_summary = _sleep_summary(today_record)
    yesterday_summary = _sleep_summary(yesterday_record)
    comparison = build_score_comparison(
        today_summary["score"],
        yesterday_summary["score"],
        yesterday_record is not None,
    )
    if today_record is None:
        comparison = {
            "text": "Sem avaliação nesta data",
            "tone": "neutral",
            "icon": "minus",
        }
    duration_helper, duration_tone = build_metric_comparison(
        today_summary["duration_minutes"],
        yesterday_summary["duration_minutes"],
        unit="min",
        has_previous=yesterday_record is not None,
    )
    if today_record is None:
        duration_helper, duration_tone = "Nenhum sono registrado nesta data.", "neutral"
    wake_helper, wake_tone = _wake_comparison(
        today_record,
        yesterday_record,
    )
    stages = sleep_stage_data(today_record) if today_record else {
        "items": [],
        "timeline": [],
        "unclassified_minutes": 0,
        "unclassified": "0 min",
        "items": [],
        "sleeping_minutes": 0,
        "awake_minutes": 0,
        "efficiency_percent": 0,
    }

    metrics = [
        {
            "title": "Horas dormidas",
            "value": today_summary["duration"],
            "helper": duration_helper,
            "helper_tone": duration_tone,
            "secondary_helper": "",
            "icon": "moon-star",
            "theme": "purple",
        },
        {
            "title": "Tempo dormindo",
            "value": (
                format_duration(stages["sleeping_minutes"])
                if stages["items"]
                else "—"
            ),
            "helper": (
                f"Eficiência {stages['efficiency_percent']}%"
                if stages["items"]
                else "Sem estágios nesta noite"
            ),
            "helper_tone": "neutral",
            "secondary_helper": "",
            "icon": "activity",
            "theme": "purple",
        },
        {
            "title": "Horário de sono",
            "value": today_summary["sleep_window"],
            "helper": (
                f"{today_summary['duration']} na cama"
                if today_record
                else "Nenhum sono registrado nesta data."
            ),
            "helper_tone": "neutral",
            "secondary_helper": "",
            "icon": "clock-3",
            "theme": "blue",
        },
        {
            "title": "Despertar",
            "value": today_summary["wake_time"],
            "helper": wake_helper,
            "helper_tone": wake_tone,
            "secondary_helper": "",
            "icon": "sun",
            "theme": "orange",
        },
    ]
    if today_record:
        optional_metrics = (
            ("FC média", today_record.average_heart_rate, "bpm", "heart-pulse", "red"),
            ("FC mínima", today_record.minimum_heart_rate, "bpm", "heart", "blue"),
            ("FC máxima", today_record.maximum_heart_rate, "bpm", "activity", "orange"),
            ("SpO₂ média", today_record.average_spo2, "%", "wind", "teal"),
            ("SpO₂ mínima", today_record.minimum_spo2, "%", "wind", "purple"),
        )
        for title, value, unit, icon, theme in optional_metrics:
            if value is None:
                continue
            metrics.append(
                {
                    "title": title,
                    "value": f"{round(value, 1):g} {unit}".replace(".", ","),
                    "helper": "Média da sessão" if "média" in title.casefold() else "Durante a sessão",
                    "helper_tone": "neutral",
                    "secondary_helper": "",
                    "icon": icon,
                    "theme": theme,
                }
            )

    weekly_start = reference_date - timedelta(days=6)
    weekly = _weekly_data_from_records(
        [record for record in records if record.record_date >= weekly_start],
        reference_date,
    )
    month_records = [
        record for record in records if record.record_date >= month_start
    ]

    return {
        "reference_label": format_local_date_label(reference_date),
        "reference_date": reference_date.isoformat(),
        "is_today": viewing_today,
        "score_title": "Pontuação de sono",
        "score": {
            "evaluated": today_record is not None,
            "value": today_summary["score"] * 5,
            "raw_value": today_summary["score"],
            "previous_raw_value": yesterday_summary["score"],
            "comparison": comparison["text"],
            "comparison_tone": comparison["tone"],
            "comparison_icon": comparison["icon"],
            "helper": (
                (
                    f"{today_summary['score']} de 20 pontos da categoria. "
                    f"{_score_message(today_summary['score'])}"
                )
                if today_record
                else "Nenhum sono registrado nesta data."
            ),
        },
        "metrics": metrics,
        "list": {
            "title": "Resumo da noite",
            "link_label": "Ver detalhes da noite",
            "link_href": "#sleep-night-details",
            "items": _night_summary_items(today_record),
            "empty": {
                "title": (
                    "Nenhum sono registrado para hoje"
                    if viewing_today
                    else "Nenhum sono registrado para esta noite"
                ),
                "description": (
                    "Registre seu sono para acompanhar a qualidade do descanso."
                ),
                "link_label": "Registrar sono",
                "link_href": (
                    f"/registrar?categoria=sono&date={reference_date.isoformat()}"
                ),
            },
        },
        "sleep_stages": stages,
        "sleep_sessions": [
            {
                "id": record.id,
                "kind": "Sono principal" if record is today_record else "Cochilo",
                "duration": format_duration(record.duration_minutes),
                "window": f"{_time_label(record.sleep_start)} – {_time_label(record.sleep_end)}",
                "stages": sleep_stage_data(record),
            }
            for record in sorted(
                today_sessions,
                key=lambda item: (not item.is_primary, item.sleep_started_at or item.created_at),
            )
        ],
        "record_origin": (
            "Mesclada"
            if today_record and today_record.record_origin == "merged"
            else "Relógio"
            if today_record and today_record.record_origin == "health_connect"
            else "Manual"
            if today_record
            else None
        ),
        "weekly": {
            "title": "Qualidade semanal",
            "labels": [item["label"] for item in weekly],
            "scores": [item["score"] for item in weekly],
            "details": weekly,
            "filter": "Últimos 7 dias",
        },
        "progress": {
            "title": "Indicadores do sono",
            "link_label": "Ver todos os indicadores",
            "items": _manual_indicators(today_record, stages),
            "empty_text": "Registre seu sono para ver os indicadores manuais.",
        },
        # Orientação demonstrativa, não médica e sem planejamento persistente.
        "action": {
            "title": "Próxima meta",
            "subtitle": _next_goal_message(today_record),
            "plan": "Orientação para a próxima noite",
            "subject": "Acompanhamento manual",
            "duration": "Sem recomendação médica",
            "schedule": "Hoje",
            "status": "Orientação geral",
            "icon": "moon-star",
            "primary_label": "Ver rotina",
            "secondary_label": "Ver todas as metas",
            "is_demonstrative": True,
        },
        "heatmap": {
            **_monthly_heatmap_from_records(
                month_records,
                reference_date.year,
                reference_date.month,
                reference_date,
            ),
            "title": "Mapa de sono",
            "activity_label": "sono",
        },
    }
