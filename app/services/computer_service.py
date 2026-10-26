from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import json
import re
from typing import Any, Iterable

from flask import current_app, has_app_context
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models import ApplicationRule, ComputerActivityBlock, ProjectRule, SessionRecord
from app.models.computer import CATEGORIES, CLASSIFICATIONS
from app.services.analytics_utils import (
    calendar_metadata,
    format_duration,
    get_local_today,
    weekday_label,
)
from app.services.scoring_service import calculate_computer_score
from desktop.monitoring.constants import MIN_CLASSIFIED_TIME_SECONDS
from desktop.monitoring.foreground import normalize_executable_name
from desktop.monitoring.classifier import ApplicationClassifier


CLASSIFICATION_LABELS = {
    "productive": "Produtivo",
    "distracting": "Distração",
    "neutral": "Neutro",
    "ignored": "Ignorado",
}
CATEGORY_LABELS = {
    "study": "Estudo",
    "programming": "Programação",
    "work": "Trabalho",
    "communication": "Comunicação",
    "entertainment": "Entretenimento",
    "social": "Redes sociais",
    "gaming": "Jogos",
    "system": "Sistema",
    "other": "Outro",
}
CATEGORY_THEMES = {
    "study": "green",
    "programming": "blue",
    "work": "purple",
    "communication": "teal",
    "entertainment": "orange",
    "social": "purple",
    "gaming": "rose",
    "system": "neutral",
    "other": "neutral",
}


class ComputerValidationError(ValueError):
    pass


def _seconds_label(seconds: int) -> str:
    return format_duration(max(0, int(seconds)) // 60)


def summarize_blocks(
    blocks: Iterable[ComputerActivityBlock],
    *,
    focused_sessions_count: int = 0,
) -> dict[str, Any]:
    totals = defaultdict(int)
    known_seconds = 0
    coverage_seconds = 0
    for block in blocks:
        duration = max(0, int(block.duration_seconds or 0))
        if block.was_idle:
            totals["idle"] += duration
            continue
        totals[block.classification] += duration
        if block.classification == "ignored":
            continue
        coverage_seconds += duration
        if block.classification_source != "fallback":
            known_seconds += duration
    percentage = (
        round(known_seconds / coverage_seconds * 100)
        if coverage_seconds
        else 0
    )
    summary = {
        "productive_seconds": totals["productive"],
        "distracted_seconds": totals["distracting"],
        "neutral_seconds": totals["neutral"],
        "idle_seconds": totals["idle"],
        "classified_apps_percentage": percentage,
        "focused_sessions_count": focused_sessions_count,
        "distraction_limit_seconds": int(
            current_app.config.get("DEFAULT_DISTRACTION_LIMIT_SECONDS", 7200)
        )
        if has_app_context()
        else 7200,
    }
    classified_time = summary["productive_seconds"] + summary["distracted_seconds"]
    summary["evaluated"] = classified_time >= MIN_CLASSIFIED_TIME_SECONDS
    summary["score"] = calculate_computer_score(
        summary if summary["evaluated"] else None
    )
    return summary


def _focused_sessions_for_date(target_date: date) -> int:
    return int(
        db.session.scalar(
            db.select(db.func.count(SessionRecord.id)).where(
                SessionRecord.record_date == target_date,
                SessionRecord.status == "completed",
                SessionRecord.related_category == "computer",
            )
        )
        or 0
    )


def get_computer_summary_for_date(target_date: date) -> dict[str, Any]:
    blocks = list(
        db.session.scalars(
            db.select(ComputerActivityBlock).where(
                ComputerActivityBlock.record_date == target_date
            )
        )
    )
    return summarize_blocks(
        blocks,
        focused_sessions_count=_focused_sessions_for_date(target_date),
    )


def get_today_top_apps(limit: int = 5, target_date: date | None = None) -> list[dict]:
    target = target_date or get_local_today()
    blocks = list(
        db.session.scalars(
            db.select(ComputerActivityBlock)
        .where(
            ComputerActivityBlock.record_date == target,
            ComputerActivityBlock.was_idle.is_(False),
            ComputerActivityBlock.classification != "ignored",
        )
            .order_by(
                ComputerActivityBlock.ended_at.desc(),
                ComputerActivityBlock.id.desc(),
            )
        )
    )
    aggregated: dict[str, dict[str, Any]] = {}
    for block in blocks:
        item = aggregated.get(block.executable_name)
        if item is None:
            item = {
                "executable_name": block.executable_name,
                "friendly_name": block.friendly_name or block.executable_name,
                "classification": block.classification,
                "classification_label": CLASSIFICATION_LABELS[block.classification],
                "category": block.category,
                "category_label": CATEGORY_LABELS[block.category],
                "classification_source": block.classification_source,
                "duration_seconds": 0,
            }
            aggregated[block.executable_name] = item
        item["duration_seconds"] += max(0, int(block.duration_seconds or 0))
    return sorted(
        aggregated.values(),
        key=lambda item: item["duration_seconds"],
        reverse=True,
    )[: max(1, min(int(limit), 50))]


def get_weekly_computer_data(reference_date: date) -> dict[str, list]:
    start = reference_date - timedelta(days=6)
    rows = db.session.execute(
        db.select(
            ComputerActivityBlock.record_date,
            ComputerActivityBlock.classification,
            db.func.sum(ComputerActivityBlock.duration_seconds).label("seconds"),
        )
        .where(
            ComputerActivityBlock.record_date.between(start, reference_date),
            ComputerActivityBlock.was_idle.is_(False),
            ComputerActivityBlock.classification.in_(("productive", "distracting")),
        )
        .group_by(
            ComputerActivityBlock.record_date,
            ComputerActivityBlock.classification,
        )
    )
    values = defaultdict(lambda: defaultdict(int))
    for row in rows:
        values[row.record_date][row.classification] = int(row.seconds or 0)
    days = [start + timedelta(days=offset) for offset in range(7)]
    return {
        "title": "Produtivo x distração",
        "filter": "Últimos 7 dias",
        "labels": [weekday_label(day) for day in days],
        "productive": [
            round(values[day]["productive"] / 3600, 2) for day in days
        ],
        "distracted": [
            round(values[day]["distracting"] / 3600, 2) for day in days
        ],
    }


def get_category_distribution(start_date: date, end_date: date) -> list[dict]:
    rows = db.session.execute(
        db.select(
            ComputerActivityBlock.category,
            db.func.sum(ComputerActivityBlock.duration_seconds).label("seconds"),
        )
        .where(
            ComputerActivityBlock.record_date.between(start_date, end_date),
            ComputerActivityBlock.was_idle.is_(False),
            ComputerActivityBlock.classification != "ignored",
        )
        .group_by(ComputerActivityBlock.category)
        .order_by(db.desc("seconds"))
    )
    items = [(row.category, int(row.seconds or 0)) for row in rows]
    total = sum(seconds for _, seconds in items)
    return [
        {
            "name": CATEGORY_LABELS[category],
            "category": category,
            "score": round(seconds / total * 100) if total else 0,
            "value": _seconds_label(seconds),
            "theme": CATEGORY_THEMES[category],
        }
        for category, seconds in items
    ]


def get_monthly_computer_heatmap(
    year: int,
    month: int,
    *,
    reference_date: date | None = None,
) -> dict:
    metadata = calendar_metadata(year, month)
    today = reference_date or get_local_today()
    first_day = date(year, month, 1)
    last_day = date(year, month, metadata["total_days"])
    blocks = list(
        db.session.scalars(
            db.select(ComputerActivityBlock).where(
                ComputerActivityBlock.record_date.between(first_day, last_day)
            )
        )
    )
    sessions = list(
        db.session.scalars(
            db.select(SessionRecord).where(
                SessionRecord.record_date.between(first_day, last_day),
                SessionRecord.status == "completed",
                SessionRecord.related_category == "computer",
            )
        )
    )
    blocks_by_date = defaultdict(list)
    sessions_by_date = defaultdict(int)
    for block in blocks:
        blocks_by_date[block.record_date].append(block)
    for session in sessions:
        sessions_by_date[session.record_date] += 1
    days = []
    for day in range(1, metadata["total_days"] + 1):
        target = date(year, month, day)
        summary = summarize_blocks(
            blocks_by_date[target],
            focused_sessions_count=sessions_by_date[target],
        )
        score = summary["score"]
        value = int(score["score"]) if score["evaluated"] else 0
        level = 0 if not score["evaluated"] else min(5, (value - 1) // 4 + 1)
        days.append(
            {
                "day": day,
                "date": target.isoformat(),
                "level": level,
                "is_highlighted": target == today,
                "title": (
                    f"{target.strftime('%d/%m/%Y')} • não avaliado"
                    if not score["evaluated"]
                    else (
                        f"{target.strftime('%d/%m/%Y')} • {value}/20 • "
                        f"produtivo {_seconds_label(summary['productive_seconds'])} • "
                        f"distração {_seconds_label(summary['distracted_seconds'])} • "
                        f"neutro {_seconds_label(summary['neutral_seconds'])} • "
                        f"cobertura {summary['classified_apps_percentage']}%"
                    )
                ),
            }
        )
    return {
        **metadata,
        "title": "Mapa de qualidade do PC",
        "activity_label": "qualidade do uso do computador",
        "days": days,
    }


def get_current_monitor_status() -> dict[str, Any]:
    agent = current_app.config.get("COMPUTER_MONITOR_AGENT")
    if agent is None:
        return {
            "status": "stopped",
            "paused": False,
            "current_process": None,
            "idle_seconds": 0,
        }
    return agent.status()


def get_computer_page_data(reference_date: date | None = None) -> dict[str, Any]:
    target = reference_date or get_local_today()
    summary = get_computer_summary_for_date(target)
    yesterday = get_computer_summary_for_date(target - timedelta(days=1))
    top_apps = [
        item
        for item in get_today_top_apps(50, target)
        if item["duration_seconds"] >= 3
    ][:5]
    score = summary["score"]
    focus_denominator = summary["productive_seconds"] + summary["distracted_seconds"]
    focus = (
        round(summary["productive_seconds"] / focus_denominator * 100)
        if focus_denominator
        else 0
    )
    status = get_current_monitor_status()
    active_total = (
        summary["productive_seconds"]
        + summary["distracted_seconds"]
        + summary["neutral_seconds"]
    )
    status_label = {
        "running": "Monitorando",
        "paused": "Pausado",
        "stopped": "Desligado",
        "error": "Erro",
    }.get(status["status"], "Desligado")
    yesterday_evaluated = yesterday["score"]["evaluated"]
    difference = int(score["score"]) - int(yesterday["score"]["score"])
    comparison = (
        "Sem comparação com ontem"
        if not yesterday_evaluated
        else f"{difference:+d} vs ontem"
        if difference
        else "Mesmo resultado de ontem"
    )
    if not score["evaluated"]:
        difference = 0
        comparison = "Sem avaliação nesta data"
    return {
        "score": {
            "evaluated": bool(score["evaluated"]),
            "value": int(score["score"]) if score["evaluated"] else 0,
            "ring_value": int(score["score"]) * 5 if score["evaluated"] else 0,
            "comparison": comparison,
            "comparison_tone": (
                "positive" if difference > 0 else "negative" if difference < 0 else "neutral"
            ),
            "comparison_icon": (
                "trending-up" if difference > 0 else "trending-down" if difference < 0 else "minus"
            ),
            "helper": (
                score["message"]
                if score["evaluated"]
                else "Nenhum uso do computador registrado nesta data."
            ),
        },
        "score_title": "Pontuação de uso do computador",
        "metrics": [
            _metric(
                "Tempo total no computador",
                active_total,
                "monitor",
                "blue",
                helper="Produtivo + distraído + neutro; não inclui ociosidade",
            ),
            _metric("Tempo produtivo", summary["productive_seconds"], "laptop", "green"),
            _metric("Tempo distraído", summary["distracted_seconds"], "gamepad-2", "orange"),
            _metric("Tempo neutro", summary["neutral_seconds"], "circle-minus", "purple"),
            _metric("Tempo ocioso", summary["idle_seconds"], "clock-3", "blue"),
        ],
        "activities": [
            {
                "name": app["friendly_name"],
                "meta": f"{app['category_label']} • {app['executable_name']}",
                "value": _seconds_label(app["duration_seconds"]),
                "status": app["classification_label"],
                "status_tone": (
                    "positive"
                    if app["classification"] == "productive"
                    else "warning"
                    if app["classification"] == "distracting"
                    else "neutral"
                ),
                "icon": "code-2" if app["category"] == "programming" else "app-window",
                "theme": CATEGORY_THEMES[app["category"]],
            }
            for app in top_apps
        ],
        "weekly_usage": get_weekly_computer_data(target),
        "categories": {
            "title": "Tempo por categoria",
            "link_label": "Gerenciar regras",
            "items": get_category_distribution(target, target),
        },
        "monitored_session": {
            "title": f"Monitoramento: {status_label}",
            "subtitle": (
                (
                    f"Você está visualizando {target.strftime('%d/%m/%Y')}. "
                    f"Monitoramento atual: {status_label.casefold()}."
                )
                if target != get_local_today()
                else "Registra somente o aplicativo em primeiro plano e a duração."
            ),
            "icon": "monitor",
            "primary_label": (
                "Pausar" if status["status"] == "running" else "Retomar"
                if status["status"] == "paused" else "Iniciar monitoramento"
            ),
            "secondary_label": "Regras de aplicativos",
            "stats": [
                {"label": "Foco no PC", "value": f"{focus}%", "icon": "target"},
                {
                    "label": "Cobertura",
                    "value": f"{summary['classified_apps_percentage']}%",
                    "icon": "badge-check",
                },
                {
                    "label": "Apps principais",
                    "value": str(len(top_apps)),
                    "icon": "layout-grid",
                },
                {
                    "label": "Projeto atual",
                    "value": status.get("current_project") or "Nenhum",
                    "icon": "folder-code",
                },
            ],
            "status": status["status"],
        },
        "heatmap": get_monthly_computer_heatmap(
            target.year,
            target.month,
            reference_date=target,
        ),
        "monitor_status": status,
        "applications": get_applications(target),
        "projects": list_project_rules(include_usage=True),
        "context_totals": {
            "chatgpt_desktop_seconds": int(
                db.session.scalar(
                    db.select(
                        db.func.sum(ComputerActivityBlock.duration_seconds)
                    ).where(
                        ComputerActivityBlock.record_date == target,
                        ComputerActivityBlock.executable_name == "chatgpt.exe",
                    )
                )
                or 0
            ),
            "chatgpt_browser_seconds": int(
                db.session.scalar(
                    db.select(
                        db.func.sum(ComputerActivityBlock.duration_seconds)
                    ).where(
                        ComputerActivityBlock.record_date == target,
                        ComputerActivityBlock.site_key == "chatgpt",
                    )
                )
                or 0
            ),
        },
    }


def _metric(
    title: str,
    seconds: int,
    icon: str,
    theme: str,
    *,
    helper: str = "Data selecionada",
) -> dict:
    return {
        "title": title,
        "value": _seconds_label(seconds),
        "helper": helper,
        "helper_tone": "neutral",
        "secondary_helper": "",
        "icon": icon,
        "theme": theme,
    }


def serialize_rule(rule: ApplicationRule) -> dict:
    return {
        "id": rule.id,
        "executable_name": rule.executable_name,
        "friendly_name": rule.friendly_name,
        "classification": rule.classification,
        "category": rule.category,
        "enabled": bool(rule.enabled),
        "priority": int(rule.priority),
    }


def list_application_rules() -> list[dict]:
    rules = list(
        db.session.scalars(
            db.select(ApplicationRule).order_by(
                ApplicationRule.priority.desc(),
                ApplicationRule.executable_name,
            )
        )
    )
    return [serialize_rule(rule) for rule in rules]


def _validate_rule_payload(payload: dict, *, partial: bool = False) -> dict:
    allowed = {
        "executable_name",
        "friendly_name",
        "classification",
        "category",
        "enabled",
        "priority",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ComputerValidationError("Há campos de regra não permitidos.")
    result = dict(payload)
    if "executable_name" in result:
        value = normalize_executable_name(result["executable_name"])
        raw = str(result["executable_name"])
        if (
            value is None
            or value != raw.strip().lower()
            or "/" in raw
            or "\\" in raw
            or "*" in raw
        ):
            raise ComputerValidationError("Informe somente o nome do executável.")
        result["executable_name"] = value
    elif not partial:
        raise ComputerValidationError("O nome do executável é obrigatório.")
    if "classification" in result and result["classification"] not in CLASSIFICATIONS:
        raise ComputerValidationError("Classificação inválida.")
    if "category" in result and result["category"] not in CATEGORIES:
        raise ComputerValidationError("Categoria inválida.")
    if not partial and (
        "classification" not in result or "category" not in result
    ):
        raise ComputerValidationError("Classificação e categoria são obrigatórias.")
    if "friendly_name" in result:
        name = str(result["friendly_name"] or "").strip()
        result["friendly_name"] = name[:255] or None
    if "enabled" in result:
        if not isinstance(result["enabled"], bool):
            raise ComputerValidationError("O estado da regra deve ser booleano.")
    if "priority" in result:
        try:
            priority = int(result["priority"])
        except (TypeError, ValueError):
            raise ComputerValidationError("Prioridade inválida.") from None
        if not 0 <= priority <= 1000:
            raise ComputerValidationError("Prioridade fora do limite.")
        result["priority"] = priority
    return result


def create_application_rule(payload: dict) -> dict:
    values = _validate_rule_payload(payload)
    rule = ApplicationRule(**values)
    db.session.add(rule)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ComputerValidationError("Já existe uma regra para esse executável.") from None
    return serialize_rule(rule)


def update_application_rule(rule_id: int, payload: dict) -> dict:
    rule = db.session.get(ApplicationRule, rule_id)
    if rule is None:
        raise LookupError("Regra não encontrada.")
    for key, value in _validate_rule_payload(payload, partial=True).items():
        setattr(rule, key, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ComputerValidationError("Já existe uma regra para esse executável.") from None
    return serialize_rule(rule)


def delete_application_rule(rule_id: int) -> None:
    rule = db.session.get(ApplicationRule, rule_id)
    if rule is None:
        raise LookupError("Regra não encontrada.")
    db.session.delete(rule)
    db.session.commit()


def get_applications(target_date: date | None = None) -> list[dict]:
    target = target_date or get_local_today()
    apps = get_today_top_apps(50, target)
    rules = {
        item["executable_name"]: item for item in list_application_rules()
    }
    for app in apps:
        app["manual_rule"] = rules.get(app["executable_name"])
    return apps


def serialize_project_rule(rule: ProjectRule, *, include_usage: bool = False) -> dict:
    try:
        terms = json.loads(rule.match_terms)
    except (TypeError, ValueError, json.JSONDecodeError):
        terms = []
    payload = {
        "id": rule.id,
        "project_key": rule.project_key,
        "display_name": rule.display_name,
        "match_terms": terms,
        "classification": rule.classification,
        "category": rule.category,
        "enabled": bool(rule.enabled),
        "priority": int(rule.priority),
    }
    if include_usage:
        today = get_local_today()
        payload["today_seconds"] = int(
            db.session.scalar(
                db.select(db.func.sum(ComputerActivityBlock.duration_seconds)).where(
                    ComputerActivityBlock.project_key == rule.project_key,
                    ComputerActivityBlock.record_date == today,
                )
            )
            or 0
        )
        payload["total_seconds"] = int(
            db.session.scalar(
                db.select(db.func.sum(ComputerActivityBlock.duration_seconds)).where(
                    ComputerActivityBlock.project_key == rule.project_key
                )
            )
            or 0
        )
    return payload


def list_project_rules(*, include_usage: bool = True) -> list[dict]:
    rules = db.session.scalars(
        db.select(ProjectRule).order_by(
            ProjectRule.priority.desc(),
            ProjectRule.display_name,
        )
    )
    return [
        serialize_project_rule(rule, include_usage=include_usage) for rule in rules
    ]


def _normalize_project_key(value: Any) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")
    if len(key) < 3 or len(key) > 100:
        raise ComputerValidationError(
            "A chave do projeto deve ter de 3 a 100 caracteres."
        )
    return key


def _validate_project_payload(payload: dict, *, partial: bool = False) -> dict:
    allowed = {
        "project_key",
        "display_name",
        "match_terms",
        "classification",
        "category",
        "enabled",
        "priority",
    }
    if set(payload) - allowed:
        raise ComputerValidationError("Há campos de projeto não permitidos.")
    result = dict(payload)
    if "project_key" in result:
        result["project_key"] = _normalize_project_key(result["project_key"])
    elif not partial:
        if "display_name" not in result:
            raise ComputerValidationError("O nome do projeto é obrigatório.")
        result["project_key"] = _normalize_project_key(result["display_name"])
    if "display_name" in result:
        display_name = str(result["display_name"] or "").strip()
        if not 2 <= len(display_name) <= 150:
            raise ComputerValidationError("Informe um nome de projeto válido.")
        result["display_name"] = display_name
    elif not partial:
        raise ComputerValidationError("O nome do projeto é obrigatório.")
    if "match_terms" in result:
        if not isinstance(result["match_terms"], list):
            raise ComputerValidationError("Os termos devem ser uma lista.")
        terms = []
        for raw in result["match_terms"]:
            term = ApplicationClassifier._normalize_text(str(raw))
            if len(term) < 3 or len(term) > 100:
                raise ComputerValidationError(
                    "Cada termo deve ter de 3 a 100 caracteres."
                )
            if any(symbol in term for symbol in ("*", "[", "]", "(", ")", "{", "}")):
                raise ComputerValidationError("Expressões regulares não são aceitas.")
            if term not in terms:
                terms.append(term)
        if not terms:
            raise ComputerValidationError("Informe ao menos um termo.")
        result["match_terms"] = json.dumps(terms, ensure_ascii=False)
    elif not partial:
        raise ComputerValidationError("Informe os termos de reconhecimento.")
    if "classification" in result and result["classification"] not in CLASSIFICATIONS:
        raise ComputerValidationError("Classificação inválida.")
    if "category" in result and result["category"] not in CATEGORIES:
        raise ComputerValidationError("Categoria inválida.")
    if not partial:
        result.setdefault("classification", "productive")
        result.setdefault("category", "programming")
    if "enabled" in result and not isinstance(result["enabled"], bool):
        raise ComputerValidationError("O estado deve ser booleano.")
    if "priority" in result:
        try:
            priority = int(result["priority"])
        except (TypeError, ValueError):
            raise ComputerValidationError("Prioridade inválida.") from None
        if not 0 <= priority <= 1000:
            raise ComputerValidationError("Prioridade fora do limite.")
        result["priority"] = priority
    return result


def create_project_rule(payload: dict) -> dict:
    rule = ProjectRule(**_validate_project_payload(payload))
    db.session.add(rule)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ComputerValidationError("Já existe um projeto com essa chave.") from None
    return serialize_project_rule(rule, include_usage=True)


def update_project_rule(rule_id: int, payload: dict) -> dict:
    rule = db.session.get(ProjectRule, rule_id)
    if rule is None:
        raise LookupError("Projeto não encontrado.")
    for key, value in _validate_project_payload(payload, partial=True).items():
        setattr(rule, key, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ComputerValidationError("Já existe um projeto com essa chave.") from None
    return serialize_project_rule(rule, include_usage=True)


def delete_project_rule(rule_id: int) -> None:
    rule = db.session.get(ProjectRule, rule_id)
    if rule is None:
        raise LookupError("Projeto não encontrado.")
    db.session.delete(rule)
    db.session.commit()


def delete_computer_data_before(target_date: date) -> int:
    try:
        result = db.session.execute(
            db.delete(ComputerActivityBlock).where(
                ComputerActivityBlock.record_date < target_date
            )
        )
        db.session.commit()
        return int(result.rowcount or 0)
    except SQLAlchemyError:
        db.session.rollback()
        raise


def delete_all_computer_data() -> int:
    try:
        result = db.session.execute(db.delete(ComputerActivityBlock))
        db.session.commit()
        return int(result.rowcount or 0)
    except SQLAlchemyError:
        db.session.rollback()
        raise
