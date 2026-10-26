from datetime import date

from flask import Blueprint, jsonify, request

from app.services.profile_service import (
    PERIOD_DAYS,
    get_computer_evolution,
    get_period_comparison,
    get_physical_evolution,
    get_profile_page_data,
    get_study_evolution,
    update_user_profile,
)
from app.services.profile_page_service import (
    get_achievements_profile_data,
    get_computer_profile_data,
    get_experience_timeline,
    get_goals_profile_data,
    get_health_profile_data,
    get_overview_data,
    get_sleep_profile_data,
    get_study_profile_data,
    get_training_profile_data,
    normalize_period,
)


profile_api = Blueprint("profile_api", __name__, url_prefix="/api/profile")


def _period_days() -> int:
    return PERIOD_DAYS.get(request.args.get("period", "30d"), 30)


def _period() -> str:
    return normalize_period(request.args.get("period"))


@profile_api.get("")
def profile():
    return jsonify(get_profile_page_data(request.args.get("period", "30d")))


@profile_api.patch("")
def edit_profile():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, message="Envie um objeto JSON válido."), 400
    try:
        profile_record = update_user_profile(payload)
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    return jsonify(
        success=True,
        message="Perfil atualizado.",
        profile={
            "name": profile_record.name,
            "initials": "".join(
                part[0] for part in profile_record.name.split()[:2]
            ).upper() if not profile_record.avatar_initials else profile_record.avatar_initials,
        },
    )


@profile_api.get("/study")
def study():
    return jsonify(get_study_profile_data(_period()))


@profile_api.get("/physical")
def physical():
    return jsonify(get_physical_evolution(_period_days()))


@profile_api.get("/computer")
def computer():
    return jsonify(get_computer_profile_data(_period()))


@profile_api.get("/overview")
def overview():
    return jsonify(get_overview_data(_period()))


@profile_api.get("/health")
def health():
    return jsonify(get_health_profile_data(_period()))


@profile_api.get("/training")
def training():
    return jsonify(get_training_profile_data(_period()))


@profile_api.get("/sleep")
def sleep():
    return jsonify(get_sleep_profile_data(_period()))


@profile_api.get("/achievements")
def achievements():
    return jsonify(
        get_achievements_profile_data(
            request.args.get("category", "all"),
            request.args.get("status", "all"),
        )
    )


@profile_api.get("/goals")
def goals():
    return jsonify(get_goals_profile_data())


@profile_api.patch("/goals")
def edit_goals():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, message="Envie um objeto JSON válido."), 400
    allowed = {
        "weekly_study_minutes",
        "weekly_training_count",
        "sleep_target_minutes",
        "hydration_target_ml",
    }
    if set(payload) - allowed:
        return jsonify(success=False, message="A edição de metas recebeu campos inválidos."), 400
    try:
        update_user_profile(payload)
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    return jsonify(
        success=True,
        message="Metas atualizadas.",
        goals=get_goals_profile_data(),
    )


@profile_api.get("/xp-history")
def xp_history():
    try:
        limit = int(request.args.get("limit", 20))
    except ValueError:
        limit = 20
    return jsonify({"items": get_experience_timeline(limit)})


@profile_api.get("/comparison")
def comparison():
    end = date.fromisoformat(request.args.get("end", date.today().isoformat()))
    days = _period_days()
    from datetime import timedelta

    return jsonify(get_period_comparison(end - timedelta(days=days - 1), end))
