from __future__ import annotations

import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import current_app


MONTH_NAMES = (
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)
WEEKDAY_NAMES = (
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
)
WEEKDAY_LABELS = ("S", "T", "Q", "Q", "S", "S", "D")


def get_app_timezone() -> ZoneInfo:
    timezone_name = current_app.config.get("APP_TIMEZONE", "America/Sao_Paulo")
    return ZoneInfo(timezone_name)


def get_local_today() -> date:
    return datetime.now(get_app_timezone()).date()


def format_duration(minutes: int) -> str:
    minutes = max(0, int(minutes))
    hours, remaining = divmod(minutes, 60)
    if not hours:
        return f"{remaining} min"
    if not remaining:
        return f"{hours}h"
    return f"{hours}h {remaining}min"


def format_local_date_label(target_date: date) -> str:
    return (
        f"{WEEKDAY_NAMES[target_date.weekday()]}, "
        f"{target_date.day} de {MONTH_NAMES[target_date.month].casefold()}"
    )


def build_date_navigation(target_date: date, route_path: str) -> dict:
    today = get_local_today()
    previous = date.fromordinal(target_date.toordinal() - 1)
    next_date = date.fromordinal(target_date.toordinal() + 1)
    return {
        "selected_date": target_date.isoformat(),
        "selected_label": format_local_date_label(target_date),
        "compact_label": (
            f"{target_date.day} de {MONTH_NAMES[target_date.month].casefold()} "
            f"de {target_date.year}"
        ),
        "is_today": target_date == today,
        "previous_url": f"{route_path}?date={previous.isoformat()}",
        "next_url": (
            f"{route_path}?date={next_date.isoformat()}"
            if next_date <= today
            else None
        ),
        "today_url": f"{route_path}?date={today.isoformat()}",
        "today": today.isoformat(),
    }


def weekday_label(target_date: date) -> str:
    return WEEKDAY_LABELS[target_date.weekday()]


def calendar_metadata(year: int, month: int) -> dict:
    return {
        "month": f"{MONTH_NAMES[month]} de {year}",
        "weekdays": list(WEEKDAY_LABELS),
        "leading_days": date(year, month, 1).weekday(),
        "total_days": calendar.monthrange(year, month)[1],
    }


def build_score_comparison(
    current: int,
    previous: int,
    has_previous: bool,
) -> dict:
    if not has_previous:
        return {
            "text": "Primeiro resultado comparável",
            "tone": "neutral",
            "icon": "minus",
        }
    difference = current - previous
    if difference > 0:
        return {
            "text": f"+{difference} pts vs ontem",
            "tone": "positive",
            "icon": "trending-up",
        }
    if difference < 0:
        return {
            "text": f"{difference} pts vs ontem",
            "tone": "negative",
            "icon": "trending-down",
        }
    return {
        "text": "Mesmo resultado de ontem",
        "tone": "neutral",
        "icon": "minus",
    }


def build_metric_comparison(
    current: int,
    previous: int,
    *,
    unit: str,
    has_previous: bool,
) -> tuple[str, str]:
    if not has_previous:
        return "Sem registros ontem", "neutral"
    difference = current - previous
    if difference == 0:
        return (
            "Mesmo tempo de ontem" if unit == "min" else "Mesmo total de ontem",
            "neutral",
        )
    sign = "+" if difference > 0 else "-"
    absolute = abs(difference)
    value = format_duration(absolute) if unit == "min" else str(absolute)
    return f"{sign}{value} vs ontem", "positive" if difference > 0 else "negative"
