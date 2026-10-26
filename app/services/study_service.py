from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable

from app.extensions import db
from app.models import StudyRecord
from app.services.analytics_utils import (
    build_metric_comparison,
    build_score_comparison,
    calendar_metadata,
    format_duration,
    format_local_date_label,
    get_local_today,
    weekday_label,
)
from app.services.scoring_service import calculate_study_score, get_score_message
from app.services.catalog_service import subject_catalog_item


FOCUS_VALUES = {
    "low": 20,
    "regular": 40,
    "good": 60,
    "very_good": 80,
    "excellent": 100,
}
FOCUS_LABELS = {
    "low": "baixo",
    "regular": "regular",
    "good": "bom",
    "very_good": "muito bom",
    "excellent": "excelente",
}
SUBJECT_STYLES = (
    ("matem", "calculator", "blue"),
    ("hist", "landmark", "green"),
    ("reda", "pencil-line", "purple"),
    ("biolog", "flask-conical", "orange"),
    ("quím", "flask-conical", "orange"),
    ("quim", "flask-conical", "orange"),
    ("fís", "atom", "blue"),
    ("fis", "atom", "blue"),
    ("geograf", "globe-2", "green"),
    ("program", "code-2", "purple"),
)
SUBJECT_THEMES = ("blue", "purple", "green", "orange", "rose")


def calculate_provisional_study_score(
    records: Iterable[StudyRecord],
) -> int:
    """Adaptador compatível; a regra oficial vive em scoring_service."""
    return calculate_study_score(records)["score"]


def get_study_records_for_date(target_date: date) -> list[StudyRecord]:
    return list(
        db.session.scalars(
            db.select(StudyRecord)
            .where(StudyRecord.record_date == target_date)
            .order_by(StudyRecord.created_at.desc())
        )
    )


def _normalized_subject(value: str) -> str:
    return " ".join(value.split()).casefold()


def _focus_average(records: list[StudyRecord]) -> int | None:
    if not records:
        return None
    return round(
        sum(FOCUS_VALUES.get(record.focus_quality, 0) for record in records)
        / len(records)
    )


def _focus_status(value: int | None) -> str:
    if value is None:
        return "Sem registros hoje"
    if value < 40:
        return "Baixo"
    if value < 60:
        return "Regular"
    if value < 75:
        return "Bom"
    if value < 90:
        return "Muito bom"
    return "Excelente"


def get_study_summary_for_date(target_date: date) -> dict:
    return _summarize_records(get_study_records_for_date(target_date))


def _summarize_records(records: list[StudyRecord]) -> dict:
    total_minutes = sum(record.duration_minutes for record in records)
    return {
        "total_minutes": total_minutes,
        "duration": format_duration(total_minutes),
        "sessions": len(records),
        "subjects": len(
            {_normalized_subject(record.subject) for record in records}
        ),
        "focus_average": _focus_average(records),
        "score": calculate_provisional_study_score(records),
    }


def get_study_summary_for_period(
    start_date: date,
    end_date: date,
) -> dict:
    records = _records_for_period(start_date, end_date)
    return _summarize_records(records)


def get_recent_study_records(
    limit: int,
    target_date: date | None = None,
) -> list[StudyRecord]:
    statement = db.select(StudyRecord)
    if target_date is not None:
        statement = statement.where(StudyRecord.record_date == target_date)
    return list(
        db.session.scalars(
            statement.order_by(StudyRecord.created_at.desc()).limit(limit)
        )
    )


def _records_for_period(start_date: date, end_date: date) -> list[StudyRecord]:
    if end_date < start_date:
        raise ValueError("A data final deve ser igual ou posterior à inicial.")
    return list(
        db.session.scalars(
            db.select(StudyRecord)
            .where(StudyRecord.record_date.between(start_date, end_date))
            .order_by(StudyRecord.record_date.desc(), StudyRecord.created_at.desc())
        )
    )


def _weekly_data_from_records(
    records: list[StudyRecord],
    reference_date: date,
) -> list[dict]:
    grouped: dict[date, list[StudyRecord]] = defaultdict(list)
    for record in records:
        grouped[record.record_date].append(record)

    weekly = []
    start_date = reference_date - timedelta(days=6)
    for offset in range(7):
        target_date = start_date + timedelta(days=offset)
        day_records = grouped[target_date]
        raw_score = calculate_provisional_study_score(day_records)
        total_minutes = sum(record.duration_minutes for record in day_records)
        weekly.append(
            {
                "date": target_date.isoformat(),
                "date_label": target_date.strftime("%d/%m"),
                "label": weekday_label(target_date),
                "score": raw_score * 5,
                "raw_score": raw_score,
                "total_minutes": total_minutes,
                "duration": format_duration(total_minutes),
                "is_today": target_date == reference_date,
            }
        )
    return weekly


def _subject_datasets(records: list[StudyRecord], weekly: list[dict]) -> list[dict]:
    dates = [item["date"] for item in weekly]
    grouped = defaultdict(lambda: defaultdict(int))
    styles = {}
    for record in records:
        style = subject_catalog_item(record.subject)
        key = style["subject_key"]
        grouped[key][record.record_date.isoformat()] += record.duration_minutes
        styles[key] = style
    return [
        {
            "key": key,
            "label": styles[key]["display_name"],
            "backgroundColor": styles[key]["color"],
            "data": [grouped[key][target] for target in dates],
        }
        for key in sorted(
            grouped,
            key=lambda item: styles[item]["display_name"].casefold(),
        )
    ]


def get_weekly_study_data(reference_date: date | None = None) -> list[dict]:
    reference_date = reference_date or get_local_today()
    records = _records_for_period(
        reference_date - timedelta(days=6),
        reference_date,
    )
    return _weekly_data_from_records(records, reference_date)


def _heatmap_level(minutes: int) -> int:
    if minutes == 0:
        return 0
    if minutes < 30:
        return 1
    if minutes < 60:
        return 2
    if minutes < 120:
        return 3
    if minutes < 180:
        return 4
    return 5


def _monthly_heatmap_from_records(
    records: list[StudyRecord],
    year: int,
    month: int,
    reference_date: date,
) -> dict:
    calendar_data = calendar_metadata(year, month)
    grouped: dict[int, list[StudyRecord]] = defaultdict(list)
    for record in records:
        if record.record_date.year == year and record.record_date.month == month:
            grouped[record.record_date.day].append(record)

    days = []
    for day in range(1, calendar_data["total_days"] + 1):
        day_records = grouped[day]
        total_minutes = sum(record.duration_minutes for record in day_records)
        subjects = sorted(
            {record.subject.strip() for record in day_records},
            key=str.casefold,
        )
        target_date = date(year, month, day)
        subject_text = ", ".join(subjects) if subjects else "nenhuma matéria"
        session_label = "sessão" if len(day_records) == 1 else "sessões"
        days.append(
            {
                "day": day,
                "date": target_date.isoformat(),
                "level": _heatmap_level(total_minutes),
                "is_highlighted": target_date == reference_date,
                "title": (
                    f"{target_date.strftime('%d/%m/%Y')} • "
                    f"{format_duration(total_minutes)} • "
                    f"{len(day_records)} {session_label} • {subject_text}"
                ),
            }
        )

    return {**calendar_data, "days": days}


def get_monthly_study_heatmap(
    year: int,
    month: int,
    reference_date: date | None = None,
) -> dict:
    reference_date = reference_date or get_local_today()
    last_day = calendar_metadata(year, month)["total_days"]
    records = _records_for_period(
        date(year, month, 1),
        date(year, month, last_day),
    )
    return _monthly_heatmap_from_records(
        records,
        year,
        month,
        reference_date,
    )


def _subject_distribution_from_records(
    records: list[StudyRecord],
) -> list[dict]:
    grouped: dict[str, dict] = {}
    for record in records:
        key = _normalized_subject(record.subject)
        display_name = " ".join(record.subject.split())
        if key not in grouped:
            style = subject_catalog_item(record.subject)
            grouped[key] = {
                "name": style["display_name"] if style["subject_key"] != "other" else display_name,
                "subject_key": style["subject_key"],
                "color_key": style["color_key"],
                "color": style["color"],
                "minutes": 0,
                "sessions": 0,
            }
        elif display_name[:1].isupper() and not grouped[key]["name"][:1].isupper():
            grouped[key]["name"] = display_name
        grouped[key]["minutes"] += record.duration_minutes
        grouped[key]["sessions"] += 1

    ordered = sorted(
        grouped.values(),
        key=lambda item: (-item["minutes"], item["name"].casefold()),
    )[:5]
    maximum = ordered[0]["minutes"] if ordered else 0
    for index, item in enumerate(ordered):
        session_label = "sessão" if item["sessions"] == 1 else "sessões"
        item.update(
            {
                "score": round(item["minutes"] / maximum * 100) if maximum else 0,
                "value": (
                    f"{format_duration(item['minutes'])} • "
                    f"{item['sessions']} {session_label}"
                ),
                "bar_label": f"Tempo relativo de {item['name']}",
                "theme": item["color_key"],
            }
        )
    return ordered


def get_subject_distribution(
    start_date: date,
    end_date: date,
) -> list[dict]:
    return _subject_distribution_from_records(
        _records_for_period(start_date, end_date)
    )


def _subject_style(subject: str) -> tuple[str, str]:
    normalized = _normalized_subject(subject)
    for fragment, icon, theme in SUBJECT_STYLES:
        if fragment in normalized:
            return icon, theme
    return "book-open", "blue"


def _session_item(record: StudyRecord) -> dict:
    icon, theme = _subject_style(record.subject)
    details = [record.topic, format_duration(record.duration_minutes)]
    if record.questions_count is not None:
        if record.correct_answers is not None:
            details.append(
                f"{record.correct_answers} de {record.questions_count} questões"
            )
        else:
            details.append(f"{record.questions_count} questões")
    details.append(f"Foco {FOCUS_LABELS.get(record.focus_quality, 'não informado')}")

    if record.questions_count and record.correct_answers is not None:
        value = f"{round(record.correct_answers / record.questions_count * 100)}% acertos"
    else:
        value = format_duration(record.duration_minutes)
    return {
        "name": record.subject,
        "meta": " • ".join(details),
        "value": value,
        "icon": icon,
        "theme": theme,
    }


def _score_message(score: int) -> str:
    return get_score_message(score, 20)


def build_study_page_data(reference_date: date | None = None) -> dict:
    reference_date = reference_date or get_local_today()
    viewing_today = reference_date == get_local_today()
    yesterday = reference_date - timedelta(days=1)
    last_30_start = reference_date - timedelta(days=29)
    month_start = reference_date.replace(day=1)
    query_start = min(yesterday, last_30_start, month_start)

    records = _records_for_period(query_start, reference_date)
    records_by_date: dict[date, list[StudyRecord]] = defaultdict(list)
    for record in records:
        records_by_date[record.record_date].append(record)

    today_records = records_by_date[reference_date]
    yesterday_records = records_by_date[yesterday]
    today_summary = _summarize_records(today_records)
    yesterday_summary = _summarize_records(yesterday_records)
    comparison = build_score_comparison(
        today_summary["score"],
        yesterday_summary["score"],
        bool(yesterday_records),
    )
    time_helper, time_tone = build_metric_comparison(
        today_summary["total_minutes"],
        yesterday_summary["total_minutes"],
        unit="min",
        has_previous=bool(yesterday_records),
    )
    session_helper, session_tone = build_metric_comparison(
        today_summary["sessions"],
        yesterday_summary["sessions"],
        unit="sessions",
        has_previous=bool(yesterday_records),
    )
    evaluated = bool(today_records)
    if not evaluated:
        comparison = {
            "text": "Sem avaliação nesta data",
            "tone": "neutral",
            "icon": "minus",
        }
        time_helper, time_tone = "Nenhum estudo registrado nesta data.", "neutral"
        session_helper, session_tone = "Nenhum estudo registrado nesta data.", "neutral"

    weekly_start = reference_date - timedelta(days=6)
    weekly_records = [
        record for record in records if weekly_start <= record.record_date
    ]
    weekly = _weekly_data_from_records(weekly_records, reference_date)
    subject_records = today_records
    month_records = [
        record for record in records if month_start <= record.record_date
    ]

    return {
        "reference_label": format_local_date_label(reference_date),
        "reference_date": reference_date.isoformat(),
        "is_today": viewing_today,
        "score": {
            "evaluated": evaluated,
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
                if evaluated
                else "Nenhum estudo registrado nesta data."
            ),
        },
        "metrics": [
            {
                "title": "Tempo estudado hoje" if viewing_today else "Tempo estudado na data",
                "value": today_summary["duration"],
                "helper": time_helper,
                "helper_tone": time_tone,
                "icon": "clock-3",
                "theme": "blue",
            },
            {
                "title": "Sessões",
                "value": str(today_summary["sessions"]),
                "helper": session_helper,
                "helper_tone": session_tone,
                "icon": "list-checks",
                "theme": "purple",
            },
            {
                "title": "Matérias",
                "value": str(today_summary["subjects"]),
                "helper": (
                    "Ativas hoje" if viewing_today else "Ativas na data"
                    if today_summary["subjects"]
                    else "Sem registros nesta data"
                ),
                "helper_tone": "neutral",
                "icon": "book-open",
                "theme": "green",
            },
            {
                "title": "Foco médio",
                "value": (
                    f"{today_summary['focus_average']}%"
                    if today_summary["focus_average"] is not None
                    else "—"
                ),
                "helper": _focus_status(today_summary["focus_average"]),
                "helper_tone": "neutral",
                "icon": "target",
                "theme": "orange",
            },
        ],
        "sessions": [_session_item(record) for record in today_records[:4]],
        "sessions_empty": {
            "title": (
                "Nenhum estudo registrado hoje"
                if viewing_today
                else "Nenhum estudo registrado nesta data"
            ),
            "description": (
                "Registre seu primeiro estudo para acompanhar seu progresso."
            ),
            "link_label": "Registrar estudo",
            "link_href": (
                f"/registrar?categoria=estudo&date={reference_date.isoformat()}"
            ),
        },
        "weekly": {
            "labels": [item["label"] for item in weekly],
            "scores": [item["score"] for item in weekly],
            "details": weekly,
            "datasets": _subject_datasets(weekly_records, weekly),
            "filter": "Últimos 7 dias",
        },
        "subjects": _subject_distribution_from_records(subject_records),
        "subjects_empty": "Nenhuma matéria registrada nesta data.",
        "next_session": {
            "title": "Próxima sessão",
            "subtitle": "Nenhuma sessão planejada.",
            "plan": "Crie uma nova sessão quando estiver pronto.",
            "subject": "Sem matéria definida",
            "duration": "—",
            "schedule": "Sem horário",
            "status": "Não planejada",
            "is_demonstrative": False,
        },
        "heatmap": _monthly_heatmap_from_records(
            month_records,
            reference_date.year,
            reference_date.month,
            reference_date,
        ),
    }
