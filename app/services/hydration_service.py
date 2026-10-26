from __future__ import annotations

from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models import HydrationRecord, UserProfile
from app.services.analytics_utils import get_app_timezone, get_local_today
from app.services.record_service import (
    RecordValidationError,
    create_hydration_record,
)

_PROFILE_UNSET = object()


def get_hydration_goal_ml(
    profile: UserProfile | None | object = _PROFILE_UNSET,
) -> int:
    if profile is _PROFILE_UNSET:
        profile = db.session.scalar(db.select(UserProfile).limit(1))
    configured = profile.hydration_target_ml if profile else None
    return int(
        configured
        or current_app.config.get("DEFAULT_HYDRATION_TARGET_ML", 2000)
    )


def get_today_hydration(
    profile: UserProfile | None | object = _PROFILE_UNSET,
) -> dict:
    today = get_local_today()
    records = list(
        db.session.scalars(
            db.select(HydrationRecord)
            .where(HydrationRecord.record_date == today)
            .order_by(
                HydrationRecord.consumed_at.desc(),
                HydrationRecord.id.desc(),
            )
        )
    )
    total = sum(record.amount_ml for record in records)
    goal = get_hydration_goal_ml(profile)
    now = datetime.now(get_app_timezone())
    return {
        "record_date": today.isoformat(),
        "total_ml": total,
        "goal_ml": goal,
        "percentage": round(total / goal * 100, 1) if goal else 0,
        "current_time": now.strftime("%H:%M"),
        "recent_records": [
            {
                "id": record.id,
                "amount_ml": record.amount_ml,
                "consumed_at": record.consumed_at.isoformat(timespec="minutes"),
            }
            for record in records[:3]
        ],
    }


def create_quick_hydration(payload: object) -> tuple[HydrationRecord, dict]:
    if not isinstance(payload, dict) or set(payload) != {"amount_ml"}:
        raise RecordValidationError(
            {"_schema": "Envie somente o campo amount_ml."}
        )
    amount = payload["amount_ml"]
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise RecordValidationError(
            {"amount_ml": "Informe uma quantidade inteira em ml."}
        )
    if amount < 10 or amount > 5_000:
        raise RecordValidationError(
            {"amount_ml": "Informe uma quantidade entre 10 e 5.000 ml."}
        )
    now = datetime.now(get_app_timezone())
    record = create_hydration_record(
        {
            "record_date": now.date().isoformat(),
            "amount": amount,
            "unit": "ml",
            "consumed_at": now.strftime("%H:%M"),
            "notes": None,
        }
    )
    current_app.logger.info(
        "Hidratação rápida salva: registro=%s quantidade_ml=%s.",
        record.id,
        amount,
    )
    return record, get_today_hydration()
