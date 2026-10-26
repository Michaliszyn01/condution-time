from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from typing import Any, Mapping
from urllib.parse import urlencode

from app.extensions import db
from app.models import (
    HydrationRecord,
    MealRecord,
    SessionRecord,
    SleepRecord,
    StudyRecord,
    TrainingRecord,
)
from app.services.analytics_utils import MONTH_NAMES, get_app_timezone, get_local_today
from app.services.scoring_service import calculate_session_bonus


PAGE_SIZE = 15
MAX_CUSTOM_DAYS = 366
MAX_ALL_PER_TYPE = 500
ALLOWED_CATEGORIES = {
    "all",
    "study",
    "training",
    "sleep",
    "meal",
    "hydration",
    "session",
}
ALLOWED_PERIODS = {"today", "yesterday", "7d", "30d", "month", "custom", "all"}
ALLOWED_SESSION_STATUSES = {"all", "completed", "cancelled", "running", "paused"}

CATEGORY_META = {
    "study": ("Estudo", "book-open", "blue"),
    "training": ("Treino", "dumbbell", "green"),
    "sleep": ("Sono", "moon-star", "purple"),
    "meal": ("Alimentação", "utensils", "orange"),
    "hydration": ("Hidratação", "glass-water", "blue"),
    "session": ("Sessões", "timer", "purple"),
}
MODEL_MAP = {
    "study": StudyRecord,
    "training": TrainingRecord,
    "sleep": SleepRecord,
    "meal": MealRecord,
    "hydration": HydrationRecord,
    "session": SessionRecord,
}
FOCUS_LABELS = {
    "low": "baixo",
    "regular": "regular",
    "good": "bom",
    "very_good": "muito bom",
    "excellent": "excelente",
}
TRAINING_LABELS = {
    "strength": "Musculação",
    "running": "Corrida",
    "walking": "Caminhada",
    "swimming": "Natação",
    "cycling": "Ciclismo",
    "sport": "Esporte",
    "mobility": "Mobilidade",
    "other": "Outro",
}
PERFORMANCE_LABELS = {
    "bad": "Ruim",
    "regular": "Regular",
    "good": "Bom",
    "very_good": "Muito bom",
    "excellent": "Excelente",
}
QUALITY_LABELS = {
    "terrible": "Péssima",
    "very_bad": "Muito ruim",
    "bad": "Ruim",
    "regular": "Regular",
    "good": "Boa",
    "excellent": "Excelente",
}
MEAL_LABELS = {
    "breakfast": "Café da manhã",
    "lunch": "Almoço",
    "snack": "Lanche",
    "dinner": "Jantar",
    "supper": "Ceia",
    "other": "Outra",
}
STATUS_LABELS = {
    "completed": "Concluída",
    "cancelled": "Cancelada",
    "running": "Em andamento",
    "paused": "Pausada",
}


class HistoryFilterError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Filtros inválidos.")
        self.errors = errors


class HistoryRecordNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class HistoryFilters:
    category: str
    period: str
    start_date: date | None
    end_date: date | None
    query: str
    session_status: str
    page: int

    def as_query(self) -> dict[str, str]:
        payload = {
            "categoria": self.category,
            "periodo": self.period,
            "status": self.session_status,
        }
        if self.query:
            payload["busca"] = self.query
        if self.start_date and self.period == "custom":
            payload["inicio"] = self.start_date.isoformat()
        if self.end_date and self.period == "custom":
            payload["fim"] = self.end_date.isoformat()
        return payload


def _parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise HistoryFilterError({field: "Use uma data válida."}) from None


def parse_history_filters(args: Mapping[str, Any]) -> HistoryFilters:
    today = get_local_today()
    category = str(args.get("categoria", "all")).strip().casefold()
    period = str(args.get("periodo", "30d")).strip().casefold()
    status = str(args.get("status", "all")).strip().casefold()
    query = " ".join(str(args.get("busca", "")).split())
    try:
        page = int(args.get("page", 1))
    except (TypeError, ValueError):
        raise HistoryFilterError({"page": "Informe uma página válida."}) from None

    errors: dict[str, str] = {}
    if category not in ALLOWED_CATEGORIES:
        errors["categoria"] = "Selecione uma categoria válida."
    if period not in ALLOWED_PERIODS:
        errors["periodo"] = "Selecione um período válido."
    if status not in ALLOWED_SESSION_STATUSES:
        errors["status"] = "Selecione um status válido."
    if len(query) > 100:
        errors["busca"] = "Use no máximo 100 caracteres."
    if page < 1:
        errors["page"] = "A página deve ser maior que zero."
    if errors:
        raise HistoryFilterError(errors)

    start_date: date | None
    end_date: date | None
    if period == "today":
        start_date = end_date = today
    elif period == "yesterday":
        start_date = end_date = today - timedelta(days=1)
    elif period == "7d":
        start_date, end_date = today - timedelta(days=6), today
    elif period == "30d":
        start_date, end_date = today - timedelta(days=29), today
    elif period == "month":
        start_date, end_date = today.replace(day=1), today
    elif period == "custom":
        start_date = _parse_date(args.get("inicio"), "inicio")
        end_date = _parse_date(args.get("fim"), "fim")
        if start_date > end_date:
            raise HistoryFilterError(
                {"inicio": "A data inicial não pode ser posterior à final."}
            )
        if (end_date - start_date).days >= MAX_CUSTOM_DAYS:
            raise HistoryFilterError(
                {"fim": "O período personalizado deve ter no máximo 1 ano."}
            )
    else:
        start_date = end_date = None

    return HistoryFilters(
        category=category,
        period=period,
        start_date=start_date,
        end_date=end_date,
        query=query,
        session_status=status,
        page=page,
    )


def _created_utc(record: Any) -> datetime:
    value = record.created_at
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _local_event(record: Any, event_time: time | None = None) -> datetime:
    if event_time is None:
        return _created_utc(record).astimezone(get_app_timezone())
    return datetime.combine(record.record_date, event_time, get_app_timezone())


def _duration_label(minutes: int | None) -> str:
    minutes = max(0, int(minutes or 0))
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h {remainder}min"
    if hours:
        return f"{hours}h"
    return f"{remainder} min"


def _seconds_label(seconds: int | None) -> str:
    seconds = max(0, int(seconds or 0))
    minutes = seconds // 60
    return _duration_label(minutes)


def _base_item(
    record: Any,
    record_type: str,
    title: str,
    summary: str,
    event_datetime: datetime,
    *,
    status: str | None = None,
    counted_duration_minutes: int = 0,
) -> dict[str, Any]:
    label, icon, theme = CATEGORY_META[record_type]
    return {
        "record_type": record_type,
        "record_id": record.id,
        "category_label": label,
        "title": title,
        "summary": summary,
        "record_date": record.record_date.isoformat(),
        "event_datetime": event_datetime.isoformat(),
        "time_label": event_datetime.strftime("%H:%M"),
        "status": status,
        "status_label": STATUS_LABELS.get(status),
        "icon": icon,
        "theme": theme,
        "editable": record_type != "session",
        "deletable": record_type != "session",
        "counted_duration_minutes": max(0, counted_duration_minutes),
    }


def serialize_study_record(record: StudyRecord) -> dict[str, Any]:
    questions = ""
    if record.questions_count is not None:
        questions = f" • {record.correct_answers or 0} de {record.questions_count} questões"
    return _base_item(
        record,
        "study",
        f"{record.subject} — {record.topic}",
        f"{_duration_label(record.duration_minutes)} • Foco {FOCUS_LABELS.get(record.focus_quality, record.focus_quality)}{questions}",
        _local_event(record),
        counted_duration_minutes=record.duration_minutes,
    )


def serialize_training_record(record: TrainingRecord) -> dict[str, Any]:
    return _base_item(
        record,
        "training",
        record.activity_name,
        (
            f"{TRAINING_LABELS.get(record.training_type, record.training_type)} • "
            f"{_duration_label(record.duration_minutes)} • "
            + (
                f"Intensidade {record.intensity}/10"
                if record.intensity is not None
                else "dados do relógio"
            )
        ),
        _local_event(record),
        counted_duration_minutes=record.duration_minutes,
    )


def serialize_sleep_record(record: SleepRecord) -> dict[str, Any]:
    quality = QUALITY_LABELS.get(
        record.perceived_quality,
        record.perceived_quality,
    )
    quality_label = quality.casefold() if quality else "não informada"
    return _base_item(
        record,
        "sleep",
        "Registro de sono",
        f"{_duration_label(record.duration_minutes)} • "
        f"Qualidade {quality_label} • "
        f"{record.awakenings_count} interrupções",
        _local_event(record, record.sleep_end),
    )


def serialize_meal_record(record: MealRecord) -> dict[str, Any]:
    return _base_item(
        record,
        "meal",
        MEAL_LABELS.get(record.meal_type, record.meal_type),
        record.foods_text,
        _local_event(record, record.meal_time),
    )


def serialize_hydration_record(record: HydrationRecord) -> dict[str, Any]:
    amount = (
        f"{record.amount_ml / 1000:g} L de água"
        if record.amount_ml >= 1000
        else f"{record.amount_ml} ml de água"
    )
    return _base_item(
        record,
        "hydration",
        "Hidratação",
        amount,
        _local_event(record, record.consumed_at),
    )


def serialize_session_record(record: SessionRecord) -> dict[str, Any]:
    bonus = calculate_session_bonus([record])["sessions"][0]["score"]
    type_label = {
        "study": "Estudo",
        "programming": "Programação",
        "work": "Trabalho",
        "reading": "Leitura",
        "project": "Projeto",
        "other": "Outro",
    }.get(record.session_type, record.session_type)
    summary = f"{type_label} • {_seconds_label(record.actual_duration_seconds)}"
    if record.status == "completed":
        summary += f" • Bônus +{bonus}"
    event = record.finished_at or record.started_at or record.created_at
    if event.tzinfo is None:
        event = event.replace(tzinfo=timezone.utc)
    return _base_item(
        record,
        "session",
        record.title,
        summary,
        event.astimezone(get_app_timezone()),
        status=record.status,
        counted_duration_minutes=(
            int(record.actual_duration_seconds or 0) // 60
            if record.status == "completed"
            else 0
        ),
    )


SERIALIZERS = {
    "study": serialize_study_record,
    "training": serialize_training_record,
    "sleep": serialize_sleep_record,
    "meal": serialize_meal_record,
    "hydration": serialize_hydration_record,
    "session": serialize_session_record,
}


def _matches_search(record: Any, record_type: str, query: str) -> bool:
    if not query:
        return True
    field_names = {
        "study": ("subject", "topic"),
        "training": ("activity_name", "training_type"),
        "meal": ("foods_text", "meal_type"),
        "session": ("title", "session_type"),
        "sleep": (),
        "hydration": (),
    }[record_type]
    fields = (getattr(record, field, None) for field in field_names)
    needle = query.casefold()
    return any(needle in str(value or "").casefold() for value in fields)


def _query_type(record_type: str, filters: HistoryFilters) -> list[Any]:
    model = MODEL_MAP[record_type]
    statement = db.select(model).order_by(
        model.record_date.desc(), model.created_at.desc(), model.id.desc()
    )
    if filters.start_date and filters.end_date:
        statement = statement.where(
            model.record_date.between(filters.start_date, filters.end_date)
        )
    if record_type == "session" and filters.session_status != "all":
        statement = statement.where(SessionRecord.status == filters.session_status)
    statement = statement.limit(MAX_ALL_PER_TYPE)
    return list(db.session.scalars(statement))


def get_unified_history(filters: HistoryFilters) -> list[dict[str, Any]]:
    requested_types = (
        MODEL_MAP.keys() if filters.category == "all" else (filters.category,)
    )
    items: list[dict[str, Any]] = []
    for record_type in requested_types:
        for record in _query_type(record_type, filters):
            if _matches_search(record, record_type, filters.query):
                items.append(SERIALIZERS[record_type](record))
    items.sort(
        key=lambda item: (item["event_datetime"], item["record_id"]),
        reverse=True,
    )
    return items


def get_history_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    days: set[str] = set()
    duration_minutes = 0
    for item in items:
        record_type = item["record_type"]
        counts[record_type] = counts.get(record_type, 0) + 1
        days.add(item["record_date"])
        duration_minutes += item["counted_duration_minutes"]

    top_type = max(counts, key=lambda key: (counts[key], key)) if counts else None
    return {
        "total_records": len(items),
        "duration": _duration_label(duration_minutes),
        "active_days": len(days),
        "top_category": CATEGORY_META[top_type][0] if top_type else "—",
        "top_category_count": counts.get(top_type, 0) if top_type else 0,
    }


def _group_label(record_date: date) -> str:
    today = get_local_today()
    if record_date == today:
        return "Hoje"
    if record_date == today - timedelta(days=1):
        return "Ontem"
    return f"{record_date.day} de {MONTH_NAMES[record_date.month].casefold()} de {record_date.year}"


def _group_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for item in items:
        if not groups or groups[-1]["date"] != item["record_date"]:
            record_date = date.fromisoformat(item["record_date"])
            groups.append(
                {
                    "date": item["record_date"],
                    "label": _group_label(record_date),
                    "items": [],
                }
            )
        groups[-1]["items"].append(item)
    return groups


def get_history_page_data(filters: HistoryFilters) -> dict[str, Any]:
    all_items = get_unified_history(filters)
    summary = get_history_summary(all_items)
    total = len(all_items)
    total_pages = max(1, ceil(total / PAGE_SIZE))
    page = min(filters.page, total_pages)
    start = (page - 1) * PAGE_SIZE
    page_items = all_items[start : start + PAGE_SIZE]
    page_numbers = list(range(max(1, page - 2), min(total_pages, page + 2) + 1))
    return {
        "filters": filters,
        "filter_query": filters.as_query(),
        "summary": summary,
        "groups": _group_items(page_items),
        "pagination": {
            "page": page,
            "total_pages": total_pages,
            "total_records": total,
            "page_numbers": page_numbers,
            "has_previous": page > 1,
            "has_next": page < total_pages,
            "base_query": urlencode(filters.as_query()),
        },
        "categories": [
            ("all", "Todas"),
            ("study", "Estudo"),
            ("training", "Treino"),
            ("sleep", "Sono"),
            ("meal", "Alimentação"),
            ("hydration", "Hidratação"),
            ("session", "Sessões"),
        ],
        "periods": [
            ("today", "Hoje"),
            ("yesterday", "Ontem"),
            ("7d", "Últimos 7 dias"),
            ("30d", "Últimos 30 dias"),
            ("month", "Este mês"),
            ("custom", "Personalizado"),
            ("all", "Todos"),
        ],
        "session_statuses": [
            ("all", "Todos"),
            ("completed", "Concluída"),
            ("cancelled", "Cancelada"),
            ("running", "Em andamento"),
            ("paused", "Pausada"),
        ],
    }


def get_record(record_type: str, record_id: int) -> Any:
    model = MODEL_MAP.get(record_type)
    if model is None:
        raise HistoryRecordNotFoundError("Tipo de registro inválido.")
    record = db.session.get(model, record_id)
    if record is None:
        raise HistoryRecordNotFoundError("Registro não encontrado.")
    return record
