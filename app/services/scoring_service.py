from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

from flask import current_app, has_app_context

from app.extensions import db


CATEGORY_MAX_SCORE = 20
TOTAL_CATEGORIES = 5
MAX_BASE_SCORE = 100
MAX_SESSION_BONUS = 10
MAX_FINAL_SCORE = 110

DEFAULT_SLEEP_TARGET_MINUTES = 480
DEFAULT_HYDRATION_TARGET_ML = 2000
DEFAULT_DISTRACTION_LIMIT_SECONDS = 7200

FOCUS_POINTS = {
    "low": 0,
    "regular": 2,
    "good": 3,
    "very_good": 4,
    "excellent": 5,
}
PERFORMANCE_POINTS = {
    "bad": 0,
    "regular": 1,
    "good": 2,
    "very_good": 3,
    "excellent": 3,
}
SLEEP_QUALITY_POINTS = {
    "terrible": 0,
    "bad": 1,
    "regular": 3,
    "good": 4,
    "excellent": 5,
}
RESTORED_POINTS = {"no": 0, "partially": 2, "yes": 4}
MEAL_QUALITY_POINTS = {
    "very_bad": 0,
    "bad": 1,
    "regular": 3,
    "good": 4,
    "excellent": 5,
}


def _round_half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _clamp(value: int | float, minimum: int, maximum: int) -> int:
    return max(minimum, min(_round_half_up(value), maximum))


def _configured_positive_int(name: str, fallback: int) -> int:
    if not has_app_context():
        return fallback
    try:
        value = int(current_app.config.get(name, fallback))
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _text_present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _detail(
    key: str,
    label: str,
    score: int,
    max_score: int,
    detail: str,
    *,
    neutral: bool = False,
    approximate: bool = False,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "key": key,
        "label": label,
        "score": _clamp(score, 0, max_score),
        "max_score": max_score,
        "detail": detail,
    }
    if neutral:
        item["neutral"] = True
    if approximate:
        item["approximate"] = True
    return item


def get_score_message(score: int, max_score: int = 100) -> str:
    percentage = 0 if max_score <= 0 else _clamp(score / max_score * 100, 0, 110)
    if percentage <= 39:
        return "Seu dia ainda precisa de atenção."
    if percentage <= 59:
        return "Você começou, mas ainda pode avançar."
    if percentage <= 74:
        return "Bom progresso no dia."
    if percentage <= 89:
        return "Seu dia está muito bom."
    if percentage <= 100:
        return "Excelente equilíbrio hoje."
    return "Dia excepcional. Você superou sua meta."


def _category_result(
    category: str,
    evaluated: bool,
    breakdown: list[dict[str, Any]],
    *,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    score = (
        _clamp(sum(item["score"] for item in breakdown), 0, CATEGORY_MAX_SCORE)
        if evaluated
        else 0
    )
    return {
        "category": category,
        "evaluated": evaluated,
        "score": score,
        "max_score": CATEGORY_MAX_SCORE,
        "percentage": score * 5,
        "breakdown": breakdown,
        "message": (
            get_score_message(score, CATEGORY_MAX_SCORE)
            if evaluated
            else "Categoria ainda não avaliada."
        ),
        "warnings": warnings or [],
    }


def calculate_study_score(records: Iterable[Any]) -> dict[str, Any]:
    records = list(records)
    if not records:
        return _category_result("study", False, [])

    total_minutes = sum(max(0, int(record.duration_minutes or 0)) for record in records)
    if total_minutes == 0:
        duration_points = 0
    elif total_minutes < 30:
        duration_points = 2
    elif total_minutes < 60:
        duration_points = 4
    elif total_minutes < 90:
        duration_points = 6
    elif total_minutes < 120:
        duration_points = 7
    else:
        duration_points = 8

    focus_scores = [
        FOCUS_POINTS.get(getattr(record, "focus_quality", None), 0)
        for record in records
    ]
    focus_points = _round_half_up(sum(focus_scores) / len(focus_scores))

    question_total = sum(
        max(0, int(record.questions_count or 0))
        for record in records
        if getattr(record, "questions_count", None) is not None
    )
    if question_total == 0:
        practice_points = 0
    elif question_total <= 5:
        practice_points = 1
    elif question_total <= 15:
        practice_points = 2
    elif question_total <= 30:
        practice_points = 3
    else:
        practice_points = 4

    answered_records = [
        record
        for record in records
        if getattr(record, "questions_count", None)
        and getattr(record, "correct_answers", None) is not None
    ]
    answered_questions = sum(int(record.questions_count) for record in answered_records)
    correct_answers = sum(int(record.correct_answers) for record in answered_records)
    if answered_questions <= 0:
        result_points = 0
        result_detail = "Neutro: sem questões corrigidas"
    else:
        accuracy = correct_answers / answered_questions * 100
        result_points = 0 if accuracy < 40 else 1 if accuracy < 60 else 2
        result_detail = f"{correct_answers} de {answered_questions} ({_round_half_up(accuracy)}%)"

    complete = any(
        _text_present(getattr(record, "subject", None))
        and _text_present(getattr(record, "topic", None))
        and int(getattr(record, "duration_minutes", 0) or 0) > 0
        and bool(getattr(record, "focus_quality", None))
        and _text_present(getattr(record, "learned_text", None))
        for record in records
    )

    breakdown = [
        _detail("duration", "Tempo estudado", duration_points, 8, f"{total_minutes} min"),
        _detail("focus", "Foco", focus_points, 5, f"Média de {len(records)} registro(s)"),
        _detail(
            "practice",
            "Prática",
            practice_points,
            4,
            f"{question_total} questão(ões)" if question_total else "Sem questões registradas",
            neutral=question_total == 0,
        ),
        _detail(
            "result",
            "Resultado",
            result_points,
            2,
            result_detail,
            neutral=answered_questions == 0,
        ),
        _detail(
            "complete_record",
            "Registro completo",
            1 if complete else 0,
            1,
            "Registro completo" if complete else "Campos obrigatórios incompletos",
        ),
    ]
    return _category_result("study", True, breakdown)


def calculate_training_score(
    records: Iterable[Any],
    weekly_records: Iterable[Any] | None = None,
) -> dict[str, Any]:
    records = list(records)
    if not records:
        return _category_result("training", False, [])

    total_minutes = sum(max(0, int(record.duration_minutes or 0)) for record in records)
    if total_minutes < 20:
        duration_points = 2 if total_minutes > 0 else 0
    elif total_minutes < 40:
        duration_points = 4
    elif total_minutes < 60:
        duration_points = 5
    else:
        duration_points = 6

    average_intensity = sum(int(record.intensity or 0) for record in records) / len(records)
    if average_intensity <= 2:
        intensity_points = 1
    elif average_intensity <= 4:
        intensity_points = 2
    elif average_intensity <= 8:
        intensity_points = 4
    else:
        intensity_points = 3

    performance_scores = [
        PERFORMANCE_POINTS.get(getattr(record, "perceived_performance", None), 0)
        for record in records
    ]
    performance_points = _round_half_up(
        sum(performance_scores) / len(performance_scores)
    )

    has_activity = any(
        _text_present(getattr(record, "activity_name", None)) for record in records
    )
    has_exercises = any(
        _text_present(getattr(record, "exercises_text", None)) for record in records
    )
    completion_points = (1 if has_activity else 0) + (2 if has_exercises else 0)

    consistency_source = list(weekly_records) if weekly_records is not None else records
    training_days = len(
        {
            getattr(record, "record_date", None)
            for record in consistency_source
            if getattr(record, "record_date", None) is not None
        }
    )
    consistency_points = 0 if training_days <= 1 else 1 if training_days == 2 else 2 if training_days == 3 else 3

    complete = any(
        bool(getattr(record, "training_type", None))
        and _text_present(getattr(record, "activity_name", None))
        and int(getattr(record, "duration_minutes", 0) or 0) > 0
        and getattr(record, "intensity", None) is not None
        and bool(getattr(record, "perceived_performance", None))
        for record in records
    )
    discomforts = [
        getattr(record, "discomfort_level", None)
        for record in records
        if getattr(record, "discomfort_level", None) in {"moderate", "strong"}
    ]
    warnings = (
        ["Há desconforto moderado ou forte registrado; considere atenção adequada."]
        if discomforts
        else []
    )

    breakdown = [
        _detail("duration", "Duração", duration_points, 6, f"{total_minutes} min"),
        _detail(
            "intensity",
            "Intensidade adequada",
            intensity_points,
            4,
            f"Média {_round_half_up(average_intensity * 10) / 10:g}/10",
        ),
        _detail(
            "performance",
            "Desempenho percebido",
            performance_points,
            3,
            f"Média de {len(records)} registro(s)",
        ),
        _detail(
            "completion",
            "Cumprimento do treino",
            completion_points,
            3,
            "Aproximação por atividade e exercícios preenchidos",
            approximate=True,
        ),
        _detail(
            "weekly_consistency",
            "Consistência semanal",
            consistency_points,
            3,
            f"{training_days} dia(s) com treino nos últimos 7 dias",
            approximate=True,
        ),
        _detail(
            "complete_record",
            "Registro completo",
            1 if complete else 0,
            1,
            "Registro completo" if complete else "Campos obrigatórios incompletos",
        ),
    ]
    return _category_result("training", True, breakdown, warnings=warnings)


def calculate_sleep_score(
    record: Any | None,
    target_minutes: int | None = None,
) -> dict[str, Any]:
    if record is None:
        return _category_result("sleep", False, [])

    target = target_minutes or _configured_positive_int(
        "DEFAULT_SLEEP_TARGET_MINUTES",
        DEFAULT_SLEEP_TARGET_MINUTES,
    )
    duration = max(0, int(getattr(record, "duration_minutes", 0) or 0))
    ratio = duration / target * 100 if target else 0
    scaled_duration = duration * 100
    if scaled_duration < target * 60:
        duration_points = 0
    elif scaled_duration < target * 75:
        duration_points = 3
    elif scaled_duration < target * 90:
        duration_points = 6
    elif scaled_duration <= target * 110:
        duration_points = 8
    elif scaled_duration <= target * 125:
        duration_points = 6
    else:
        duration_points = 4

    quality_points = SLEEP_QUALITY_POINTS.get(
        getattr(record, "perceived_quality", None),
        0,
    )
    restored_points = RESTORED_POINTS.get(getattr(record, "woke_restored", None), 0)
    awakenings = max(0, int(getattr(record, "awakenings_count", 0) or 0))
    continuity_points = 2 if awakenings == 0 else 1 if awakenings <= 2 else 0
    complete = (
        getattr(record, "sleep_start", None) is not None
        and getattr(record, "sleep_end", None) is not None
        and duration > 0
        and bool(getattr(record, "perceived_quality", None))
        and getattr(record, "awakenings_count", None) is not None
        and bool(getattr(record, "woke_restored", None))
    )

    breakdown = [
        _detail(
            "duration",
            "Duração",
            duration_points,
            8,
            f"{duration} min de uma meta de {target} min ({_round_half_up(ratio)}%)",
        ),
        _detail("quality", "Qualidade percebida", quality_points, 5, str(getattr(record, "perceived_quality", "—"))),
        _detail("restored", "Acordou descansado", restored_points, 4, str(getattr(record, "woke_restored", "—"))),
        _detail("continuity", "Continuidade", continuity_points, 2, f"{awakenings} despertar(es)"),
        _detail(
            "complete_record",
            "Registro completo",
            1 if complete else 0,
            1,
            "Registro completo" if complete else "Campos obrigatórios incompletos",
        ),
    ]
    return _category_result("sleep", True, breakdown)


def calculate_nutrition_score(
    meals: Iterable[Any],
    hydration_records: Iterable[Any],
    hydration_target_ml: int | None = None,
) -> dict[str, Any]:
    meals = list(meals)
    hydration_records = list(hydration_records)
    if not meals and not hydration_records:
        return _category_result("nutrition", False, [])

    meal_count = len(meals)
    regularity_points = min(meal_count, 3)

    quality_scores = [
        MEAL_QUALITY_POINTS.get(getattr(meal, "perceived_quality", None), 0)
        for meal in meals
    ]
    quality_points = (
        _round_half_up(sum(quality_scores) / len(quality_scores))
        if quality_scores
        else 0
    )
    protein_count = sum(getattr(meal, "has_protein", None) == "yes" for meal in meals)
    produce_count = sum(
        getattr(meal, "has_fruits_or_vegetables", None) == "yes" for meal in meals
    )
    protein_points = 0 if protein_count == 0 else 2 if protein_count == 1 else 4
    produce_points = 0 if produce_count == 0 else 2 if produce_count == 1 else 4

    hydration_total = sum(
        max(0, int(getattr(record, "amount_ml", 0) or 0))
        for record in hydration_records
    )
    target = hydration_target_ml or _configured_positive_int(
        "DEFAULT_HYDRATION_TARGET_ML",
        DEFAULT_HYDRATION_TARGET_ML,
    )
    hydration_ratio = hydration_total / target * 100 if target else 0
    if hydration_ratio < 40:
        hydration_points = 0
    elif hydration_ratio < 70:
        hydration_points = 1
    elif hydration_ratio < 100:
        hydration_points = 2
    else:
        hydration_points = 3

    conscious = any(
        bool(getattr(meal, "meal_type", None))
        and getattr(meal, "meal_time", None) is not None
        and _text_present(getattr(meal, "foods_text", None))
        and bool(getattr(meal, "perceived_quality", None))
        for meal in meals
    )
    unknown_protein_count = sum(
        getattr(meal, "has_protein", None) == "unknown"
        for meal in meals
    )
    unknown_produce_count = sum(
        getattr(meal, "has_fruits_or_vegetables", None) == "unknown"
        for meal in meals
    )

    breakdown = [
        _detail("regularity", "Regularidade", regularity_points, 3, f"{meal_count} refeição(ões)"),
        _detail(
            "quality",
            "Qualidade média",
            quality_points,
            5,
            f"Média de {len(quality_scores)} refeição(ões)" if quality_scores else "Neutro: sem refeições",
            neutral=not quality_scores,
        ),
        _detail(
            "protein",
            "Proteína",
            protein_points,
            4,
            f"{protein_count} refeição(ões) com proteína"
            + (
                f"; {unknown_protein_count} resposta(s) neutra(s)"
                if unknown_protein_count
                else ""
            ),
        ),
        _detail(
            "produce",
            "Frutas ou verduras",
            produce_points,
            4,
            f"{produce_count} refeição(ões) com frutas ou verduras"
            + (
                f"; {unknown_produce_count} resposta(s) neutra(s)"
                if unknown_produce_count
                else ""
            ),
        ),
        _detail(
            "hydration",
            "Hidratação",
            hydration_points,
            3,
            f"{hydration_total} ml de uma meta de {target} ml",
        ),
        _detail(
            "conscious_record",
            "Registro consciente",
            1 if conscious else 0,
            1,
            "Refeição completa" if conscious else "Sem refeição completa",
        ),
    ]
    return _category_result("nutrition", True, breakdown)


def calculate_computer_score(
    summary: Mapping[str, Any] | None,
    distraction_limit_seconds: int | None = None,
) -> dict[str, Any]:
    summary = summary or {}
    productive = max(0, int(summary.get("productive_seconds") or 0))
    distracted = max(0, int(summary.get("distracted_seconds") or 0))
    classified_seconds = productive + distracted
    if classified_seconds <= 0:
        return _category_result("computer", False, [])

    productive_ratio = productive / classified_seconds * 100
    if productive_ratio < 25:
        productive_points = 0
    elif productive_ratio < 40:
        productive_points = 3
    elif productive_ratio < 55:
        productive_points = 5
    elif productive_ratio < 70:
        productive_points = 7
    elif productive_ratio < 85:
        productive_points = 9
    else:
        productive_points = 10

    limit = distraction_limit_seconds or int(
        summary.get("distraction_limit_seconds")
        or _configured_positive_int(
            "DEFAULT_DISTRACTION_LIMIT_SECONDS",
            DEFAULT_DISTRACTION_LIMIT_SECONDS,
        )
    )
    if limit <= 0:
        limit = _configured_positive_int(
            "DEFAULT_DISTRACTION_LIMIT_SECONDS",
            DEFAULT_DISTRACTION_LIMIT_SECONDS,
        )
    distraction_ratio = distracted / limit * 100 if limit else 0
    if distraction_ratio <= 100:
        distraction_points = 4
    elif distraction_ratio <= 125:
        distraction_points = 2
    elif distraction_ratio <= 150:
        distraction_points = 1
    else:
        distraction_points = 0

    sessions = max(0, int(summary.get("focused_sessions_count") or 0))
    session_points = 0 if sessions == 0 else 2 if sessions == 1 else 4
    classified_apps = max(
        0.0,
        min(float(summary.get("classified_apps_percentage") or 0), 100.0),
    )
    classification_points = 0 if classified_apps < 50 else 1 if classified_apps < 80 else 2

    breakdown = [
        _detail("productive_ratio", "Proporção produtiva", productive_points, 10, f"{_round_half_up(productive_ratio)}% do tempo classificado"),
        _detail("controlled_distraction", "Distração controlada", distraction_points, 4, f"{distracted}s de um limite de {limit}s"),
        _detail("focused_sessions", "Sessões focadas", session_points, 4, f"{sessions} sessão(ões)"),
        _detail("app_classification", "Classificação dos aplicativos", classification_points, 2, f"{_round_half_up(classified_apps)}% classificados"),
    ]
    return _category_result("computer", True, breakdown)


def calculate_session_bonus(sessions: Iterable[Any]) -> dict[str, Any]:
    sessions = list(sessions)
    session_details: list[dict[str, Any]] = []
    total = 0
    for index, session in enumerate(sessions, start=1):
        completed = getattr(session, "status", None) == "completed"
        completion_points = 2 if completed else 0
        focus_points = (
            1
            if completed
            and getattr(session, "focus_percentage", None) is not None
            and int(session.focus_percentage) >= 70
            else 0
        )
        objective_points = (
            1 if completed and _text_present(getattr(session, "result_text", None)) else 0
        )
        reflection_points = (
            1
            if completed
            and (
                _text_present(getattr(session, "learned_text", None))
                or _text_present(getattr(session, "difficulty_text", None))
                or getattr(session, "self_rating", None) is not None
            )
            else 0
        )
        score = _clamp(
            completion_points + focus_points + objective_points + reflection_points,
            0,
            5,
        )
        total += score
        session_details.append(
            {
                "index": index,
                "status": getattr(session, "status", None),
                "score": score,
                "max_score": 5,
                "breakdown": [
                    _detail("completed", "Sessão concluída", completion_points, 2, str(getattr(session, "status", "—"))),
                    _detail("focus", "Foco", focus_points, 1, f"{getattr(session, 'focus_percentage', None) if getattr(session, 'focus_percentage', None) is not None else '—'}%"),
                    _detail("objective", "Objetivo concluído", objective_points, 1, "Aproximação por resultado preenchido", approximate=True),
                    _detail("reflection", "Reflexão final", reflection_points, 1, "Aprendizado, dificuldade ou autoavaliação"),
                ],
            }
        )

    score = min(total, MAX_SESSION_BONUS)
    return {
        "category": "session_bonus",
        "evaluated": bool(sessions),
        "score": score,
        "max_score": MAX_SESSION_BONUS,
        "percentage": score * 10,
        "sessions": session_details,
        "message": (
            "Bônus diário limitado a 10 pontos."
            if total > MAX_SESSION_BONUS
            else "Bônus calculado pelas sessões concluídas."
        ),
        # TODO(v2): substituir result_text por um campo explícito de objetivo concluído.
        # A duração e os tempos produtivo/distraído não entram no bônus para evitar
        # dupla contagem com as categorias. source_session_id poderá relacionar os
        # registros futuramente sem alterar a regra de pontuação.
    }


def get_score_coverage(categories: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    evaluated = sum(bool(result.get("evaluated")) for result in categories.values())
    total = TOTAL_CATEGORIES
    return {
        "evaluated_categories": evaluated,
        "total_categories": total,
        "coverage_percentage": _round_half_up(evaluated / total * 100) if total else 0,
    }


def calculate_daily_score(
    reference_date: date,
    computer_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from app.models import (
        ComputerActivityBlock,
        HydrationRecord,
        MealRecord,
        SessionRecord,
        SleepRecord,
        StudyRecord,
        TrainingRecord,
    )
    study_records = list(
        db.session.scalars(
            db.select(StudyRecord).where(StudyRecord.record_date == reference_date)
        )
    )
    training_records = list(
        db.session.scalars(
            db.select(TrainingRecord).where(TrainingRecord.record_date == reference_date)
        )
    )
    weekly_training_records = list(
        db.session.scalars(
            db.select(TrainingRecord).where(
                TrainingRecord.record_date.between(
                    reference_date - timedelta(days=6),
                    reference_date,
                )
            )
        )
    )
    sleep_record = db.session.scalar(
        db.select(SleepRecord).where(SleepRecord.record_date == reference_date)
    )
    meals = list(
        db.session.scalars(
            db.select(MealRecord).where(MealRecord.record_date == reference_date)
        )
    )
    hydration = list(
        db.session.scalars(
            db.select(HydrationRecord).where(
                HydrationRecord.record_date == reference_date
            )
        )
    )
    sessions = list(
        db.session.scalars(
            db.select(SessionRecord).where(SessionRecord.record_date == reference_date)
        )
    )
    if computer_summary is None:
        from app.services.computer_service import summarize_blocks

        computer_blocks = list(
            db.session.scalars(
                db.select(ComputerActivityBlock).where(
                    ComputerActivityBlock.record_date == reference_date
                )
            )
        )
        computer_summary = summarize_blocks(
            computer_blocks,
            focused_sessions_count=sum(
                session.status == "completed"
                and session.related_category == "computer"
                for session in sessions
            ),
        )

    categories = {
        "study": calculate_study_score(study_records),
        "training": calculate_training_score(
            training_records,
            weekly_training_records,
        ),
        "sleep": calculate_sleep_score(sleep_record),
        "nutrition": calculate_nutrition_score(meals, hydration),
        "computer": calculate_computer_score(computer_summary),
    }
    coverage = get_score_coverage(categories)
    evaluated_results = [
        result for result in categories.values() if result["evaluated"]
    ]
    raw_base_score = min(
        sum(result["score"] for result in evaluated_results),
        MAX_BASE_SCORE,
    )
    raw_base_max = min(
        CATEGORY_MAX_SCORE * len(evaluated_results),
        MAX_BASE_SCORE,
    )
    normalized_base_score = (
        _clamp(raw_base_score / raw_base_max * 100, 0, MAX_BASE_SCORE)
        if raw_base_max
        else 0
    )
    session_bonus_detail = calculate_session_bonus(sessions)
    session_bonus = min(session_bonus_detail["score"], MAX_SESSION_BONUS)
    final_score = min(normalized_base_score + session_bonus, MAX_FINAL_SCORE)

    return {
        "date": reference_date.isoformat(),
        "categories": categories,
        "raw_base_score": raw_base_score,
        "raw_base_max": raw_base_max,
        "normalized_base_score": normalized_base_score,
        **coverage,
        "session_bonus": session_bonus,
        "session_bonus_detail": session_bonus_detail,
        "final_score": final_score,
        "max_final_score": MAX_FINAL_SCORE,
        "message": get_score_message(final_score),
        "day_closed": False,
        # TODO(v2): definir fechamento explícito do dia; categorias sem dados
        # permanecem não avaliadas até que essa regra seja implementada.
    }


# TODO(v2): prática sem questões exigirá um campo próprio no StudyRecord.
# TODO(v2): substituir a aproximação de conclusão do treino por aderência ao plano.
# TODO(v2): descanso planejado depende de planejamento semanal persistente.
