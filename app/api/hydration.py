from flask import Blueprint, jsonify, request

from app.services.hydration_service import (
    create_quick_hydration,
    get_today_hydration,
)
from app.services.record_service import (
    RecordPersistenceError,
    RecordValidationError,
    serialize_record,
)


hydration_api = Blueprint(
    "hydration_api",
    __name__,
    url_prefix="/api/hydration",
)


@hydration_api.get("/today")
def today():
    return jsonify(success=True, **get_today_hydration())


@hydration_api.post("/quick")
def quick():
    try:
        record, summary = create_quick_hydration(request.get_json(silent=True))
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
