from datetime import date

from flask import Blueprint, jsonify, request

from app.services.record_service import (
    RecordConflictError,
    RecordNotFoundError,
    RecordPersistenceError,
    RecordValidationError,
    create_hydration_record,
    create_meal_record,
    create_sleep_record,
    create_study_record,
    create_training_record,
    complete_imported_sleep,
    complete_imported_training,
    delete_record,
    get_daily_record_counts,
    get_hydration_total_by_date,
    get_record_for_management,
    ignore_imported_suggestion,
    serialize_record,
    serialize_record_for_management,
    update_record,
)
from app.services.analytics_utils import get_local_today
from app.services.hydration_service import (
    create_quick_hydration as save_quick_hydration,
    get_today_hydration,
)
from app.services.watch_service import get_watch_suggestions


records_api = Blueprint("records_api", __name__, url_prefix="/api/records")


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise RecordValidationError(
            {"_schema": "Envie um objeto JSON válido."}
        )
    return payload


def _created_response(record):
    return (
        jsonify(
            {
                "success": True,
                "message": "Registro salvo com sucesso.",
                "record": serialize_record(record),
                "daily_counts": get_daily_record_counts(record.record_date),
            }
        ),
        201,
    )


def _create(factory):
    try:
        return _created_response(factory(_json_payload()))
    except RecordValidationError as exc:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Não foi possível salvar o registro.",
                    "errors": exc.errors,
                }
            ),
            400,
        )
    except RecordPersistenceError:
        return (
            jsonify(
                {
                    "success": False,
                    "message": (
                        "Não foi possível salvar o registro. "
                        "Tente novamente."
                    ),
                    "errors": {},
                }
            ),
            500,
        )


@records_api.post("/study")
def create_study():
    return _create(create_study_record)


@records_api.post("/sleep")
def create_sleep():
    return _create(create_sleep_record)


@records_api.post("/training")
def create_training():
    return _create(create_training_record)


@records_api.post("/meal")
def create_meal():
    return _create(create_meal_record)


@records_api.post("/hydration")
def create_hydration():
    return _create(create_hydration_record)


@records_api.post("/hydration/quick")
def create_quick_hydration():
    try:
        record, summary = save_quick_hydration(request.get_json(silent=True))
        return jsonify(
            success=True,
            message=f"{record.amount_ml} ml registrados",
            record=serialize_record(record),
            **summary,
        ), 201
    except RecordValidationError as exc:
        return jsonify(
            success=False,
            message=next(iter(exc.errors.values())),
            errors=exc.errors,
        ), 400
    except RecordPersistenceError:
        return jsonify(
            success=False,
            message="Não foi possível registrar a hidratação.",
            errors={},
        ), 500


@records_api.get("/hydration/today")
def hydration_today():
    return jsonify(success=True, **get_today_hydration())


@records_api.get("/watch/<kind>")
def watch_suggestions(kind: str):
    if kind not in {"training", "sleep"}:
        return jsonify(success=False, message="Tipo inválido.", records=[]), 404
    return jsonify(success=True, records=get_watch_suggestions(kind))


@records_api.patch("/watch/training/<int:record_id>")
def complete_watch_training(record_id: int):
    try:
        record = complete_imported_training(record_id, _json_payload())
        return jsonify(
            success=True,
            message="Treino do relógio complementado sem duplicação.",
            record=serialize_record(record),
            daily_counts=get_daily_record_counts(record.record_date),
        )
    except (
        RecordValidationError,
        RecordNotFoundError,
        RecordPersistenceError,
    ) as exc:
        return _management_error(exc)


@records_api.patch("/watch/sleep/<int:record_id>")
def complete_watch_sleep(record_id: int):
    try:
        record = complete_imported_sleep(record_id, _json_payload())
        return jsonify(
            success=True,
            message="Sono do relógio complementado sem duplicação.",
            record=serialize_record(record),
            daily_counts=get_daily_record_counts(record.record_date),
        )
    except (
        RecordValidationError,
        RecordNotFoundError,
        RecordPersistenceError,
    ) as exc:
        return _management_error(exc)


@records_api.post("/watch/<kind>/<int:record_id>/ignore")
def ignore_watch_suggestion(kind: str, record_id: int):
    try:
        ignore_imported_suggestion(kind, record_id)
        return jsonify(success=True, message="Sugestão ignorada.")
    except (
        RecordValidationError,
        RecordNotFoundError,
        RecordPersistenceError,
    ) as exc:
        return _management_error(exc)


@records_api.get("/counts")
def daily_counts():
    raw_date = request.args.get("date")
    try:
        record_date = date.fromisoformat(raw_date) if raw_date else get_local_today()
    except ValueError:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Data inválida.",
                    "errors": {"date": "Use o formato AAAA-MM-DD."},
                }
            ),
            400,
        )
    return jsonify(
        {
            "success": True,
            "record_date": record_date.isoformat(),
            "counts": get_daily_record_counts(record_date),
        }
    )


def _management_error(exc):
    if isinstance(exc, RecordConflictError):
        return jsonify(
            success=False,
            message=next(iter(exc.errors.values()), "Conflito ao salvar registro."),
            errors=exc.errors,
        ), 409
    if isinstance(exc, RecordValidationError):
        return jsonify(
            success=False,
            message="Revise os dados informados.",
            errors=exc.errors,
        ), 400
    if isinstance(exc, RecordNotFoundError):
        return jsonify(success=False, message=str(exc), errors={}), 404
    return jsonify(
        success=False,
        message="Não foi possível concluir a ação. Tente novamente.",
        errors={},
    ), 500


@records_api.get("/<record_type>/<int:record_id>")
def record_detail(record_type: str, record_id: int):
    try:
        record = get_record_for_management(record_type, record_id)
        return jsonify(
            success=True,
            record=serialize_record_for_management(record),
        )
    except (
        RecordValidationError,
        RecordNotFoundError,
        RecordPersistenceError,
    ) as exc:
        return _management_error(exc)


@records_api.patch("/<record_type>/<int:record_id>")
def edit_record(record_type: str, record_id: int):
    if record_type == "session":
        return jsonify(
            success=False,
            message="Sessões são somente leitura nesta etapa.",
            errors={"record_type": "Edição de sessão não permitida."},
        ), 403
    try:
        record = update_record(record_type, record_id, _json_payload())
        return jsonify(
            success=True,
            message=(
                "Registro atualizado. "
                "A pontuação será recalculada automaticamente."
            ),
            record=serialize_record_for_management(record),
            daily_counts=get_daily_record_counts(record.record_date),
        )
    except (
        RecordConflictError,
        RecordValidationError,
        RecordNotFoundError,
        RecordPersistenceError,
    ) as exc:
        return _management_error(exc)


@records_api.delete("/<record_type>/<int:record_id>")
def remove_record(record_type: str, record_id: int):
    if record_type == "session":
        return jsonify(
            success=False,
            message="Sessões não podem ser excluídas nesta etapa.",
            errors={"record_type": "Exclusão de sessão não permitida."},
        ), 403
    try:
        record = get_record_for_management(record_type, record_id)
        record_date = record.record_date
        delete_record(record_type, record_id)
        return jsonify(
            success=True,
            message=(
                "Registro excluído. "
                "A pontuação será recalculada automaticamente."
            ),
            daily_counts=get_daily_record_counts(record_date),
        )
    except (
        RecordValidationError,
        RecordNotFoundError,
        RecordPersistenceError,
    ) as exc:
        return _management_error(exc)
