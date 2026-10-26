from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_SCHEMA_VERSION = "1.0.0"
APP_TIMEZONE_NAME = "America/Sao_Paulo"
APP_TIMEZONE = ZoneInfo(APP_TIMEZONE_NAME)

FOCUS_PERCENTAGES = {
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
SLEEP_QUALITY_LABELS = {
    "terrible": "péssima",
    "bad": "ruim",
    "regular": "regular",
    "good": "boa",
    "excellent": "excelente",
}
RESTORED_LABELS = {
    "no": "não",
    "partially": "parcialmente",
    "yes": "sim",
}

REQUIRED_COLUMNS = {
    "alembic_version": {"version_num"},
    "study_records": {
        "id",
        "record_date",
        "subject",
        "topic",
        "duration_minutes",
        "questions_count",
        "correct_answers",
        "focus_quality",
        "learned_text",
        "difficulty_text",
        "record_origin",
        "created_at",
    },
    "sleep_records": {
        "id",
        "record_date",
        "sleep_start",
        "sleep_end",
        "duration_minutes",
        "perceived_quality",
        "awakenings_count",
        "woke_restored",
        "notes",
        "record_origin",
        "sleep_started_at",
        "sleep_ended_at",
        "is_primary",
    },
    "session_records": {
        "id",
        "record_date",
        "session_type",
        "title",
        "related_category",
        "target_duration_minutes",
        "actual_duration_seconds",
        "computer_monitoring_enabled",
        "objective_text",
        "result_text",
        "learned_text",
        "difficulty_text",
        "self_rating",
        "focus_percentage",
        "productive_seconds",
        "distracted_seconds",
        "status",
        "started_at",
        "finished_at",
    },
    "computer_activity_blocks": {
        "id",
        "record_date",
        "classification",
        "category",
        "classification_source",
        "started_at",
        "ended_at",
        "duration_seconds",
        "was_idle",
        "session_id",
    },
    "user_profile": {
        "id",
        "academic_goal",
        "weekly_study_minutes",
        "sleep_target_minutes",
    },
}


class ExportError(RuntimeError):
    """Erro seguro e esperado durante a exportação."""


def default_database_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    return base / "CondutionTime" / "data" / "condution_time.db"


def default_output_path() -> Path:
    return PROJECT_ROOT / "exports" / "ufpr" / "condution_time_ufpr.json"


def default_validation_path() -> Path:
    return PROJECT_ROOT / "exports" / "ufpr" / "validation_report.json"


def _connect_read_only(database: Path) -> sqlite3.Connection:
    try:
        resolved = database.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise ExportError(f"Banco de dados não encontrado: {database}") from exc
    if not resolved.is_file():
        raise ExportError(f"A fonte não é um arquivo SQLite: {resolved}")
    connection = sqlite3.connect(
        f"file:{resolved.as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("BEGIN")
    return connection


def _validate_schema(connection: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    missing_tables = sorted(set(REQUIRED_COLUMNS) - tables)
    missing_columns: dict[str, list[str]] = {}
    for table, expected in REQUIRED_COLUMNS.items():
        if table not in tables:
            continue
        actual = {
            row[1]
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        missing = sorted(expected - actual)
        if missing:
            missing_columns[table] = missing
    if missing_tables or missing_columns:
        details = []
        if missing_tables:
            details.append(f"tabelas ausentes: {', '.join(missing_tables)}")
        if missing_columns:
            rendered = "; ".join(
                f"{table}: {', '.join(columns)}"
                for table, columns in sorted(missing_columns.items())
            )
            details.append(f"colunas ausentes: {rendered}")
        raise ExportError(
            "O esquema do banco não é compatível com a exportação UFPR ("
            + " | ".join(details)
            + ")."
        )


def _rows(
    connection: sqlite3.Connection,
    query: str,
    parameters: Iterable[Any] = (),
) -> list[sqlite3.Row]:
    return list(connection.execute(query, tuple(parameters)))


def _scalar(
    connection: sqlite3.Connection,
    query: str,
    parameters: Iterable[Any] = (),
) -> Any:
    row = connection.execute(query, tuple(parameters)).fetchone()
    return row[0] if row else None


def _nullable_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _clean_short_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _subject_key(value: Any) -> str:
    return _clean_short_text(value).casefold()


def _iso_time(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(str(value)[:8], "%H:%M:%S").time().isoformat(
            timespec="minutes"
        )
    except ValueError:
        try:
            return datetime.strptime(str(value)[:5], "%H:%M").time().isoformat(
                timespec="minutes"
            )
        except ValueError:
            return str(value)


def _parse_database_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    # SQLAlchemy/SQLite remove o offset, mas estes campos são gravados em UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: Any) -> str | None:
    parsed = _parse_database_datetime(value)
    if parsed is None:
        return None
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _iso_local(value: Any) -> str | None:
    parsed = _parse_database_datetime(value)
    if parsed is None:
        return None
    return parsed.astimezone(APP_TIMEZONE).isoformat(timespec="seconds")


def _percentage(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    value = (
        Decimal(str(numerator))
        * Decimal("100")
        / Decimal(str(denominator))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(value)


def _minutes_from_seconds(seconds: int | None) -> float:
    value = Decimal(max(int(seconds or 0), 0)) / Decimal("60")
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _hours_from_minutes(minutes: int | None) -> float:
    value = Decimal(max(int(minutes or 0), 0)) / Decimal("60")
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _study_record(row: sqlite3.Row) -> dict[str, Any]:
    questions = row["questions_count"]
    correct = row["correct_answers"]
    errors = (
        int(questions) - int(correct)
        if questions is not None and correct is not None
        else None
    )
    focus_code = row["focus_quality"]
    return {
        "id_origem": int(row["id"]),
        "data": row["record_date"],
        "materia": _clean_short_text(row["subject"]),
        "materia_chave": _subject_key(row["subject"]),
        "assunto": _clean_short_text(row["topic"]),
        "duracao_minutos": int(row["duration_minutes"]),
        "questoes_resolvidas": int(questions) if questions is not None else None,
        "acertos": int(correct) if correct is not None else None,
        "erros": errors,
        "taxa_acerto_percentual": _percentage(correct or 0, questions or 0),
        "qualidade_foco_codigo": focus_code,
        "qualidade_foco": FOCUS_LABELS.get(focus_code, focus_code),
        "foco_percentual_referencia": FOCUS_PERCENTAGES.get(focus_code),
        "o_que_aprendeu": _nullable_text(row["learned_text"]),
        "dificuldade_encontrada": _nullable_text(row["difficulty_text"]),
        "origem_registro": row["record_origin"],
        "registrado_em_utc": _iso_utc(row["created_at"]),
    }


def _sleep_record(row: sqlite3.Row) -> dict[str, Any]:
    quality_code = row["perceived_quality"]
    restored_code = row["woke_restored"]
    return {
        "id_origem": int(row["id"]),
        "data_despertar": row["record_date"],
        "principal": bool(row["is_primary"]),
        "inicio_horario_registrado": _iso_time(row["sleep_start"]),
        "fim_horario_registrado": _iso_time(row["sleep_end"]),
        "inicio_local": _iso_local(row["sleep_started_at"]),
        "fim_local": _iso_local(row["sleep_ended_at"]),
        "duracao_minutos": int(row["duration_minutes"]),
        "duracao_horas": _hours_from_minutes(row["duration_minutes"]),
        "qualidade_percebida_codigo": quality_code,
        "qualidade_percebida": SLEEP_QUALITY_LABELS.get(quality_code, quality_code),
        "despertares": int(row["awakenings_count"] or 0),
        "acordou_descansado_codigo": restored_code,
        "acordou_descansado": RESTORED_LABELS.get(restored_code, restored_code),
        "observacoes": _nullable_text(row["notes"]),
        "origem_registro": row["record_origin"],
    }


def _focus_session(row: sqlite3.Row) -> dict[str, Any]:
    duration = int(row["actual_duration_seconds"] or 0)
    productive = int(row["productive_seconds"] or 0)
    distracted = int(row["distracted_seconds"] or 0)
    return {
        "id_origem": int(row["id"]),
        "data": row["record_date"],
        "tipo_sessao": row["session_type"],
        "titulo": _clean_short_text(row["title"]),
        "categoria_relacionada": row["related_category"],
        "duracao_alvo_minutos": row["target_duration_minutes"],
        "duracao_real_segundos": duration,
        "duracao_real_minutos": _minutes_from_seconds(duration),
        "monitoramento_computador_ativo": bool(
            row["computer_monitoring_enabled"]
        ),
        "objetivo": _nullable_text(row["objective_text"]),
        "resultado": _nullable_text(row["result_text"]),
        "aprendizado": _nullable_text(row["learned_text"]),
        "dificuldade": _nullable_text(row["difficulty_text"]),
        "autoavaliacao_1_a_10": row["self_rating"],
        "foco_percentual": row["focus_percentage"],
        "tempo_produtivo_segundos": productive,
        "tempo_distraido_segundos": distracted,
        "status": row["status"],
        "inicio_utc": _iso_utc(row["started_at"]),
        "fim_utc": _iso_utc(row["finished_at"]),
        "inicio_local": _iso_local(row["started_at"]),
        "fim_local": _iso_local(row["finished_at"]),
    }


def _computer_period(row: sqlite3.Row) -> dict[str, Any]:
    was_idle = bool(row["was_idle"])
    classification = row["classification"]
    if was_idle:
        period_type = "ocioso"
    elif classification == "productive":
        period_type = "foco_produtivo"
    else:
        period_type = "distracao"
    duration = int(row["duration_seconds"])
    return {
        "id_origem": int(row["id"]),
        "data": row["record_date"],
        "tipo_periodo": period_type,
        "classificacao": classification,
        "categoria": row["category"],
        "inicio_local": _iso_local(row["started_at"]),
        "fim_local": _iso_local(row["ended_at"]),
        "duracao_segundos": duration,
        "duracao_minutos": _minutes_from_seconds(duration),
        "origem_classificacao": row["classification_source"],
        "id_sessao_foco": row["session_id"],
    }


def _display_subject(current: str | None, candidate: str) -> str:
    if current is None:
        return candidate
    if candidate[:1].isupper() and not current[:1].isupper():
        return candidate
    return current


def _daily_study(rows: list[sqlite3.Row]) -> dict[str, Any]:
    questions = sum(int(row["questions_count"] or 0) for row in rows)
    corrected_rows = [row for row in rows if row["correct_answers"] is not None]
    corrected_questions = sum(
        int(row["questions_count"] or 0) for row in corrected_rows
    )
    correct = sum(int(row["correct_answers"] or 0) for row in corrected_rows)
    focus_values = [
        FOCUS_PERCENTAGES[row["focus_quality"]]
        for row in rows
        if row["focus_quality"] in FOCUS_PERCENTAGES
    ]
    subjects: dict[str, str] = {}
    for row in rows:
        key = _subject_key(row["subject"])
        candidate = _clean_short_text(row["subject"])
        subjects[key] = _display_subject(subjects.get(key), candidate)
    total_minutes = sum(int(row["duration_minutes"]) for row in rows)
    return {
        "dados_registrados": bool(rows),
        "tempo_total_minutos": total_minutes,
        "tempo_total_horas": _hours_from_minutes(total_minutes),
        "sessoes": len(rows),
        "materias": sorted(subjects.values(), key=str.casefold),
        "questoes_registradas": questions,
        "questoes_com_resultado": corrected_questions,
        "acertos": correct,
        "erros": corrected_questions - correct,
        "taxa_acerto_percentual": _percentage(correct, corrected_questions),
        "foco_medio_percentual_referencia": (
            round(sum(focus_values) / len(focus_values), 2)
            if focus_values
            else None
        ),
    }


def _daily_sleep(rows: list[sqlite3.Row]) -> dict[str, Any]:
    primary_rows = [row for row in rows if bool(row["is_primary"])]
    primary = primary_rows[0] if primary_rows else None
    total_minutes = sum(int(row["duration_minutes"]) for row in rows)
    nap_minutes = sum(
        int(row["duration_minutes"])
        for row in rows
        if not bool(row["is_primary"])
    )
    quality_code = primary["perceived_quality"] if primary else None
    restored_code = primary["woke_restored"] if primary else None
    return {
        "dados_registrados": bool(rows),
        "sessoes_sono": len(rows),
        "sessoes_principais": len(primary_rows),
        "tempo_total_minutos": total_minutes,
        "tempo_total_horas": _hours_from_minutes(total_minutes),
        "sono_principal_minutos": (
            int(primary["duration_minutes"]) if primary else None
        ),
        "cochilos_minutos": nap_minutes,
        "inicio_sono_principal_local": (
            _iso_local(primary["sleep_started_at"]) if primary else None
        ),
        "fim_sono_principal_local": (
            _iso_local(primary["sleep_ended_at"]) if primary else None
        ),
        "qualidade_percebida_codigo": quality_code,
        "qualidade_percebida": SLEEP_QUALITY_LABELS.get(
            quality_code, quality_code
        ),
        "despertares_sono_principal": (
            int(primary["awakenings_count"] or 0) if primary else None
        ),
        "acordou_descansado_codigo": restored_code,
        "acordou_descansado": RESTORED_LABELS.get(
            restored_code, restored_code
        ),
    }


def _daily_focus_sessions(rows: list[sqlite3.Row]) -> dict[str, Any]:
    completed = [row for row in rows if row["status"] == "completed"]
    focus_values = [
        int(row["focus_percentage"])
        for row in completed
        if row["focus_percentage"] is not None
    ]
    return {
        "dados_registrados": bool(rows),
        "sessoes_totais": len(rows),
        "sessoes_concluidas": len(completed),
        "duracao_concluida_segundos": sum(
            int(row["actual_duration_seconds"] or 0) for row in completed
        ),
        "foco_medio_percentual": (
            round(sum(focus_values) / len(focus_values), 2)
            if focus_values
            else None
        ),
        "tempo_produtivo_segundos": sum(
            int(row["productive_seconds"] or 0) for row in completed
        ),
        "tempo_distraido_segundos": sum(
            int(row["distracted_seconds"] or 0) for row in completed
        ),
    }


def _daily_computer(rows: list[sqlite3.Row]) -> dict[str, Any]:
    totals: defaultdict[str, int] = defaultdict(int)
    study_totals: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        duration = int(row["duration_seconds"] or 0)
        if bool(row["was_idle"]):
            totals["idle"] += duration
            continue
        classification = row["classification"]
        totals[classification] += duration
        if row["category"] == "study" and classification != "ignored":
            study_totals[classification] += duration
    productive = totals["productive"]
    distracted = totals["distracting"]
    return {
        "dados_registrados": bool(rows),
        "tempo_produtivo_segundos": productive,
        "tempo_distraido_segundos": distracted,
        "tempo_neutro_segundos": totals["neutral"],
        "tempo_ocioso_segundos": totals["idle"],
        "tempo_ignorado_segundos": totals["ignored"],
        "taxa_foco_percentual": _percentage(
            productive, productive + distracted
        ),
        "categoria_estudo_total_segundos": sum(study_totals.values()),
        "categoria_estudo_produtivo_segundos": study_totals["productive"],
        "categoria_estudo_distraido_segundos": study_totals["distracting"],
    }


def _date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _build_daily_summaries(
    study_rows: list[sqlite3.Row],
    sleep_rows: list[sqlite3.Row],
    session_rows: list[sqlite3.Row],
    computer_rows: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    grouped_study: defaultdict[str, list[sqlite3.Row]] = defaultdict(list)
    grouped_sleep: defaultdict[str, list[sqlite3.Row]] = defaultdict(list)
    grouped_sessions: defaultdict[str, list[sqlite3.Row]] = defaultdict(list)
    grouped_computer: defaultdict[str, list[sqlite3.Row]] = defaultdict(list)
    all_dates: list[date] = []
    for rows, target in (
        (study_rows, grouped_study),
        (sleep_rows, grouped_sleep),
        (session_rows, grouped_sessions),
        (computer_rows, grouped_computer),
    ):
        for row in rows:
            raw_date = row["record_date"]
            target[raw_date].append(row)
            all_dates.append(date.fromisoformat(raw_date))
    if not all_dates:
        return []
    start, end = min(all_dates), max(all_dates)
    return [
        {
            "data": target_date.isoformat(),
            "dia_semana_iso": target_date.isoweekday(),
            "estudo": _daily_study(grouped_study[target_date.isoformat()]),
            "sono": _daily_sleep(grouped_sleep[target_date.isoformat()]),
            "sessoes_foco": _daily_focus_sessions(
                grouped_sessions[target_date.isoformat()]
            ),
            "computador": _daily_computer(
                grouped_computer[target_date.isoformat()]
            ),
        }
        for target_date in _date_range(start, end)
    ]


def _build_weekly_summaries(
    daily: list[dict[str, Any]],
    first_study_date: date | None,
    weekly_goal_minutes: int | None,
) -> list[dict[str, Any]]:
    if not daily or first_study_date is None:
        return []
    daily_by_date = {item["data"]: item for item in daily}
    export_end = date.fromisoformat(daily[-1]["data"])
    week_start = first_study_date - timedelta(days=first_study_date.weekday())
    summaries = []
    while week_start <= export_end:
        week_end = week_start + timedelta(days=6)
        items = [
            daily_by_date.get(target.isoformat())
            for target in _date_range(week_start, week_end)
        ]
        items = [item for item in items if item is not None]
        study_items = [item["estudo"] for item in items]
        sleep_items = [
            item["sono"] for item in items if item["sono"]["dados_registrados"]
        ]
        computer_items = [item["computador"] for item in items]
        study_minutes = sum(item["tempo_total_minutos"] for item in study_items)
        corrected_questions = sum(
            item["questoes_com_resultado"] for item in study_items
        )
        correct = sum(item["acertos"] for item in study_items)
        iso_year, iso_week, _ = week_start.isocalendar()
        summaries.append(
            {
                "ano_iso": iso_year,
                "semana_iso": iso_week,
                "inicio_semana": week_start.isoformat(),
                "fim_semana": week_end.isoformat(),
                "periodo_observado_inicio": max(
                    week_start, first_study_date
                ).isoformat(),
                "periodo_observado_fim": min(week_end, export_end).isoformat(),
                "estudo": {
                    "dados_registrados": any(
                        item["dados_registrados"] for item in study_items
                    ),
                    "tempo_total_minutos": study_minutes,
                    "sessoes": sum(item["sessoes"] for item in study_items),
                    "dias_com_estudo": sum(
                        item["dados_registrados"] for item in study_items
                    ),
                    "questoes_registradas": sum(
                        item["questoes_registradas"] for item in study_items
                    ),
                    "questoes_com_resultado": corrected_questions,
                    "acertos": correct,
                    "erros": corrected_questions - correct,
                    "taxa_acerto_percentual": _percentage(
                        correct, corrected_questions
                    ),
                    "meta_semanal_minutos": weekly_goal_minutes,
                    "progresso_meta_percentual": (
                        _percentage(study_minutes, weekly_goal_minutes)
                        if weekly_goal_minutes
                        else None
                    ),
                    "meta_cumprida": (
                        study_minutes >= weekly_goal_minutes
                        if weekly_goal_minutes
                        else None
                    ),
                },
                "sono": {
                    "dias_com_registro": len(sleep_items),
                    "media_horas_por_dia_registrado": (
                        round(
                            sum(item["tempo_total_horas"] for item in sleep_items)
                            / len(sleep_items),
                            2,
                        )
                        if sleep_items
                        else None
                    ),
                },
                "computador": {
                    "tempo_produtivo_segundos": sum(
                        item["tempo_produtivo_segundos"]
                        for item in computer_items
                    ),
                    "tempo_distraido_segundos": sum(
                        item["tempo_distraido_segundos"]
                        for item in computer_items
                    ),
                    "categoria_estudo_total_segundos": sum(
                        item["categoria_estudo_total_segundos"]
                        for item in computer_items
                    ),
                },
            }
        )
        week_start += timedelta(days=7)
    return summaries


def _build_subject_performance(
    rows: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _subject_key(row["subject"])
        display = _clean_short_text(row["subject"])
        item = grouped.setdefault(
            key,
            {
                "materia": display,
                "materia_chave": key,
                "datas": set(),
                "sessoes": 0,
                "minutos": 0,
                "questoes": 0,
                "questoes_corrigidas": 0,
                "acertos": 0,
                "focos": [],
            },
        )
        item["materia"] = _display_subject(item["materia"], display)
        item["datas"].add(row["record_date"])
        item["sessoes"] += 1
        item["minutos"] += int(row["duration_minutes"])
        item["questoes"] += int(row["questions_count"] or 0)
        if row["correct_answers"] is not None:
            item["questoes_corrigidas"] += int(row["questions_count"] or 0)
            item["acertos"] += int(row["correct_answers"] or 0)
        if row["focus_quality"] in FOCUS_PERCENTAGES:
            item["focos"].append(FOCUS_PERCENTAGES[row["focus_quality"]])
    result = []
    for item in grouped.values():
        dates = sorted(item.pop("datas"))
        focuses = item.pop("focos")
        result.append(
            {
                "materia": item["materia"],
                "materia_chave": item["materia_chave"],
                "primeira_data_estudo": dates[0],
                "ultima_data_estudo": dates[-1],
                "dias_com_estudo": len(dates),
                "sessoes": item["sessoes"],
                "tempo_total_minutos": item["minutos"],
                "questoes_registradas": item["questoes"],
                "questoes_com_resultado": item["questoes_corrigidas"],
                "acertos": item["acertos"],
                "erros": item["questoes_corrigidas"] - item["acertos"],
                "taxa_acerto_percentual": _percentage(
                    item["acertos"], item["questoes_corrigidas"]
                ),
                "foco_medio_percentual_referencia": (
                    round(sum(focuses) / len(focuses), 2)
                    if focuses
                    else None
                ),
            }
        )
    return sorted(
        result,
        key=lambda item: (-item["tempo_total_minutos"], item["materia"].casefold()),
    )


def _longest_streak(active_dates: set[date]) -> int:
    longest = current = 0
    previous: date | None = None
    for target in sorted(active_dates):
        current = current + 1 if previous == target - timedelta(days=1) else 1
        longest = max(longest, current)
        previous = target
    return longest


def _build_consistency(
    study_rows: list[sqlite3.Row],
    export_end: date | None,
    weekly: list[dict[str, Any]],
    weekly_goal_minutes: int | None,
) -> dict[str, Any]:
    active_dates = {
        date.fromisoformat(row["record_date"]) for row in study_rows
    }
    if not active_dates or export_end is None:
        return {
            "inicio_periodo_observado": None,
            "fim_periodo_observado": export_end.isoformat() if export_end else None,
            "dias_calendario_observados": 0,
            "dias_com_estudo": 0,
            "taxa_dias_com_estudo_percentual": None,
            "maior_sequencia_dias": 0,
            "sequencia_no_fim_do_periodo_dias": 0,
            "ultima_data_com_estudo": None,
            "semanas_com_meta_cumprida": None,
        }
    start = min(active_dates)
    observed_days = (export_end - start).days + 1
    end_streak = 0
    cursor = export_end
    while cursor in active_dates:
        end_streak += 1
        cursor -= timedelta(days=1)
    goals_met = (
        sum(item["estudo"]["meta_cumprida"] is True for item in weekly)
        if weekly_goal_minutes
        else None
    )
    return {
        "inicio_periodo_observado": start.isoformat(),
        "fim_periodo_observado": export_end.isoformat(),
        "dias_calendario_observados": observed_days,
        "dias_com_estudo": len(active_dates),
        "taxa_dias_com_estudo_percentual": _percentage(
            len(active_dates), observed_days
        ),
        "maior_sequencia_dias": _longest_streak(active_dates),
        "sequencia_no_fim_do_periodo_dias": end_streak,
        "ultima_data_com_estudo": max(active_dates).isoformat(),
        "semanas_com_meta_cumprida": goals_met,
    }


def _coverage(
    connection: sqlite3.Connection,
    table: str,
) -> dict[str, Any]:
    row = connection.execute(
        f'SELECT MIN(record_date), MAX(record_date), COUNT(*) FROM "{table}"'
    ).fetchone()
    return {
        "primeira_data": row[0],
        "ultima_data": row[1],
        "linhas": int(row[2]),
    }


def _duplicate_stats(connection: sqlite3.Connection) -> dict[str, Any]:
    study_group = """
        SELECT COUNT(*) AS quantidade
        FROM study_records
        GROUP BY record_date, subject, topic, duration_minutes,
                 questions_count, correct_answers, focus_quality,
                 learned_text, difficulty_text, record_origin
        HAVING COUNT(*) > 1
    """
    study_duplicates = [int(row[0]) for row in connection.execute(study_group)]
    sleep_group = """
        SELECT COUNT(*) AS quantidade
        FROM sleep_records
        GROUP BY record_date, sleep_start, sleep_end, duration_minutes,
                 perceived_quality, awakenings_count, woke_restored, notes,
                 record_origin, sleep_started_at, sleep_ended_at, is_primary
        HAVING COUNT(*) > 1
    """
    sleep_duplicates = [int(row[0]) for row in connection.execute(sleep_group)]
    computer_group = """
        SELECT COUNT(*) AS quantidade
        FROM computer_activity_blocks
        GROUP BY record_date, classification, category, classification_source,
                 started_at, ended_at, duration_seconds, was_idle, session_id
        HAVING COUNT(*) > 1
    """
    computer_duplicates = [int(row[0]) for row in connection.execute(computer_group)]
    session_group = """
        SELECT COUNT(*) AS quantidade
        FROM session_records
        GROUP BY record_date, session_type, title, related_category,
                 target_duration_minutes, actual_duration_seconds,
                 objective_text, result_text, learned_text, difficulty_text,
                 self_rating, focus_percentage, productive_seconds,
                 distracted_seconds, status, started_at, finished_at
        HAVING COUNT(*) > 1
    """
    session_duplicates = [int(row[0]) for row in connection.execute(session_group)]
    return {
        "estudo": {
            "grupos": len(study_duplicates),
            "linhas_excedentes": sum(value - 1 for value in study_duplicates),
        },
        "sessoes_foco": {
            "grupos": len(session_duplicates),
            "linhas_excedentes": sum(value - 1 for value in session_duplicates),
        },
        "sono": {
            "grupos": len(sleep_duplicates),
            "linhas_excedentes": sum(value - 1 for value in sleep_duplicates),
        },
        "computador": {
            "grupos": len(computer_duplicates),
            "linhas_excedentes": sum(value - 1 for value in computer_duplicates),
        },
        "sono_ids_fonte_repetidos": int(
            _scalar(
                connection,
                """
                SELECT COUNT(*) FROM (
                    SELECT source_record_id
                    FROM sleep_records
                    WHERE source_record_id IS NOT NULL
                    GROUP BY source_record_id
                    HAVING COUNT(*) > 1
                )
                """,
            )
            if "source_record_id"
            in {
                row[1]
                for row in connection.execute(
                    'PRAGMA table_info("sleep_records")'
                )
            }
            else 0
        ),
        "datas_com_multiplos_sonos_principais": int(
            _scalar(
                connection,
                """
                SELECT COUNT(*) FROM (
                    SELECT record_date
                    FROM sleep_records
                    WHERE is_primary = 1
                    GROUP BY record_date
                    HAVING COUNT(*) > 1
                )
                """,
            )
        ),
    }


def _semantic_issues(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "estudo_valores_invalidos": int(
            _scalar(
                connection,
                """
                SELECT COUNT(*) FROM study_records
                WHERE duration_minutes <= 0
                   OR questions_count < 0
                   OR correct_answers < 0
                   OR (correct_answers IS NOT NULL AND questions_count IS NULL)
                   OR correct_answers > questions_count
                   OR trim(subject) = ''
                   OR trim(topic) = ''
                   OR focus_quality NOT IN
                      ('low', 'regular', 'good', 'very_good', 'excellent')
                """,
            )
        ),
        "sono_valores_invalidos": int(
            _scalar(
                connection,
                """
                SELECT COUNT(*) FROM sleep_records
                WHERE duration_minutes <= 0
                   OR awakenings_count < 0
                   OR is_primary NOT IN (0, 1)
                   OR (sleep_started_at IS NOT NULL
                       AND sleep_ended_at IS NOT NULL
                       AND sleep_ended_at <= sleep_started_at)
                """,
            )
        ),
        "sessoes_foco_valores_invalidos": int(
            _scalar(
                connection,
                """
                SELECT COUNT(*) FROM session_records
                WHERE target_duration_minutes <= 0
                   OR actual_duration_seconds < 0
                   OR productive_seconds < 0
                   OR distracted_seconds < 0
                   OR productive_seconds + distracted_seconds
                      > actual_duration_seconds
                   OR focus_percentage < 0
                   OR focus_percentage > 100
                   OR self_rating < 1
                   OR self_rating > 10
                """,
            )
        ),
        "computador_valores_invalidos": int(
            _scalar(
                connection,
                """
                SELECT COUNT(*) FROM computer_activity_blocks
                WHERE duration_seconds <= 0
                   OR ended_at <= started_at
                   OR classification NOT IN
                      ('productive', 'distracting', 'neutral', 'ignored')
                   OR category NOT IN
                      ('study', 'programming', 'work', 'communication',
                       'entertainment', 'social', 'gaming', 'system', 'other')
                """,
            )
        ),
        "metas_numericas_invalidas": int(
            _scalar(
                connection,
                """
                SELECT COUNT(*) FROM user_profile
                WHERE weekly_study_minutes <= 0
                   OR sleep_target_minutes <= 0
                """,
            )
        ),
    }


def _missing_stats(connection: sqlite3.Connection) -> dict[str, Any]:
    return {
        "estudo_sem_questoes": int(
            _scalar(
                connection,
                "SELECT COUNT(*) FROM study_records WHERE questions_count IS NULL",
            )
        ),
        "estudo_sem_resultado_questoes": int(
            _scalar(
                connection,
                "SELECT COUNT(*) FROM study_records WHERE correct_answers IS NULL",
            )
        ),
        "estudo_sem_texto_aprendizado": int(
            _scalar(
                connection,
                """
                SELECT COUNT(*) FROM study_records
                WHERE learned_text IS NULL OR trim(learned_text) = ''
                """,
            )
        ),
        "sono_sem_qualidade_percebida": int(
            _scalar(
                connection,
                "SELECT COUNT(*) FROM sleep_records WHERE perceived_quality IS NULL",
            )
        ),
        "sono_sem_resposta_descanso": int(
            _scalar(
                connection,
                "SELECT COUNT(*) FROM sleep_records WHERE woke_restored IS NULL",
            )
        ),
        "sessoes_foco_sem_foco_percentual": int(
            _scalar(
                connection,
                "SELECT COUNT(*) FROM session_records WHERE focus_percentage IS NULL",
            )
        ),
    }


def _check(
    name: str,
    source_value: Any,
    exported_value: Any,
) -> dict[str, Any]:
    return {
        "verificacao": name,
        "status": "ok" if source_value == exported_value else "erro",
        "valor_fonte": source_value,
        "valor_exportado": exported_value,
    }


def _unique_ids(items: list[dict[str, Any]]) -> bool:
    ids = [item["id_origem"] for item in items]
    return len(ids) == len(set(ids))


def _build_validation(
    connection: sqlite3.Connection,
    study_rows: list[sqlite3.Row],
    sleep_rows: list[sqlite3.Row],
    session_rows: list[sqlite3.Row],
    computer_rows: list[sqlite3.Row],
    exported_study: list[dict[str, Any]],
    exported_sleep: list[dict[str, Any]],
    exported_sessions: list[dict[str, Any]],
    exported_periods: list[dict[str, Any]],
    daily: list[dict[str, Any]],
    duplicates: dict[str, Any],
    missing: dict[str, Any],
    semantic_issues: dict[str, int],
) -> dict[str, Any]:
    integrity_rows = [
        row[0] for row in connection.execute("PRAGMA integrity_check")
    ]
    foreign_key_issues = len(
        list(connection.execute("PRAGMA foreign_key_check"))
    )
    expected_period_rows = [
        row
        for row in computer_rows
        if bool(row["was_idle"])
        or row["classification"] in {"productive", "distracting"}
    ]
    checks = [
        _check("linhas de estudo", len(study_rows), len(exported_study)),
        _check(
            "minutos de estudo",
            sum(int(row["duration_minutes"]) for row in study_rows),
            sum(item["duracao_minutos"] for item in exported_study),
        ),
        _check(
            "questões registradas",
            sum(int(row["questions_count"] or 0) for row in study_rows),
            sum(int(item["questoes_resolvidas"] or 0) for item in exported_study),
        ),
        _check(
            "acertos registrados",
            sum(int(row["correct_answers"] or 0) for row in study_rows),
            sum(int(item["acertos"] or 0) for item in exported_study),
        ),
        _check("linhas de sono", len(sleep_rows), len(exported_sleep)),
        _check(
            "minutos de sono",
            sum(int(row["duration_minutes"]) for row in sleep_rows),
            sum(item["duracao_minutos"] for item in exported_sleep),
        ),
        _check("linhas de sessões de foco", len(session_rows), len(exported_sessions)),
        _check(
            "segundos das sessões de foco",
            sum(int(row["actual_duration_seconds"] or 0) for row in session_rows),
            sum(item["duracao_real_segundos"] for item in exported_sessions),
        ),
        _check(
            "períodos produtivos, distraídos ou ociosos",
            len(expected_period_rows),
            len(exported_periods),
        ),
        _check(
            "segundos dos períodos exportados",
            sum(int(row["duration_seconds"]) for row in expected_period_rows),
            sum(item["duracao_segundos"] for item in exported_periods),
        ),
        _check("IDs únicos de estudo", True, _unique_ids(exported_study)),
        _check("IDs únicos de sono", True, _unique_ids(exported_sleep)),
        _check("IDs únicos de sessões", True, _unique_ids(exported_sessions)),
        _check("IDs únicos de períodos", True, _unique_ids(exported_periods)),
    ]
    source_computer_totals: defaultdict[str, int] = defaultdict(int)
    for row in computer_rows:
        duration = int(row["duration_seconds"] or 0)
        if bool(row["was_idle"]):
            source_computer_totals["idle"] += duration
        else:
            source_computer_totals[row["classification"]] += duration
    daily_study_minutes = sum(
        item["estudo"]["tempo_total_minutos"] for item in daily
    )
    daily_questions = sum(
        item["estudo"]["questoes_registradas"] for item in daily
    )
    checks.extend(
        [
            _check(
                "minutos de estudo nos resumos diários",
                sum(int(row["duration_minutes"]) for row in study_rows),
                daily_study_minutes,
            ),
            _check(
                "questões nos resumos diários",
                sum(int(row["questions_count"] or 0) for row in study_rows),
                daily_questions,
            ),
            _check(
                "segundos produtivos nos resumos diários",
                source_computer_totals["productive"],
                sum(
                    item["computador"]["tempo_produtivo_segundos"]
                    for item in daily
                ),
            ),
            _check(
                "segundos distraídos nos resumos diários",
                source_computer_totals["distracting"],
                sum(
                    item["computador"]["tempo_distraido_segundos"]
                    for item in daily
                ),
            ),
            _check(
                "segundos neutros nos resumos diários",
                source_computer_totals["neutral"],
                sum(
                    item["computador"]["tempo_neutro_segundos"]
                    for item in daily
                ),
            ),
            _check(
                "segundos ociosos nos resumos diários",
                source_computer_totals["idle"],
                sum(
                    item["computador"]["tempo_ocioso_segundos"]
                    for item in daily
                ),
            ),
            _check(
                "segundos ignorados nos resumos diários",
                source_computer_totals["ignored"],
                sum(
                    item["computador"]["tempo_ignorado_segundos"]
                    for item in daily
                ),
            ),
        ]
    )
    all_dates = [
        date.fromisoformat(row["record_date"])
        for rows in (study_rows, sleep_rows, session_rows, computer_rows)
        for row in rows
    ]
    expected_daily = (
        (max(all_dates) - min(all_dates)).days + 1 if all_dates else 0
    )
    checks.append(_check("dias contínuos no resumo", expected_daily, len(daily)))
    integrity_ok = integrity_rows == ["ok"]
    foreign_keys_ok = foreign_key_issues == 0
    checks_ok = all(item["status"] == "ok" for item in checks)
    has_duplicate_warning = any(
        duplicates[key]["grupos"] > 0
        for key in ("estudo", "sessoes_foco", "sono", "computador")
    ) or bool(
        duplicates["sono_ids_fonte_repetidos"]
        or duplicates["datas_com_multiplos_sonos_principais"]
    )
    semantic_ok = not any(semantic_issues.values())
    return {
        "status_geral": (
            "aprovado"
            if integrity_ok and foreign_keys_ok and checks_ok and semantic_ok
            else "reprovado"
        ),
        "integridade_sqlite": integrity_rows,
        "problemas_chaves_estrangeiras": foreign_key_issues,
        "verificacoes": checks,
        "duplicatas_suspeitas_na_fonte": duplicates,
        "aviso_duplicatas": has_duplicate_warning,
        "valores_ausentes": missing,
        "inconsistencias_semanticas": semantic_issues,
    }


def _load_profile(connection: sqlite3.Connection) -> tuple[dict[str, Any], int]:
    rows = _rows(
        connection,
        """
        SELECT id, academic_goal, weekly_study_minutes, sleep_target_minutes
        FROM user_profile
        ORDER BY id
        """,
    )
    if not rows:
        return {
            "id_perfil_origem": None,
            "objetivo_academico": None,
            "meta_estudo_semanal_minutos": None,
            "meta_sono_por_noite_minutos": None,
        }, 0
    row = rows[0]
    return {
        "id_perfil_origem": int(row["id"]),
        "objetivo_academico": _nullable_text(row["academic_goal"]),
        "meta_estudo_semanal_minutos": row["weekly_study_minutes"],
        "meta_sono_por_noite_minutos": row["sleep_target_minutes"],
    }, len(rows)


def build_export(
    connection: sqlite3.Connection,
    *,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _validate_schema(connection)
    generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    study_rows = _rows(
        connection,
        "SELECT * FROM study_records ORDER BY record_date, created_at, id",
    )
    sleep_rows = _rows(
        connection,
        """
        SELECT * FROM sleep_records
        ORDER BY record_date, is_primary DESC, sleep_started_at, id
        """,
    )
    session_rows = _rows(
        connection,
        "SELECT * FROM session_records ORDER BY record_date, started_at, id",
    )
    computer_rows = _rows(
        connection,
        """
        SELECT * FROM computer_activity_blocks
        ORDER BY record_date, started_at, id
        """,
    )
    exported_study = [_study_record(row) for row in study_rows]
    exported_sleep = [_sleep_record(row) for row in sleep_rows]
    exported_sessions = [_focus_session(row) for row in session_rows]
    exported_periods = [
        _computer_period(row)
        for row in computer_rows
        if bool(row["was_idle"])
        or row["classification"] in {"productive", "distracting"}
    ]
    daily = _build_daily_summaries(
        study_rows,
        sleep_rows,
        session_rows,
        computer_rows,
    )
    goals, profile_rows = _load_profile(connection)
    first_study_date = (
        min(date.fromisoformat(row["record_date"]) for row in study_rows)
        if study_rows
        else None
    )
    export_end = date.fromisoformat(daily[-1]["data"]) if daily else None
    weekly = _build_weekly_summaries(
        daily,
        first_study_date,
        goals["meta_estudo_semanal_minutos"],
    )
    duplicates = _duplicate_stats(connection)
    missing = _missing_stats(connection)
    semantic_issues = _semantic_issues(connection)
    validation = _build_validation(
        connection,
        study_rows,
        sleep_rows,
        session_rows,
        computer_rows,
        exported_study,
        exported_sleep,
        exported_sessions,
        exported_periods,
        daily,
        duplicates,
        missing,
        semantic_issues,
    )
    migration = _scalar(connection, "SELECT version_num FROM alembic_version")
    coverage = {
        "estudo": _coverage(connection, "study_records"),
        "sono": _coverage(connection, "sleep_records"),
        "sessoes_foco": _coverage(connection, "session_records"),
        "computador": _coverage(connection, "computer_activity_blocks"),
    }
    export = {
        "metadados": {
            "schema_exportacao": EXPORT_SCHEMA_VERSION,
            "gerado_em_utc": generated.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
            "fuso_horario_local": APP_TIMEZONE_NAME,
            "fonte": "banco SQLite ativo do Condution Time",
            "versao_migracao_fonte": migration,
            "cobertura_fontes": coverage,
            "politica_valores_ausentes": (
                "null significa desconhecido ou não informado; zero só representa "
                "uma contagem/duração realmente nula ou ausência de linhas, sempre "
                "acompanhada por dados_registrados"
            ),
        },
        "metas": goals,
        "sessoes_estudo": exported_study,
        "sessoes_foco": exported_sessions,
        "sessoes_sono": exported_sleep,
        "periodos_computador": exported_periods,
        "resumos_diarios": daily,
        "resumos_semanais": weekly,
        "desempenho_por_materia": _build_subject_performance(study_rows),
        "consistencia_estudo": _build_consistency(
            study_rows,
            export_end,
            weekly,
            goals["meta_estudo_semanal_minutos"],
        ),
        "qualidade_dados": {
            "status_validacao": validation["status_geral"],
            "duplicatas_suspeitas_na_fonte": duplicates,
            "valores_ausentes": missing,
            "inconsistencias_semanticas": semantic_issues,
            "perfis_encontrados": profile_rows,
            "perfil_utilizado": "menor id" if profile_rows else None,
        },
    }
    report = {
        "schema_exportacao": EXPORT_SCHEMA_VERSION,
        "gerado_em_utc": export["metadados"]["gerado_em_utc"],
        "versao_migracao_fonte": migration,
        "cobertura_fontes": coverage,
        "validacao": validation,
        "linhas_exportadas": {
            "sessoes_estudo": len(exported_study),
            "sessoes_foco": len(exported_sessions),
            "sessoes_sono": len(exported_sleep),
            "periodos_computador": len(exported_periods),
            "resumos_diarios": len(daily),
            "resumos_semanais": len(weekly),
            "materias": len(export["desempenho_por_materia"]),
        },
        "dados_omitidos_por_escopo": [
            "identidade, nascimento e medidas corporais do perfil",
            "treinos e métricas biométricas",
            "alimentação e hidratação",
            "XP, conquistas, notificações e logs de importação",
            "nomes de aplicativos, projetos e sites monitorados",
            "blocos individuais neutros ou ignorados do computador",
            "hashes e identificadores externos do Health Connect",
        ],
    }
    return export, report


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
    except Exception:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_export(
    database: Path,
    output: Path,
    validation_output: Path,
) -> dict[str, Any]:
    resolved_output = output.expanduser().resolve()
    resolved_validation = validation_output.expanduser().resolve()
    if resolved_output == resolved_validation:
        raise ExportError("O JSON principal e o relatório precisam de caminhos distintos.")
    connection = _connect_read_only(database)
    try:
        export, report = build_export(connection)
    finally:
        connection.rollback()
        connection.close()
    _atomic_json_write(resolved_output, export)
    report["arquivo_exportado"] = resolved_output.name
    report["sha256_exportacao"] = _sha256(resolved_output)
    _atomic_json_write(resolved_validation, report)
    return {
        "status": report["validacao"]["status_geral"],
        "arquivo": str(resolved_output),
        "relatorio": str(resolved_validation),
        "sha256": report["sha256_exportacao"],
        "linhas_exportadas": report["linhas_exportadas"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Exporta em modo somente leitura os dados do Condution Time "
            "relevantes à preparação para a UFPR."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=default_database_path(),
        help=(
            "Banco SQLite de origem. Padrão: "
            "LOCALAPPDATA/CondutionTime/data/condution_time.db"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output_path(),
        help="Destino do JSON consolidado.",
    )
    parser.add_argument(
        "--validation-output",
        type=Path,
        default=default_validation_path(),
        help="Destino do relatório JSON de validação.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_export(args.database, args.output, args.validation_output)
    except (ExportError, sqlite3.Error, OSError, ValueError) as exc:
        print(json.dumps({"status": "erro", "mensagem": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "aprovado" else 2


if __name__ == "__main__":
    raise SystemExit(main())
