from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from app.extensions import db
from app.models import (
    HydrationRecord,
    MealRecord,
    SessionRecord,
    SleepRecord,
    StudyRecord,
    TrainingRecord,
    ComputerActivityBlock,
)
from app.services.analytics_utils import (
    calendar_metadata,
    format_duration,
    format_local_date_label,
    get_app_timezone,
    get_local_today,
    weekday_label,
)
from app.services.nutrition_service import format_hydration
from app.services.scoring_service import (
    MAX_FINAL_SCORE,
    TOTAL_CATEGORIES,
    _round_half_up,
    calculate_computer_score,
    calculate_daily_score,
    calculate_nutrition_score,
    calculate_session_bonus,
    calculate_sleep_score,
    calculate_study_score,
    calculate_training_score,
    get_score_coverage,
    get_score_message,
)
from app.services.computer_service import summarize_blocks


CATEGORY_PRESENTATION = {
    "study": {
        "name": "Estudo",
        "icon": "book-open",
        "theme": "blue",
        "endpoint": "main.estudo",
    },
    "training": {
        "name": "Treino",
        "icon": "dumbbell",
        "theme": "green",
        "endpoint": "main.treino",
    },
    "sleep": {
        "name": "Sono",
        "icon": "moon-star",
        "theme": "purple",
        "endpoint": "main.sono",
    },
    "computer": {
        "name": "Computador",
        "icon": "monitor",
        "theme": "orange",
        "endpoint": "main.computador",
    },
    "nutrition": {
        "name": "Alimentação",
        "icon": "apple",
        "theme": "teal",
        "endpoint": "main.alimentacao",
    },
}
MEAL_TYPE_LABELS = {
    "breakfast": "Café da manhã",
    "lunch": "Almoço",
    "snack": "Lanche",
    "dinner": "Jantar",
    "supper": "Ceia",
    "other": "refeição",
}


def _records_for_period(start_date: date, end_date: date) -> dict[str, list[Any]]:
    """Carrega cada fonte uma vez para calendário, consistência e feitos."""
    if end_date < start_date:
        raise ValueError("A data final deve ser igual ou posterior à inicial.")

    def load(model: Any) -> list[Any]:
        return list(
            db.session.scalars(
                db.select(model).where(model.record_date.between(start_date, end_date))
            )
        )

    return {
        "study": load(StudyRecord),
        "training": load(TrainingRecord),
        "sleep": load(SleepRecord),
        "meal": load(MealRecord),
        "hydration": load(HydrationRecord),
        "session": load(SessionRecord),
        "computer": load(ComputerActivityBlock),
    }


def _group_records(loaded: dict[str, list[Any]]) -> dict[str, dict[date, list[Any]]]:
    grouped: dict[str, dict[date, list[Any]]] = {}
    for key, records in loaded.items():
        by_date: dict[date, list[Any]] = defaultdict(list)
        for record in records:
            by_date[record.record_date].append(record)
        grouped[key] = by_date
    return grouped


def _daily_score_from_loaded(
    target_date: date,
    grouped: dict[str, dict[date, list[Any]]],
) -> dict[str, Any]:
    """Orquestra calculadoras oficiais sobre dados já carregados, sem N+1."""
    training_window = [
        record
        for offset in range(7)
        for record in grouped["training"].get(
            target_date - timedelta(days=offset),
            [],
        )
    ]
    categories = {
        "study": calculate_study_score(grouped["study"].get(target_date, [])),
        "training": calculate_training_score(
            grouped["training"].get(target_date, []),
            training_window,
        ),
        "sleep": calculate_sleep_score(
            next(iter(grouped["sleep"].get(target_date, [])), None)
        ),
        "nutrition": calculate_nutrition_score(
            grouped["meal"].get(target_date, []),
            grouped["hydration"].get(target_date, []),
        ),
        "computer": calculate_computer_score(
            summarize_blocks(
                grouped["computer"].get(target_date, []),
                focused_sessions_count=sum(
                    session.status == "completed"
                    and session.related_category == "computer"
                    for session in grouped["session"].get(target_date, [])
                ),
            )
        ),
    }
    coverage = get_score_coverage(categories)
    evaluated = [item for item in categories.values() if item["evaluated"]]
    raw_base_score = sum(item["score"] for item in evaluated)
    raw_base_max = len(evaluated) * 20
    normalized_base_score = (
        _round_half_up(raw_base_score / raw_base_max * 100)
        if raw_base_max
        else 0
    )
    session_detail = calculate_session_bonus(
        grouped["session"].get(target_date, [])
    )
    session_bonus = session_detail["score"]
    final_score = min(
        normalized_base_score + session_bonus,
        MAX_FINAL_SCORE,
    )
    return {
        "date": target_date.isoformat(),
        "categories": categories,
        "raw_base_score": raw_base_score,
        "raw_base_max": raw_base_max,
        "normalized_base_score": normalized_base_score,
        **coverage,
        "session_bonus": session_bonus,
        "session_bonus_detail": session_detail,
        "final_score": final_score,
        "max_final_score": MAX_FINAL_SCORE,
        "message": get_score_message(final_score),
        "day_closed": False,
    }


def _build_daily_cache(
    start_date: date,
    end_date: date,
    grouped: dict[str, dict[date, list[Any]]],
) -> dict[date, dict[str, Any]]:
    return {
        start_date + timedelta(days=offset): _daily_score_from_loaded(
            start_date + timedelta(days=offset),
            grouped,
        )
        for offset in range((end_date - start_date).days + 1)
    }


def _comparison(today: dict[str, Any], yesterday: dict[str, Any]) -> dict[str, str]:
    yesterday_has_data = (
        yesterday["evaluated_categories"] > 0 or yesterday["session_bonus"] > 0
    )
    if not yesterday_has_data:
        return {
            "text": "Sem comparação com ontem",
            "tone": "neutral",
            "icon": "minus",
            "coverage": "Sem cobertura comparável",
        }

    difference = today["final_score"] - yesterday["final_score"]
    coverage_difference = (
        today["evaluated_categories"] - yesterday["evaluated_categories"]
    )
    if difference > 0:
        text = f"+{difference} vs ontem"
        tone = "positive"
        icon = "trending-up"
    elif difference < 0:
        text = f"{difference} vs ontem"
        tone = "negative"
        icon = "trending-down"
    else:
        text = "Mesmo resultado de ontem"
        tone = "neutral"
        icon = "minus"

    if coverage_difference < 0:
        absolute = abs(coverage_difference)
        label = "categoria" if absolute == 1 else "categorias"
        agreement = "avaliada" if absolute == 1 else "avaliadas"
        text = f"{text}, com {absolute} {label} a menos {agreement}"
    if coverage_difference == 0:
        coverage_text = "Mesma cobertura de ontem"
    else:
        sign = "+" if coverage_difference > 0 else ""
        coverage_text = f"Cobertura: {sign}{coverage_difference} categoria"
        if abs(coverage_difference) != 1:
            coverage_text += "s"
    return {
        "text": text,
        "tone": tone,
        "icon": icon,
        "coverage": coverage_text,
    }


def _category_cards(daily_score: dict[str, Any]) -> list[dict[str, Any]]:
    cards = []
    for key, presentation in CATEGORY_PRESENTATION.items():
        result = daily_score["categories"][key]
        warning = ""
        if result["warnings"]:
            warning = (
                "Atenção ao desconforto registrado."
                if key == "training"
                else result["warnings"][0]
            )
        cards.append(
            {
                **presentation,
                "key": key,
                "evaluated": result["evaluated"],
                "score": result["score"],
                "display_score": (
                    str(result["score"]) if result["evaluated"] else "—"
                ),
                "max_score": result["max_score"],
                "percentage": result["percentage"] if result["evaluated"] else 0,
                "status": (
                    result["message"]
                    if result["evaluated"]
                    else "Ainda não avaliada hoje"
                ),
                "warning": warning,
            }
        )
    return cards


def _as_local_datetime(value: datetime | None, fallback_date: date) -> datetime:
    app_timezone = get_app_timezone()
    if value is None:
        return datetime.combine(fallback_date, time.min, app_timezone)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(app_timezone)


def _clock_datetime(target_date: date, value: time | None) -> datetime:
    return datetime.combine(
        target_date,
        value or time.min,
        get_app_timezone(),
    )


def _accomplishments_from_loaded(
    reference_date: date,
    loaded: dict[str, list[Any]],
    limit: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def add(
        category: str,
        text: str,
        occurred_at: datetime,
        icon: str,
        theme: str,
        endpoint: str,
        record_type: str,
        record_id: int,
    ) -> None:
        items.append(
            {
                "category": category,
                "text": text,
                "time": occurred_at.strftime("%H:%M"),
                "icon": icon,
                "theme": theme,
                "endpoint": endpoint,
                "href": f"/historico?registro={record_type}:{record_id}",
                "_sort_at": occurred_at,
            }
        )

    for record in loaded["study"]:
        if record.record_date == reference_date:
            add(
                "Estudo",
                f"Estudou {record.subject} por {format_duration(record.duration_minutes)}",
                _as_local_datetime(record.created_at, reference_date),
                "book-open",
                "blue",
                "main.estudo",
                "study",
                record.id,
            )
    for record in loaded["training"]:
        if record.record_date == reference_date:
            add(
                "Treino",
                f"Concluiu {record.activity_name} em {format_duration(record.duration_minutes)}",
                _as_local_datetime(record.created_at, reference_date),
                "dumbbell",
                "green",
                "main.treino",
                "training",
                record.id,
            )
    for record in loaded["sleep"]:
        if record.record_date == reference_date:
            add(
                "Sono",
                f"Registrou {format_duration(record.duration_minutes)} de sono",
                _as_local_datetime(record.created_at, reference_date),
                "moon-star",
                "purple",
                "main.sono",
                "sleep",
                record.id,
            )
    for record in loaded["meal"]:
        if record.record_date == reference_date:
            add(
                "Alimentação",
                "Registrou "
                + MEAL_TYPE_LABELS.get(record.meal_type, "refeição"),
                _clock_datetime(reference_date, record.meal_time),
                "utensils",
                "teal",
                "main.alimentacao",
                "meal",
                record.id,
            )
    for record in loaded["hydration"]:
        if record.record_date == reference_date:
            add(
                "Alimentação",
                f"Registrou {format_hydration(record.amount_ml)} de água",
                _clock_datetime(reference_date, record.consumed_at),
                "droplet",
                "blue",
                "main.alimentacao",
                "hydration",
                record.id,
            )
    for record in loaded["session"]:
        if record.record_date == reference_date and record.status == "completed":
            add(
                "Sessão",
                f"Concluiu a sessão {record.title}",
                _as_local_datetime(
                    record.finished_at or record.created_at,
                    reference_date,
                ),
                "focus",
                "blue",
                "main.sessao",
                "session",
                record.id,
            )

    items.sort(key=lambda item: item["_sort_at"], reverse=True)
    for item in items:
        item.pop("_sort_at", None)
    return items[: max(0, limit)]


def get_daily_accomplishments(
    reference_date: date,
    limit: int = 5,
    *,
    loaded: dict[str, list[Any]] | None = None,
) -> list[dict[str, Any]]:
    loaded = loaded or _records_for_period(reference_date, reference_date)
    return _accomplishments_from_loaded(reference_date, loaded, limit)


def get_yesterday_summary(
    reference_date: date,
    *,
    daily_score: dict[str, Any] | None = None,
) -> dict[str, Any]:
    yesterday = reference_date - timedelta(days=1)
    daily_score = daily_score or calculate_daily_score(yesterday)
    evaluated = [
        (key, result)
        for key, result in daily_score["categories"].items()
        if result["evaluated"]
    ]
    if not evaluated and daily_score["session_bonus"] == 0:
        return {
            "available": False,
            "title": "Não há dados suficientes de ontem.",
            "items": [],
        }

    best = max(evaluated, key=lambda item: item[1]["score"]) if evaluated else None
    worst = min(evaluated, key=lambda item: item[1]["score"]) if evaluated else None

    def area_text(item: tuple[str, dict[str, Any]] | None) -> str:
        if item is None:
            return "Nenhuma categoria avaliada"
        key, result = item
        return (
            f"{CATEGORY_PRESENTATION[key]['name']} — "
            f"{result['score']}/{result['max_score']}"
        )

    return {
        "available": True,
        "title": f"Ontem você fez {daily_score['final_score']} pontos",
        "items": [
            f"Base: {daily_score['normalized_base_score']}/100",
            f"Bônus de sessão: +{daily_score['session_bonus']}",
            (
                f"{daily_score['evaluated_categories']} de "
                f"{TOTAL_CATEGORIES} categorias avaliadas"
            ),
            f"Melhor área: {area_text(best)}",
            f"Menor pontuação: {area_text(worst)}",
        ],
        "best_category": area_text(best),
        "lowest_category": area_text(worst),
    }


def _calendar_level(daily_score: dict[str, Any]) -> int:
    if daily_score["evaluated_categories"] == 0:
        return 0
    score = daily_score["final_score"]
    if score <= 39:
        level = 1
    elif score <= 59:
        level = 2
    elif score <= 74:
        level = 3
    elif score <= 89:
        level = 4
    else:
        level = 5
    if daily_score["coverage_percentage"] < 60:
        level = max(1, level - 1)
    return level


def get_home_month_calendar(
    year: int,
    month: int,
    *,
    reference_date: date | None = None,
    daily_scores: dict[date, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reference_date = reference_date or get_local_today()
    metadata = calendar_metadata(year, month)
    first_day = date(year, month, 1)
    last_day = date(year, month, metadata["total_days"])
    if daily_scores is None:
        loaded = _records_for_period(first_day - timedelta(days=6), last_day)
        grouped = _group_records(loaded)
        daily_scores = _build_daily_cache(first_day, last_day, grouped)

    days = []
    for day_number in range(1, metadata["total_days"] + 1):
        target_date = date(year, month, day_number)
        score = daily_scores[target_date]
        days.append(
            {
                "day": day_number,
                "level": _calendar_level(score),
                "is_highlighted": target_date == reference_date,
                "title": (
                    f"{target_date.strftime('%d/%m/%Y')} • "
                    f"{score['final_score']} pontos • "
                    f"Base {score['normalized_base_score']}/100 • "
                    f"Bônus +{score['session_bonus']} • "
                    f"Cobertura {score['coverage_percentage']}% • "
                    f"{score['evaluated_categories']} de {TOTAL_CATEGORIES} categorias"
                ),
            }
        )
    return {**metadata, "days": days}


def get_consistency_summary(
    reference_date: date,
    *,
    daily_scores: dict[date, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    start_date = reference_date - timedelta(days=6)
    if daily_scores is None:
        loaded = _records_for_period(start_date - timedelta(days=6), reference_date)
        grouped = _group_records(loaded)
        daily_scores = _build_daily_cache(start_date, reference_date, grouped)

    days = []
    for offset in range(7):
        target_date = start_date + timedelta(days=offset)
        score = daily_scores[target_date]
        is_consistent = (
            score["evaluated_categories"] >= 3
            and score["normalized_base_score"] >= 60
        )
        days.append(
            {
                "date": target_date.isoformat(),
                "label": weekday_label(target_date),
                "is_consistent": is_consistent,
                "title": (
                    f"{target_date.strftime('%d/%m')} • "
                    f"{score['evaluated_categories']} categorias • "
                    f"Base {score['normalized_base_score']}/100"
                ),
            }
        )
    count = sum(day["is_consistent"] for day in days)
    if count <= 1:
        message = "Começando"
    elif count <= 3:
        message = "Em evolução"
    elif count <= 5:
        message = "Boa consistência"
    else:
        message = "Excelente consistência"
    return {
        "days": count,
        "period": "nos últimos 7 dias",
        "message": message,
        "weekdays": days,
        "rule": "Dia consistente: 3 categorias avaliadas e base mínima de 60.",
    }


def get_home_cta_state(daily_score: dict[str, Any]) -> dict[str, Any]:
    evaluated = daily_score["evaluated_categories"]
    if evaluated == 0:
        return {
            "title": "Vamos começar hoje?",
            "description": "Registre sua primeira atividade ou inicie uma sessão.",
            "primary_label": "Registrar",
            "primary_endpoint": "main.registrar",
            "secondary_label": "Iniciar sessão",
            "secondary_endpoint": "main.sessao",
        }
    if evaluated < TOTAL_CATEGORIES:
        return {
            "title": "Continue construindo seu dia",
            "description": f"Você avaliou {evaluated} de {TOTAL_CATEGORIES} categorias.",
            "primary_label": "Registrar próxima categoria",
            "primary_endpoint": "main.registrar",
            "secondary_label": "Iniciar sessão",
            "secondary_endpoint": "main.sessao",
        }
    return {
        "title": "Seu dia está completo",
        "description": "Você avaliou todas as categorias de hoje.",
        "primary_label": "Ver detalhes",
        "primary_href": "#categories-title",
        "secondary_label": "Iniciar sessão",
        "secondary_endpoint": "main.sessao",
    }


def get_home_page_data(reference_date: date | None = None) -> dict[str, Any]:
    reference_date = reference_date or get_local_today()
    yesterday_date = reference_date - timedelta(days=1)
    month_first = reference_date.replace(day=1)
    month_last = date(
        reference_date.year,
        reference_date.month,
        calendar.monthrange(reference_date.year, reference_date.month)[1],
    )
    load_start = min(month_first, reference_date - timedelta(days=6)) - timedelta(
        days=6
    )
    load_end = max(month_last, reference_date)
    loaded = _records_for_period(load_start, load_end)
    grouped = _group_records(loaded)
    cache_start = min(month_first, reference_date - timedelta(days=6))
    daily_scores = _build_daily_cache(cache_start, month_last, grouped)

    # Hoje e ontem usam diretamente o agregador oficial solicitado.
    today_score = calculate_daily_score(reference_date)
    yesterday_score = calculate_daily_score(yesterday_date)
    daily_scores[reference_date] = today_score
    if yesterday_date in daily_scores:
        daily_scores[yesterday_date] = yesterday_score

    comparison = _comparison(today_score, yesterday_score)
    coverage_label = (
        f"{today_score['evaluated_categories']} de "
        f"{TOTAL_CATEGORIES} categorias avaliadas"
    )
    coverage_note = (
        f"{today_score['normalized_base_score']} pontos nas categorias avaliadas"
        if today_score["normalized_base_score"] == 100
        and today_score["coverage_percentage"] < 100
        else f"Base: {today_score['normalized_base_score']}/100"
    )

    return {
        "today": {
            "date": reference_date.isoformat(),
            "date_label": format_local_date_label(reference_date),
            "daily_score": today_score,
        },
        "yesterday": {
            "date": yesterday_date.isoformat(),
            "daily_score": yesterday_score,
        },
        "score": {
            "value": today_score["final_score"],
            "ring_value": today_score["normalized_base_score"],
            "base": today_score["normalized_base_score"],
            "bonus": today_score["session_bonus"],
            "coverage": coverage_label,
            "coverage_note": coverage_note,
            "comparison": comparison["text"],
            "comparison_tone": comparison["tone"],
            "comparison_icon": comparison["icon"],
            "coverage_comparison": comparison["coverage"],
            "helper": today_score["message"],
        },
        "categories": _category_cards(today_score),
        "accomplishments": get_daily_accomplishments(
            reference_date,
            loaded=loaded,
        ),
        "yesterday_summary": get_yesterday_summary(
            reference_date,
            daily_score=yesterday_score,
        ),
        "calendar": get_home_month_calendar(
            reference_date.year,
            reference_date.month,
            reference_date=reference_date,
            daily_scores=daily_scores,
        ),
        "consistency": get_consistency_summary(
            reference_date,
            daily_scores=daily_scores,
        ),
        "cta": get_home_cta_state(today_score),
    }
