from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable

from flask import current_app

from app.extensions import db
from app.models import HydrationRecord, MealRecord
from app.services.analytics_utils import (
    build_metric_comparison,
    build_score_comparison,
    calendar_metadata,
    format_local_date_label,
    get_local_today,
    weekday_label,
)
from app.services.scoring_service import calculate_nutrition_score, get_score_message


MEAL_TYPE_LABELS = {
    "breakfast": "Café da manhã",
    "lunch": "Almoço",
    "snack": "Lanche",
    "dinner": "Jantar",
    "supper": "Ceia",
    "other": "Outra",
}
MEAL_TYPE_STYLES = {
    "breakfast": ("sunrise", "orange"),
    "lunch": ("utensils", "green"),
    "snack": ("apple", "purple"),
    "dinner": ("moon-star", "orange"),
    "supper": ("moon-star", "purple"),
    "other": ("utensils", "green"),
}
TRINARY_LABELS = {
    "yes": "Sim",
    "no": "Não",
    "unknown": "Não sei",
}
MEAL_QUALITY_LABELS = {
    "very_bad": "Muito ruim",
    "bad": "Ruim",
    "regular": "Regular",
    "good": "Boa",
    "excellent": "Excelente",
}
MEAL_QUALITY_PERCENT = {
    "very_bad": 20,
    "bad": 40,
    "regular": 60,
    "good": 80,
    "excellent": 100,
}


def format_hydration(amount_ml: int) -> str:
    amount_ml = max(0, int(amount_ml))
    if amount_ml < 1000:
        return f"{amount_ml} ml"
    liters = amount_ml / 1000
    value = f"{liters:.1f}".replace(".", ",")
    if value.endswith(",0"):
        value = value[:-2]
    return f"{value} L"


def calculate_provisional_nutrition_score(
    meals: Iterable[MealRecord],
    hydration_records: Iterable[HydrationRecord],
) -> int:
    """Adaptador compatível; a regra oficial vive em scoring_service."""
    return calculate_nutrition_score(meals, hydration_records)["score"]


def get_meals_for_date(target_date: date) -> list[MealRecord]:
    return list(
        db.session.scalars(
            db.select(MealRecord)
            .where(MealRecord.record_date == target_date)
            .order_by(MealRecord.meal_time.asc())
        )
    )


def get_hydration_for_date(target_date: date) -> list[HydrationRecord]:
    return list(
        db.session.scalars(
            db.select(HydrationRecord)
            .where(HydrationRecord.record_date == target_date)
            .order_by(HydrationRecord.consumed_at.asc())
        )
    )


def _meals_for_period(start_date: date, end_date: date) -> list[MealRecord]:
    if end_date < start_date:
        raise ValueError("A data final deve ser igual ou posterior à inicial.")
    return list(
        db.session.scalars(
            db.select(MealRecord)
            .where(MealRecord.record_date.between(start_date, end_date))
            .order_by(MealRecord.record_date.desc(), MealRecord.meal_time.asc())
        )
    )


def _hydration_for_period(
    start_date: date,
    end_date: date,
) -> list[HydrationRecord]:
    if end_date < start_date:
        raise ValueError("A data final deve ser igual ou posterior à inicial.")
    return list(
        db.session.scalars(
            db.select(HydrationRecord)
            .where(HydrationRecord.record_date.between(start_date, end_date))
            .order_by(
                HydrationRecord.record_date.desc(),
                HydrationRecord.consumed_at.asc(),
            )
        )
    )


def _nutrition_summary(
    meals: list[MealRecord],
    hydration_records: list[HydrationRecord],
) -> dict:
    hydration_total = sum(record.amount_ml for record in hydration_records)
    quality_average = None
    if meals:
        quality_average = round(
            sum(
                MEAL_QUALITY_PERCENT.get(meal.perceived_quality, 0)
                for meal in meals
            )
            / len(meals)
        )
    return {
        "meals": len(meals),
        "protein_meals": sum(meal.has_protein == "yes" for meal in meals),
        "produce_meals": sum(
            meal.has_fruits_or_vegetables == "yes" for meal in meals
        ),
        "hydration_ml": hydration_total,
        "hydration": format_hydration(hydration_total),
        "quality_average": quality_average,
        "score": calculate_provisional_nutrition_score(
            meals,
            hydration_records,
        ),
    }


def get_nutrition_summary_for_date(target_date: date) -> dict:
    return _nutrition_summary(
        get_meals_for_date(target_date),
        get_hydration_for_date(target_date),
    )


def _weekly_data_from_records(
    meals: list[MealRecord],
    hydration_records: list[HydrationRecord],
    reference_date: date,
) -> list[dict]:
    meals_by_date: dict[date, list[MealRecord]] = defaultdict(list)
    hydration_by_date: dict[date, list[HydrationRecord]] = defaultdict(list)
    for meal in meals:
        meals_by_date[meal.record_date].append(meal)
    for record in hydration_records:
        hydration_by_date[record.record_date].append(record)

    weekly = []
    start_date = reference_date - timedelta(days=6)
    for offset in range(7):
        target_date = start_date + timedelta(days=offset)
        day_meals = meals_by_date[target_date]
        day_hydration = hydration_by_date[target_date]
        raw_score = calculate_provisional_nutrition_score(
            day_meals,
            day_hydration,
        )
        hydration_total = sum(record.amount_ml for record in day_hydration)
        meal_label = "refeição" if len(day_meals) == 1 else "refeições"
        weekly.append(
            {
                "date": target_date.isoformat(),
                "date_label": target_date.strftime("%d/%m"),
                "label": weekday_label(target_date),
                "score": raw_score * 5,
                "raw_score": raw_score,
                "meals": len(day_meals),
                "hydration_ml": hydration_total,
                "hydration": format_hydration(hydration_total),
                "tooltip_lines": [
                    f"{len(day_meals)} {meal_label}",
                    f"Água: {format_hydration(hydration_total)}",
                ],
                "is_today": target_date == reference_date,
            }
        )
    return weekly


def get_weekly_nutrition_data(
    reference_date: date | None = None,
) -> list[dict]:
    reference_date = reference_date or get_local_today()
    start_date = reference_date - timedelta(days=6)
    return _weekly_data_from_records(
        _meals_for_period(start_date, reference_date),
        _hydration_for_period(start_date, reference_date),
        reference_date,
    )


def _percentage(part: int, total: int) -> int:
    return round(part / total * 100) if total else 0


def _nutrition_indicators_from_records(
    meals: list[MealRecord],
    hydration_records: list[HydrationRecord],
    start_date: date,
    end_date: date,
) -> list[dict]:
    if not meals and not hydration_records:
        return []
    period_days = (end_date - start_date).days + 1
    meal_count = len(meals)
    protein_percent = _percentage(
        sum(meal.has_protein == "yes" for meal in meals),
        meal_count,
    )
    produce_percent = _percentage(
        sum(meal.has_fruits_or_vegetables == "yes" for meal in meals),
        meal_count,
    )
    quality_percent = (
        round(
            sum(
                MEAL_QUALITY_PERCENT.get(meal.perceived_quality, 0)
                for meal in meals
            )
            / meal_count
        )
        if meal_count
        else 0
    )
    hydration_average = round(
        sum(record.amount_ml for record in hydration_records) / period_days
    )
    # Referência apenas visual para a barra; não representa prescrição de água.
    hydration_target = current_app.config["DEFAULT_HYDRATION_TARGET_ML"]
    hydration_percent = min(
        round(hydration_average / hydration_target * 100),
        100,
    )
    meal_days = len({meal.record_date for meal in meals})
    regularity_percent = round(meal_days / period_days * 100)
    return [
        {
            "name": "Proteína",
            "score": protein_percent,
            "value": f"{protein_percent}% das refeições",
            "bar_label": "Refeições com fonte de proteína",
            "theme": "blue",
        },
        {
            "name": "Frutas e verduras",
            "score": produce_percent,
            "value": f"{produce_percent}% das refeições",
            "bar_label": "Refeições com frutas ou verduras",
            "theme": "green",
        },
        {
            "name": "Água",
            "score": hydration_percent,
            "value": f"{format_hydration(hydration_average)} por dia",
            "bar_label": (
                "Média diária frente à meta configurada de "
                f"{format_hydration(hydration_target)}"
            ),
            "theme": "blue",
        },
        {
            "name": "Regularidade",
            "score": regularity_percent,
            "value": f"{regularity_percent}% dos dias",
            "bar_label": "Dias com ao menos uma refeição registrada",
            "theme": "purple",
        },
        {
            "name": "Qualidade percebida",
            "score": quality_percent,
            "value": f"{quality_percent}%",
            "bar_label": "Média das avaliações manuais de qualidade",
            "theme": "orange",
        },
    ]


def get_nutrition_indicators(
    start_date: date,
    end_date: date,
) -> list[dict]:
    return _nutrition_indicators_from_records(
        _meals_for_period(start_date, end_date),
        _hydration_for_period(start_date, end_date),
        start_date,
        end_date,
    )


def _nutrition_heatmap_level(score: int) -> int:
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
    meals: list[MealRecord],
    hydration_records: list[HydrationRecord],
    year: int,
    month: int,
    reference_date: date,
) -> dict:
    calendar_data = calendar_metadata(year, month)
    meals_by_day: dict[int, list[MealRecord]] = defaultdict(list)
    hydration_by_day: dict[int, list[HydrationRecord]] = defaultdict(list)
    for meal in meals:
        if meal.record_date.year == year and meal.record_date.month == month:
            meals_by_day[meal.record_date.day].append(meal)
    for record in hydration_records:
        if record.record_date.year == year and record.record_date.month == month:
            hydration_by_day[record.record_date.day].append(record)

    days = []
    for day in range(1, calendar_data["total_days"] + 1):
        day_meals = meals_by_day[day]
        day_hydration = hydration_by_day[day]
        score = calculate_provisional_nutrition_score(
            day_meals,
            day_hydration,
        )
        hydration_total = sum(record.amount_ml for record in day_hydration)
        target_date = date(year, month, day)
        meal_label = "refeição" if len(day_meals) == 1 else "refeições"
        days.append(
            {
                "day": day,
                "level": _nutrition_heatmap_level(score),
                "is_highlighted": target_date == reference_date,
                "title": (
                    f"{target_date.strftime('%d/%m/%Y')} • "
                    f"{score} de 20 pontos • "
                    f"{len(day_meals)} {meal_label} • "
                    f"Água: {format_hydration(hydration_total)}"
                ),
            }
        )
    return {**calendar_data, "days": days}


def get_monthly_nutrition_heatmap(
    year: int,
    month: int,
    reference_date: date | None = None,
) -> dict:
    reference_date = reference_date or get_local_today()
    last_day = calendar_metadata(year, month)["total_days"]
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)
    return _monthly_heatmap_from_records(
        _meals_for_period(start_date, end_date),
        _hydration_for_period(start_date, end_date),
        year,
        month,
        reference_date,
    )


def _meal_item(meal: MealRecord) -> dict:
    icon, theme = MEAL_TYPE_STYLES.get(
        meal.meal_type,
        MEAL_TYPE_STYLES["other"],
    )
    return {
        "name": MEAL_TYPE_LABELS.get(meal.meal_type, "Outra"),
        "meta": " • ".join(
            (
                meal.foods_text,
                f"Qualidade {MEAL_QUALITY_LABELS.get(meal.perceived_quality, 'Não informada').casefold()}",
                f"Proteína: {TRINARY_LABELS.get(meal.has_protein, 'Não informado')}",
                (
                    "Frutas/verduras: "
                    f"{TRINARY_LABELS.get(meal.has_fruits_or_vegetables, 'Não informado')}"
                ),
            )
        ),
        "value": meal.meal_time.strftime("%H:%M"),
        "icon": icon,
        "theme": theme,
    }


def _score_message(score: int) -> str:
    return get_score_message(score, 20)


def _meal_count_label(value: int) -> str:
    return f"{value} refeição" if value == 1 else f"{value} refeições"


def _quality_status(value: int | None) -> str:
    if value is None:
        return "Sem refeições hoje"
    if value < 40:
        return "Baixa"
    if value < 60:
        return "Regular"
    if value < 80:
        return "Boa"
    if value < 90:
        return "Muito boa"
    return "Excelente"


def _hydration_comparison(
    current: int,
    previous: int,
    has_previous: bool,
) -> tuple[str, str]:
    if not has_previous:
        return "Sem registros ontem", "neutral"
    difference = current - previous
    if difference == 0:
        return "Mesmo total de ontem", "neutral"
    sign = "+" if difference > 0 else "-"
    return (
        f"{sign}{format_hydration(abs(difference))} vs ontem",
        "positive" if difference > 0 else "negative",
    )


def get_nutrition_page_data(reference_date: date | None = None) -> dict:
    reference_date = reference_date or get_local_today()
    yesterday = reference_date - timedelta(days=1)
    last_30_start = reference_date - timedelta(days=29)
    weekly_start = reference_date - timedelta(days=6)
    month_start = reference_date.replace(day=1)
    query_start = min(yesterday, last_30_start, month_start)

    meals = _meals_for_period(query_start, reference_date)
    hydration_records = _hydration_for_period(query_start, reference_date)
    meals_by_date: dict[date, list[MealRecord]] = defaultdict(list)
    hydration_by_date: dict[date, list[HydrationRecord]] = defaultdict(list)
    for meal in meals:
        meals_by_date[meal.record_date].append(meal)
    for record in hydration_records:
        hydration_by_date[record.record_date].append(record)

    today_meals = sorted(
        meals_by_date[reference_date],
        key=lambda meal: meal.meal_time,
    )
    today_hydration = hydration_by_date[reference_date]
    yesterday_meals = meals_by_date[yesterday]
    yesterday_hydration = hydration_by_date[yesterday]
    today_summary = _nutrition_summary(today_meals, today_hydration)
    yesterday_summary = _nutrition_summary(
        yesterday_meals,
        yesterday_hydration,
    )
    has_yesterday = bool(yesterday_meals or yesterday_hydration)
    score_comparison = build_score_comparison(
        today_summary["score"],
        yesterday_summary["score"],
        has_yesterday,
    )
    meals_helper, meals_tone = build_metric_comparison(
        today_summary["meals"],
        yesterday_summary["meals"],
        unit="meals",
        has_previous=has_yesterday,
    )
    hydration_helper, hydration_tone = _hydration_comparison(
        today_summary["hydration_ml"],
        yesterday_summary["hydration_ml"],
        has_yesterday,
    )

    weekly_meals = [
        meal for meal in meals if meal.record_date >= weekly_start
    ]
    weekly_hydration = [
        record
        for record in hydration_records
        if record.record_date >= weekly_start
    ]
    weekly = _weekly_data_from_records(
        weekly_meals,
        weekly_hydration,
        reference_date,
    )
    indicator_meals = [
        meal for meal in meals if meal.record_date >= last_30_start
    ]
    indicator_hydration = [
        record
        for record in hydration_records
        if record.record_date >= last_30_start
    ]
    month_meals = [
        meal for meal in meals if meal.record_date >= month_start
    ]
    month_hydration = [
        record
        for record in hydration_records
        if record.record_date >= month_start
    ]
    protein_percent = _percentage(
        today_summary["protein_meals"],
        today_summary["meals"],
    )

    if not today_meals:
        action_message = "Registre sua primeira refeição do dia."
    elif today_summary["hydration_ml"] == 0:
        action_message = "Lembre-se de registrar sua hidratação."
    else:
        action_message = "Continue registrando suas próximas refeições."

    return {
        "reference_label": format_local_date_label(reference_date),
        "score_title": "Pontuação de alimentação",
        "score": {
            "value": today_summary["score"] * 5,
            "raw_value": today_summary["score"],
            "previous_raw_value": yesterday_summary["score"],
            "comparison": score_comparison["text"],
            "comparison_tone": score_comparison["tone"],
            "comparison_icon": score_comparison["icon"],
            "helper": (
                f"{today_summary['score']} de 20 pontos da categoria. "
                f"{_score_message(today_summary['score'])}"
            ),
        },
        "metrics": [
            {
                "title": "Refeições",
                "value": _meal_count_label(today_summary["meals"]),
                "helper": meals_helper,
                "helper_tone": meals_tone,
                "secondary_helper": "Registradas hoje",
                "icon": "utensils",
                "theme": "green",
            },
            {
                "title": "Proteína",
                "value": _meal_count_label(today_summary["protein_meals"]),
                "helper": "Com fonte de proteína",
                "helper_tone": "neutral",
                "secondary_helper": (
                    f"{protein_percent}% das refeições"
                    if today_summary["meals"]
                    else "Sem refeições hoje"
                ),
                "icon": "activity",
                "theme": "purple",
            },
            {
                "title": "Hidratação",
                "value": today_summary["hydration"],
                "helper": hydration_helper,
                "helper_tone": hydration_tone,
                "secondary_helper": "",
                "icon": "droplet",
                "theme": "blue",
            },
            {
                "title": "Qualidade",
                "value": (
                    f"{today_summary['quality_average']}%"
                    if today_summary["quality_average"] is not None
                    else "—"
                ),
                "helper": _quality_status(today_summary["quality_average"]),
                "helper_tone": "neutral",
                "secondary_helper": "",
                "icon": "badge-check",
                "theme": "orange",
            },
        ],
        "list": {
            "title": "O que comi hoje",
            "link_label": "Ver todas as refeições",
            "link_href": "/historico?categoria=meal",
            "items": [_meal_item(meal) for meal in today_meals[:4]],
            "empty": {
                "title": "Nenhuma refeição registrada hoje",
                "description": (
                    "Registre sua primeira refeição para acompanhar sua alimentação."
                ),
                "link_label": "Registrar alimentação",
                "link_href": "/registrar?categoria=alimentacao",
            },
        },
        "weekly": {
            "title": "Desempenho semanal",
            "labels": [item["label"] for item in weekly],
            "scores": [item["score"] for item in weekly],
            "details": weekly,
            "filter": "Últimos 7 dias",
        },
        "progress": {
            "title": "Qualidade da alimentação",
            "link_label": "Ver todos os indicadores",
            "items": _nutrition_indicators_from_records(
                indicator_meals,
                indicator_hydration,
                last_30_start,
                reference_date,
            ),
            "empty_text": (
                "Nenhum registro de alimentação nos últimos 30 dias."
            ),
        },
        "action": {
            "title": "Próximo registro",
            "subtitle": "Continue acompanhando sua alimentação.",
            "plan": action_message,
            "subject": "Acompanhamento manual",
            "duration": "Sem planejamento automático",
            "schedule": "",
            "status": "Registro manual",
            "icon": "utensils",
            "primary_label": "Registrar alimentação",
            "primary_href": "/registrar?categoria=alimentacao",
            "secondary_label": "Ver registros",
            "is_demonstrative": False,
        },
        "heatmap": {
            **_monthly_heatmap_from_records(
                month_meals,
                month_hydration,
                reference_date.year,
                reference_date.month,
                reference_date,
            ),
            "title": "Mapa de alimentação",
            "activity_label": "alimentação",
        },
    }
