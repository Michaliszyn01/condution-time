from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models import (
    HydrationRecord,
    MealRecord,
    SessionRecord,
    SleepRecord,
    StudyRecord,
    TrainingRecord,
)
from app.services.analytics_utils import get_local_today
from app.services.catalog_service import manual_training_options


FOCUS_QUALITY = {
    "Baixa": "low",
    "Regular": "regular",
    "Boa": "good",
    "Muito boa": "very_good",
    "Excelente": "excellent",
}
STUDY_ORIGIN = {
    "Sessão monitorada": "monitored_session",
    "Estudo manual": "manual",
    "Outro": "other",
}
SLEEP_QUALITY = {
    "Péssima": "terrible",
    "Ruim": "bad",
    "Regular": "regular",
    "Boa": "good",
    "Excelente": "excellent",
}
RESTORED_OPTIONS = {
    "Sim": "yes",
    "Parcialmente": "partially",
    "Não": "no",
}
TRAINING_TYPES = {
    "Musculação": "strength",
    "Corrida": "running",
    "Caminhada": "walking",
    "Natação": "swimming",
    "Ciclismo": "cycling",
    "Esporte": "sport",
    "Mobilidade": "mobility",
    "Outro": "other",
}
TRAINING_TYPES.update(
    {
        item["label"]: item["value"]
        for item in manual_training_options()
    }
)
TRAINING_TYPES.update(
    {
        item["value"]: item["value"]
        for item in manual_training_options()
    }
)
PERFORMANCE_OPTIONS = {
    "Ruim": "bad",
    "Regular": "regular",
    "Bom": "good",
    "Muito bom": "very_good",
    "Excelente": "excellent",
}
DISCOMFORT_OPTIONS = {
    "Nenhum": "none",
    "Leve": "mild",
    "Moderado": "moderate",
    "Forte": "strong",
}
MEAL_TYPES = {
    "Café da manhã": "breakfast",
    "Almoço": "lunch",
    "Lanche": "snack",
    "Jantar": "dinner",
    "Ceia": "supper",
    "Outra": "other",
}
TRINARY_OPTIONS = {
    "Sim": "yes",
    "Não": "no",
    "Não sei": "unknown",
}
MEAL_QUALITY = {
    "Muito ruim": "very_bad",
    "Ruim": "bad",
    "Regular": "regular",
    "Boa": "good",
    "Excelente": "excellent",
}


class RecordValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Dados inválidos.")
        self.errors = errors


class RecordPersistenceError(RuntimeError):
    pass


class RecordConflictError(RecordValidationError):
    pass


class RecordNotFoundError(LookupError):
    pass


def _reject_unknown_fields(data: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise RecordValidationError(
            {"_schema": f"Campos não reconhecidos: {', '.join(unknown)}."}
        )


def _text(
    data: dict[str, Any],
    field: str,
    *,
    required: bool = False,
    max_length: int = 500,
) -> str | None:
    raw = data.get(field)
    if raw is not None and not isinstance(raw, str):
        raise RecordValidationError({field: "Informe um texto válido."})
    value = " ".join(str(raw).split()) if raw is not None else ""
    if required and not value:
        raise RecordValidationError({field: "Este campo é obrigatório."})
    if len(value) > max_length:
        raise RecordValidationError(
            {field: f"Use no máximo {max_length} caracteres."}
        )
    return value or None


def _long_text(
    data: dict[str, Any],
    field: str,
    *,
    required: bool = False,
    max_length: int = 2000,
) -> str | None:
    raw = data.get(field)
    if raw is not None and not isinstance(raw, str):
        raise RecordValidationError({field: "Informe um texto válido."})
    value = str(raw).strip() if raw is not None else ""
    if required and not value:
        raise RecordValidationError({field: "Este campo é obrigatório."})
    if len(value) > max_length:
        raise RecordValidationError(
            {field: f"Use no máximo {max_length} caracteres."}
        )
    return value or None


def _integer(
    data: dict[str, Any],
    field: str,
    *,
    required: bool = False,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    raw = data.get(field)
    if raw in (None, ""):
        if required:
            raise RecordValidationError({field: "Este campo é obrigatório."})
        return None
    if isinstance(raw, bool):
        raise RecordValidationError({field: "Informe um número inteiro válido."})
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise RecordValidationError(
            {field: "Informe um número inteiro válido."}
        ) from None
    if minimum is not None and value < minimum:
        raise RecordValidationError(
            {field: f"O valor mínimo permitido é {minimum}."}
        )
    if maximum is not None and value > maximum:
        raise RecordValidationError(
            {field: f"O valor máximo permitido é {maximum}."}
        )
    return value


def _record_date(data: dict[str, Any]) -> date:
    raw = data.get("record_date")
    if raw in (None, ""):
        return get_local_today()
    try:
        value = date.fromisoformat(str(raw))
    except ValueError:
        raise RecordValidationError(
            {"record_date": "Informe uma data válida."}
        ) from None
    if value > get_local_today():
        raise RecordValidationError(
            {"record_date": "Não é permitido registrar uma data futura."}
        )
    return value


def _time(data: dict[str, Any], field: str) -> time:
    raw = data.get(field)
    if raw in (None, ""):
        raise RecordValidationError({field: "Este campo é obrigatório."})
    try:
        parsed = time.fromisoformat(str(raw))
    except ValueError:
        raise RecordValidationError({field: "Informe um horário válido."}) from None
    return parsed.replace(second=0, microsecond=0)


def _enum(
    data: dict[str, Any],
    field: str,
    choices: dict[str, str],
) -> str:
    raw = data.get(field)
    if not isinstance(raw, str) or raw not in choices:
        raise RecordValidationError({field: "Selecione uma opção válida."})
    return choices[raw]


def _commit(record: db.Model, *, duplicate_sleep: bool = False) -> db.Model:
    try:
        db.session.add(record)
        db.session.commit()
        db.session.refresh(record)
        return record
    except IntegrityError as exc:
        db.session.rollback()
        if duplicate_sleep:
            raise RecordValidationError(
                {"record_date": "Já existe um registro de sono para esta data."}
            ) from exc
        current_app.logger.exception("Falha de integridade ao salvar registro")
        raise RecordPersistenceError("Não foi possível salvar o registro.") from exc
    except SQLAlchemyError as exc:
        db.session.rollback()
        current_app.logger.exception("Falha ao salvar registro")
        raise RecordPersistenceError("Não foi possível salvar o registro.") from exc


def _study_values(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
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
    }
    _reject_unknown_fields(data, allowed)
    duration = _integer(data, "duration_minutes", required=True, minimum=1)
    questions = _integer(data, "questions_count", minimum=0)
    correct = _integer(data, "correct_answers", minimum=0)
    if correct is not None and questions is None:
        raise RecordValidationError(
            {"questions_count": "Informe a quantidade de questões."}
        )
    if correct is not None and questions is not None and correct > questions:
        raise RecordValidationError(
            {
                "correct_answers": (
                    "Os acertos não podem superar a quantidade de questões."
                )
            }
        )

    return {
        "record_date": _record_date(data),
        "subject": _text(data, "subject", required=True, max_length=80),
        "topic": _text(data, "topic", required=True, max_length=150),
        "duration_minutes": duration,
        "questions_count": questions,
        "correct_answers": correct,
        "focus_quality": _enum(data, "focus_quality", FOCUS_QUALITY),
        "learned_text": _long_text(data, "learned_text"),
        "difficulty_text": _long_text(data, "difficulty_text"),
        "record_origin": _enum(data, "record_origin", STUDY_ORIGIN),
    }


def create_study_record(data: dict[str, Any]) -> StudyRecord:
    return _commit(StudyRecord(**_study_values(data)))


def calculate_sleep_duration(sleep_start: time, sleep_end: time) -> int:
    start_minutes = sleep_start.hour * 60 + sleep_start.minute
    end_minutes = sleep_end.hour * 60 + sleep_end.minute
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60
    return end_minutes - start_minutes


def _sleep_values(
    data: dict[str, Any],
    *,
    existing_id: int | None = None,
) -> dict[str, Any]:
    allowed = {
        "record_date",
        "sleep_start",
        "sleep_end",
        "perceived_quality",
        "awakenings_count",
        "woke_restored",
        "notes",
        "record_origin",
    }
    _reject_unknown_fields(data, allowed)
    record_date = _record_date(data)
    existing_query = db.select(SleepRecord.id).where(
        SleepRecord.record_date == record_date,
        SleepRecord.is_primary.is_(True),
    )
    if existing_id is not None:
        existing_query = existing_query.where(SleepRecord.id != existing_id)
    existing = db.session.scalar(existing_query)
    if existing is not None:
        raise RecordConflictError(
            {"record_date": "Já existe um registro de sono para esta data."}
        )

    sleep_start = _time(data, "sleep_start")
    sleep_end = _time(data, "sleep_end")
    origin = data.get("record_origin", "Manual")
    if origin != "Manual":
        raise RecordValidationError(
            {"record_origin": "A origem deve ser manual nesta etapa."}
        )

    return {
        "record_date": record_date,
        "sleep_start": sleep_start,
        "sleep_end": sleep_end,
        "duration_minutes": calculate_sleep_duration(sleep_start, sleep_end),
        "perceived_quality": _enum(data, "perceived_quality", SLEEP_QUALITY),
        "awakenings_count": _integer(
            data,
            "awakenings_count",
            required=True,
            minimum=0,
        ),
        "woke_restored": _enum(data, "woke_restored", RESTORED_OPTIONS),
        "notes": _long_text(data, "notes"),
        "record_origin": "manual",
        "is_primary": True,
        "suggestion_status": "completed",
    }


def create_sleep_record(data: dict[str, Any]) -> SleepRecord:
    return _commit(SleepRecord(**_sleep_values(data)), duplicate_sleep=True)


def _training_values(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "record_date",
        "training_type",
        "activity_name",
        "duration_minutes",
        "intensity",
        "perceived_performance",
        "exercises_text",
        "discomfort_level",
        "discomfort_location",
        "notes",
    }
    _reject_unknown_fields(data, allowed)
    discomfort = _enum(data, "discomfort_level", DISCOMFORT_OPTIONS)
    location = _text(data, "discomfort_location", max_length=150)
    if discomfort != "none" and not location:
        raise RecordValidationError(
            {
                "discomfort_location": (
                    "Informe onde sentiu o desconforto."
                )
            }
        )

    return {
        "record_date": _record_date(data),
        "training_type": _enum(data, "training_type", TRAINING_TYPES),
        "activity_name": _text(
            data,
            "activity_name",
            required=True,
            max_length=150,
        ),
        "duration_minutes": _integer(
            data,
            "duration_minutes",
            required=True,
            minimum=1,
        ),
        "intensity": _integer(
            data,
            "intensity",
            required=True,
            minimum=1,
            maximum=10,
        ),
        "perceived_performance": _enum(
            data,
            "perceived_performance",
            PERFORMANCE_OPTIONS,
        ),
        "exercises_text": _long_text(data, "exercises_text"),
        "discomfort_level": discomfort,
        "discomfort_location": location,
        "notes": _long_text(data, "notes"),
        "record_origin": "manual",
        "suggestion_status": "completed",
    }


def create_training_record(data: dict[str, Any]) -> TrainingRecord:
    return _commit(TrainingRecord(**_training_values(data)))


def complete_imported_training(
    record_id: int,
    data: dict[str, Any],
) -> TrainingRecord:
    allowed = {
        "training_type",
        "intensity",
        "perceived_performance",
        "exercises_text",
        "discomfort_level",
        "discomfort_location",
        "notes",
    }
    _reject_unknown_fields(data, allowed)
    record = db.session.get(TrainingRecord, record_id)
    if record is None or not record.source_record_id:
        raise RecordNotFoundError("Treino importado não encontrado.")
    discomfort = _enum(data, "discomfort_level", DISCOMFORT_OPTIONS)
    location = _text(data, "discomfort_location", max_length=150)
    if discomfort != "none" and not location:
        raise RecordValidationError(
            {"discomfort_location": "Informe onde sentiu o desconforto."}
        )
    selected_training_type = data.get("training_type")
    if selected_training_type:
        record.manual_training_type = _enum(
            data,
            "training_type",
            TRAINING_TYPES,
        )
        record.training_type = record.manual_training_type
        record.activity_name = _label(
            TRAINING_TYPES,
            record.manual_training_type,
        )
    record.intensity = _integer(
        data,
        "intensity",
        required=True,
        minimum=1,
        maximum=10,
    )
    record.perceived_performance = _enum(
        data,
        "perceived_performance",
        PERFORMANCE_OPTIONS,
    )
    record.exercises_text = _long_text(data, "exercises_text")
    record.discomfort_level = discomfort
    record.discomfort_location = location
    record.notes = _long_text(data, "notes")
    record.record_origin = "merged"
    record.suggestion_status = "completed"
    return _commit(record)


def complete_imported_sleep(
    record_id: int,
    data: dict[str, Any],
) -> SleepRecord:
    allowed = {"perceived_quality", "woke_restored", "notes"}
    _reject_unknown_fields(data, allowed)
    record = db.session.get(SleepRecord, record_id)
    if record is None or not record.source_record_id:
        raise RecordNotFoundError("Sono importado não encontrado.")
    record.perceived_quality = _enum(
        data,
        "perceived_quality",
        SLEEP_QUALITY,
    )
    record.woke_restored = _enum(data, "woke_restored", RESTORED_OPTIONS)
    record.notes = _long_text(data, "notes")
    record.record_origin = "merged"
    record.suggestion_status = "completed"
    return _commit(record)


def ignore_imported_suggestion(record_type: str, record_id: int) -> db.Model:
    model = {"training": TrainingRecord, "sleep": SleepRecord}.get(record_type)
    if model is None:
        raise RecordValidationError({"record_type": "Tipo de sugestão inválido."})
    record = db.session.get(model, record_id)
    if record is None or not record.source_record_id:
        raise RecordNotFoundError("Sugestão importada não encontrada.")
    record.suggestion_status = "ignored"
    return _commit(record)


def _meal_values(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "record_date",
        "meal_type",
        "meal_time",
        "foods_text",
        "approximate_amount",
        "has_protein",
        "has_fruits_or_vegetables",
        "perceived_quality",
        "notes",
    }
    _reject_unknown_fields(data, allowed)
    return {
        "record_date": _record_date(data),
        "meal_type": _enum(data, "meal_type", MEAL_TYPES),
        "meal_time": _time(data, "meal_time"),
        "foods_text": _long_text(data, "foods_text", required=True),
        "approximate_amount": _text(data, "approximate_amount", max_length=500),
        "has_protein": _enum(data, "has_protein", TRINARY_OPTIONS),
        "has_fruits_or_vegetables": _enum(
            data,
            "has_fruits_or_vegetables",
            TRINARY_OPTIONS,
        ),
        "perceived_quality": _enum(data, "perceived_quality", MEAL_QUALITY),
        "notes": _long_text(data, "notes"),
    }


def create_meal_record(data: dict[str, Any]) -> MealRecord:
    return _commit(MealRecord(**_meal_values(data)))


def _hydration_values(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "record_date",
        "amount",
        "unit",
        "consumed_at",
        "notes",
    }
    _reject_unknown_fields(data, allowed)
    raw_amount = data.get("amount")
    try:
        amount = Decimal(str(raw_amount))
    except (InvalidOperation, TypeError, ValueError):
        raise RecordValidationError(
            {"amount": "Informe uma quantidade válida."}
        ) from None
    if amount <= 0:
        raise RecordValidationError(
            {"amount": "A quantidade deve ser maior que zero."}
        )
    unit = data.get("unit")
    if unit not in {"ml", "L"}:
        raise RecordValidationError({"unit": "Selecione uma unidade válida."})
    amount_ml = amount * (1000 if unit == "L" else 1)
    amount_ml_int = int(amount_ml.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if amount_ml_int <= 0 or amount_ml_int > 20_000:
        raise RecordValidationError(
            {"amount": "Informe uma quantidade entre 1 e 20.000 ml."}
        )

    return {
        "record_date": _record_date(data),
        "amount_ml": amount_ml_int,
        "consumed_at": _time(data, "consumed_at"),
        "notes": _long_text(data, "notes"),
    }


def create_hydration_record(data: dict[str, Any]) -> HydrationRecord:
    return _commit(HydrationRecord(**_hydration_values(data)))


EDITABLE_RECORD_TYPES = {
    "study": StudyRecord,
    "training": TrainingRecord,
    "sleep": SleepRecord,
    "meal": MealRecord,
    "hydration": HydrationRecord,
}
ALL_RECORD_TYPES = {**EDITABLE_RECORD_TYPES, "session": SessionRecord}
VALUE_BUILDERS = {
    "study": _study_values,
    "training": _training_values,
    "meal": _meal_values,
    "hydration": _hydration_values,
}


def get_record_for_management(record_type: str, record_id: int) -> db.Model:
    model = ALL_RECORD_TYPES.get(record_type)
    if model is None:
        raise RecordValidationError({"record_type": "Tipo de registro inválido."})
    record = db.session.get(model, record_id)
    if record is None:
        raise RecordNotFoundError("Registro não encontrado.")
    return record


def update_record(
    record_type: str,
    record_id: int,
    data: dict[str, Any],
) -> db.Model:
    if record_type == "session":
        raise RecordValidationError(
            {"record_type": "Sessões são somente leitura nesta etapa."}
        )
    record = get_record_for_management(record_type, record_id)
    if record_type == "sleep":
        values = _sleep_values(data, existing_id=record_id)
    else:
        builder = VALUE_BUILDERS.get(record_type)
        if builder is None:
            raise RecordValidationError(
                {"record_type": "Tipo de registro inválido."}
            )
        values = builder(data)
    if (
        record_type in {"training", "sleep"}
        and getattr(record, "source_record_id", None)
    ):
        values["record_origin"] = "merged"
        values["suggestion_status"] = "completed"
    for field, value in values.items():
        setattr(record, field, value)
    return _commit(record, duplicate_sleep=record_type == "sleep")


def delete_record(record_type: str, record_id: int) -> None:
    if record_type == "session":
        raise RecordValidationError(
            {"record_type": "Sessões não podem ser excluídas nesta etapa."}
        )
    record = get_record_for_management(record_type, record_id)
    try:
        db.session.delete(record)
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        current_app.logger.exception("Falha ao excluir registro")
        raise RecordPersistenceError("Não foi possível excluir o registro.") from exc


def _label(mapping: dict[str, str], stored: str | None) -> str | None:
    return next((label for label, value in mapping.items() if value == stored), stored)


def _iso_time(value: time | None) -> str | None:
    return value.isoformat(timespec="minutes") if value else None


def serialize_record_for_management(record: db.Model) -> dict[str, Any]:
    base = {
        "id": record.id,
        "record_date": record.record_date.isoformat(),
        "created_at": record.created_at.isoformat(),
        "editable": not isinstance(record, SessionRecord),
        "deletable": not isinstance(record, SessionRecord),
    }
    details: list[dict[str, str]] = []
    data: dict[str, Any]
    title: str

    if isinstance(record, StudyRecord):
        accuracy = (
            round((record.correct_answers or 0) / record.questions_count * 100)
            if record.questions_count
            else None
        )
        title = f"{record.subject} — {record.topic}"
        data = {
            "record_date": base["record_date"],
            "subject": record.subject,
            "topic": record.topic,
            "duration_minutes": record.duration_minutes,
            "questions_count": record.questions_count,
            "correct_answers": record.correct_answers,
            "focus_quality": _label(FOCUS_QUALITY, record.focus_quality),
            "learned_text": record.learned_text,
            "difficulty_text": record.difficulty_text,
            "record_origin": _label(STUDY_ORIGIN, record.record_origin),
        }
        details = [
            {"label": "Matéria", "value": record.subject},
            {"label": "Assunto", "value": record.topic},
            {"label": "Duração", "value": f"{record.duration_minutes} min"},
            {"label": "Questões", "value": str(record.questions_count or "—")},
            {"label": "Acertos", "value": str(record.correct_answers or "—")},
            {"label": "Percentual de acertos", "value": f"{accuracy}%" if accuracy is not None else "—"},
            {"label": "Qualidade do foco", "value": str(data["focus_quality"])},
            {"label": "O que aprendeu", "value": record.learned_text or "—"},
            {"label": "Dificuldade encontrada", "value": record.difficulty_text or "—"},
            {"label": "Origem do registro", "value": str(data["record_origin"])},
        ]
        record_type = "study"
    elif isinstance(record, TrainingRecord):
        title = record.activity_name
        data = {
            "record_date": base["record_date"],
            "training_type": _label(TRAINING_TYPES, record.training_type),
            "activity_name": record.activity_name,
            "duration_minutes": record.duration_minutes,
            "intensity": record.intensity,
            "perceived_performance": _label(PERFORMANCE_OPTIONS, record.perceived_performance),
            "exercises_text": record.exercises_text,
            "discomfort_level": _label(DISCOMFORT_OPTIONS, record.discomfort_level),
            "discomfort_location": record.discomfort_location,
            "notes": record.notes,
        }
        details = [
            {"label": "Tipo de treino", "value": str(data["training_type"])},
            {"label": "Atividade", "value": record.activity_name},
            {"label": "Duração", "value": f"{record.duration_minutes} min"},
            {
                "label": "Intensidade",
                "value": (
                    f"{record.intensity}/10"
                    if record.intensity is not None
                    else "Não informada"
                ),
            },
            {"label": "Desempenho percebido", "value": str(data["perceived_performance"])},
            {"label": "Exercícios", "value": record.exercises_text or "—"},
            {"label": "Desconforto", "value": str(data["discomfort_level"])},
            {"label": "Local do desconforto", "value": record.discomfort_location or "—"},
            {"label": "Observações", "value": record.notes or "—"},
        ]
        record_type = "training"
    elif isinstance(record, SleepRecord):
        title = "Registro de sono"
        data = {
            "record_date": base["record_date"],
            "sleep_start": _iso_time(record.sleep_start),
            "sleep_end": _iso_time(record.sleep_end),
            "perceived_quality": _label(SLEEP_QUALITY, record.perceived_quality),
            "awakenings_count": record.awakenings_count,
            "woke_restored": _label(RESTORED_OPTIONS, record.woke_restored),
            "notes": record.notes,
            "record_origin": "Manual",
        }
        details = [
            {"label": "Data de referência", "value": base["record_date"]},
            {"label": "Horário em que dormiu", "value": str(data["sleep_start"])},
            {"label": "Horário em que acordou", "value": str(data["sleep_end"])},
            {"label": "Duração calculada", "value": f"{record.duration_minutes} min"},
            {"label": "Qualidade percebida", "value": str(data["perceived_quality"])},
            {"label": "Interrupções", "value": str(record.awakenings_count)},
            {"label": "Acordou descansado", "value": str(data["woke_restored"])},
            {"label": "Origem do registro", "value": "Manual"},
            {"label": "Observações", "value": record.notes or "—"},
        ]
        record_type = "sleep"
    elif isinstance(record, MealRecord):
        title = str(_label(MEAL_TYPES, record.meal_type))
        data = {
            "record_date": base["record_date"],
            "meal_type": title,
            "meal_time": _iso_time(record.meal_time),
            "foods_text": record.foods_text,
            "approximate_amount": record.approximate_amount,
            "has_protein": _label(TRINARY_OPTIONS, record.has_protein),
            "has_fruits_or_vegetables": _label(TRINARY_OPTIONS, record.has_fruits_or_vegetables),
            "perceived_quality": _label(MEAL_QUALITY, record.perceived_quality),
            "notes": record.notes,
        }
        details = [
            {"label": "Tipo de refeição", "value": title},
            {"label": "Horário", "value": str(data["meal_time"])},
            {"label": "Alimentos", "value": record.foods_text},
            {"label": "Quantidade aproximada", "value": record.approximate_amount or "—"},
            {"label": "Proteína", "value": str(data["has_protein"])},
            {"label": "Frutas ou verduras", "value": str(data["has_fruits_or_vegetables"])},
            {"label": "Qualidade percebida", "value": str(data["perceived_quality"])},
            {"label": "Observações", "value": record.notes or "—"},
        ]
        record_type = "meal"
    elif isinstance(record, HydrationRecord):
        title = "Hidratação"
        data = {
            "record_date": base["record_date"],
            "amount": record.amount_ml,
            "unit": "ml",
            "consumed_at": _iso_time(record.consumed_at),
            "notes": record.notes,
        }
        litres = f"{record.amount_ml / 1000:g} L" if record.amount_ml >= 1000 else "—"
        details = [
            {"label": "Quantidade", "value": f"{record.amount_ml} ml"},
            {"label": "Em litros", "value": litres},
            {"label": "Horário", "value": str(data["consumed_at"])},
            {"label": "Observações", "value": record.notes or "—"},
        ]
        record_type = "hydration"
    elif isinstance(record, SessionRecord):
        from app.services.scoring_service import calculate_session_bonus

        title = record.title
        bonus = calculate_session_bonus([record])["sessions"][0]["score"]
        data = {}
        details = [
            {"label": "Tipo", "value": record.session_type},
            {"label": "Título", "value": record.title},
            {"label": "Categoria relacionada", "value": record.related_category},
            {"label": "Meta de duração", "value": f"{record.target_duration_minutes or 0} min"},
            {"label": "Duração real", "value": f"{int(record.actual_duration_seconds or 0) // 60} min"},
            {"label": "Status", "value": record.status},
            {"label": "Objetivo", "value": record.objective_text or "—"},
            {"label": "Resultado", "value": record.result_text or "—"},
            {"label": "Aprendizado", "value": record.learned_text or "—"},
            {"label": "Dificuldade", "value": record.difficulty_text or "—"},
            {"label": "Autoavaliação", "value": str(record.self_rating or "—")},
            {"label": "Foco", "value": f"{record.focus_percentage}%" if record.focus_percentage is not None else "—"},
            {"label": "Bônus oficial", "value": f"+{bonus} pts" if record.status == "completed" else "Sem bônus"},
            {"label": "Início", "value": record.started_at.isoformat() if record.started_at else "—"},
            {"label": "Conclusão", "value": record.finished_at.isoformat() if record.finished_at else "—"},
        ]
        record_type = "session"
    else:
        raise RecordValidationError({"record_type": "Tipo de registro inválido."})

    details.extend(
        [
            {"label": "Data", "value": base["record_date"]},
            {"label": "Horário de criação", "value": base["created_at"]},
        ]
    )
    return {
        **base,
        "record_type": record_type,
        "title": title,
        "data": data,
        "details": details,
    }


def get_study_records_by_date(record_date: date) -> list[StudyRecord]:
    return list(
        db.session.scalars(
            db.select(StudyRecord)
            .where(StudyRecord.record_date == record_date)
            .order_by(StudyRecord.created_at.desc())
        )
    )


def get_sleep_record_by_date(record_date: date) -> SleepRecord | None:
    return db.session.scalar(
        db.select(SleepRecord).where(SleepRecord.record_date == record_date)
    )


def get_training_records_by_date(record_date: date) -> list[TrainingRecord]:
    return list(
        db.session.scalars(
            db.select(TrainingRecord)
            .where(TrainingRecord.record_date == record_date)
            .order_by(TrainingRecord.created_at.desc())
        )
    )


def get_meals_by_date(record_date: date) -> list[MealRecord]:
    return list(
        db.session.scalars(
            db.select(MealRecord)
            .where(MealRecord.record_date == record_date)
            .order_by(MealRecord.meal_time.desc())
        )
    )


def get_hydration_total_by_date(record_date: date) -> int:
    total = db.session.scalar(
        db.select(func.coalesce(func.sum(HydrationRecord.amount_ml), 0)).where(
            HydrationRecord.record_date == record_date
        )
    )
    return int(total or 0)


def get_records_by_interval(
    model: type[db.Model],
    start_date: date,
    end_date: date,
) -> list[db.Model]:
    if end_date < start_date:
        raise ValueError("A data final deve ser igual ou posterior à inicial.")
    return list(
        db.session.scalars(
            db.select(model)
            .where(model.record_date.between(start_date, end_date))
            .order_by(model.record_date.desc(), model.created_at.desc())
        )
    )


def get_records_last_7_days(
    model: type[db.Model],
    reference_date: date | None = None,
) -> list[db.Model]:
    end_date = reference_date or date.today()
    return get_records_by_interval(model, end_date - timedelta(days=6), end_date)


def get_daily_record_counts(record_date: date) -> dict[str, int]:
    def count(model: type[db.Model]) -> int:
        return int(
            db.session.scalar(
                db.select(func.count(model.id)).where(
                    model.record_date == record_date
                )
            )
            or 0
        )

    meal_count = count(MealRecord)
    hydration_count = count(HydrationRecord)
    return {
        "study": count(StudyRecord),
        "sleep": count(SleepRecord),
        "training": count(TrainingRecord),
        "meal": meal_count,
        "hydration": hydration_count,
        "nutrition": meal_count + hydration_count,
    }


def serialize_record(record: db.Model) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": record.id,
        "record_date": record.record_date.isoformat(),
        "created_at": record.created_at.isoformat(),
    }
    if isinstance(record, StudyRecord):
        payload.update(
            {
                "category": "study",
                "subject": record.subject,
                "topic": record.topic,
                "duration_minutes": record.duration_minutes,
            }
        )
    elif isinstance(record, SleepRecord):
        payload.update(
            {
                "category": "sleep",
                "duration_minutes": record.duration_minutes,
                "perceived_quality": record.perceived_quality,
            }
        )
    elif isinstance(record, TrainingRecord):
        payload.update(
            {
                "category": "training",
                "activity_name": record.activity_name,
                "duration_minutes": record.duration_minutes,
                "intensity": record.intensity,
            }
        )
    elif isinstance(record, MealRecord):
        payload.update(
            {
                "category": "meal",
                "meal_type": record.meal_type,
                "meal_time": record.meal_time.isoformat(timespec="minutes"),
            }
        )
    elif isinstance(record, HydrationRecord):
        payload.update(
            {
                "category": "hydration",
                "amount_ml": record.amount_ml,
                "consumed_at": record.consumed_at.isoformat(timespec="minutes"),
            }
        )
    return payload
