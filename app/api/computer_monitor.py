from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.services.computer_service import (
    ComputerValidationError,
    create_application_rule,
    delete_all_computer_data,
    delete_application_rule,
    get_applications,
    get_computer_summary_for_date,
    list_application_rules,
    update_application_rule,
    create_project_rule,
    delete_project_rule,
    list_project_rules,
    update_project_rule,
)
from app.services.analytics_utils import get_local_today
from app.services.notification_service import (
    create_cooldown_notification,
    create_notification,
    resolve_notification,
)


computer_monitor_api = Blueprint(
    "computer_monitor_api",
    __name__,
    url_prefix="/api/computer-monitor",
)
MONITOR_SETTING_KEYS = {
    "monitoring_enabled",
    "start_monitoring_with_app",
    "idle_threshold_seconds",
    "sample_interval_seconds",
}


@computer_monitor_api.before_request
def local_only():
    if request.remote_addr not in {None, "127.0.0.1", "::1"}:
        return jsonify(error="Este recurso está disponível apenas localmente."), 403
    return None


def _agent():
    return current_app.config.get("COMPUTER_MONITOR_AGENT")


def _bridge():
    return current_app.config.get("DESKTOP_BRIDGE")


def _payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ComputerValidationError("Envie um objeto JSON válido.")
    return payload


def _agent_unavailable():
    return jsonify(error="Monitoramento indisponível neste modo."), 503


@computer_monitor_api.get("/status")
def status():
    agent = _agent()
    return jsonify(
        agent.status()
        if agent is not None
        else {"status": "stopped", "paused": False, "available": False}
    )


def _command(name: str):
    agent = _agent()
    if agent is None:
        return _agent_unavailable()
    try:
        changed = bool(getattr(agent, name)())
    except Exception:
        create_cooldown_notification(
            notification_key="monitoring:error",
            type="monitoring_error",
            title="Falha no monitoramento",
            message=(
                "O monitoramento encontrou um erro persistente. "
                "Abra Computador para revisar o estado."
            ),
            action_url="/computador",
            severity="error",
            source_type="computer_monitor",
            cooldown_minutes=60,
        )
        raise
    if name in {"pause", "stop"} and changed:
        create_notification(
            notification_key="monitoring:paused",
            type="monitoring_paused",
            title="Monitoramento pausado",
            message="O uso do computador não está sendo registrado.",
            action_url="/computador",
            severity="warning",
            source_type="computer_monitor",
        )
    elif name in {"resume", "start"} and changed:
        resolve_notification("monitoring:paused")
    return jsonify(ok=True, changed=changed, monitor=agent.status())


@computer_monitor_api.post("/start")
def start():
    return _command("start")


@computer_monitor_api.post("/pause")
def pause():
    return _command("pause")


@computer_monitor_api.post("/resume")
def resume():
    return _command("resume")


@computer_monitor_api.post("/stop")
def stop():
    return _command("stop")


@computer_monitor_api.get("/settings")
def get_settings():
    bridge = _bridge()
    if bridge is None:
        return jsonify(
            monitoring_enabled=False,
            start_monitoring_with_app=False,
            idle_threshold_seconds=300,
            sample_interval_seconds=2,
            available=False,
        )
    settings = bridge.get_settings()
    return jsonify(
        **{key: settings[key] for key in MONITOR_SETTING_KEYS},
        available=True,
    )


@computer_monitor_api.patch("/settings")
def update_settings():
    bridge = _bridge()
    if bridge is None:
        return _agent_unavailable()
    try:
        payload = _payload()
        unknown = set(payload) - MONITOR_SETTING_KEYS
        if unknown:
            raise ComputerValidationError("Há configurações não permitidas.")
        settings = bridge.update_settings(payload)
        agent = _agent()
        if agent is not None:
            agent.configure(
                sample_interval_seconds=settings["sample_interval_seconds"],
                idle_threshold_seconds=settings["idle_threshold_seconds"],
            )
            if not settings["monitoring_enabled"]:
                agent.stop()
            elif agent.status()["status"] == "stopped":
                agent.start()
        return jsonify(
            **{key: settings[key] for key in MONITOR_SETTING_KEYS},
            available=True,
        )
    except (ComputerValidationError, ValueError) as exc:
        return jsonify(error=str(exc)), 400


@computer_monitor_api.get("/rules")
def rules():
    return jsonify(rules=list_application_rules())


@computer_monitor_api.post("/rules")
def create_rule():
    try:
        return jsonify(rule=create_application_rule(_payload())), 201
    except ComputerValidationError as exc:
        return jsonify(error=str(exc)), 400


@computer_monitor_api.patch("/rules/<int:rule_id>")
def update_rule(rule_id: int):
    try:
        return jsonify(rule=update_application_rule(rule_id, _payload()))
    except ComputerValidationError as exc:
        return jsonify(error=str(exc)), 400
    except LookupError:
        return jsonify(error="Regra não encontrada."), 404


@computer_monitor_api.delete("/rules/<int:rule_id>")
def delete_rule(rule_id: int):
    try:
        delete_application_rule(rule_id)
        return jsonify(ok=True)
    except LookupError:
        return jsonify(error="Regra não encontrada."), 404


@computer_monitor_api.get("/applications")
def applications():
    return jsonify(applications=get_applications())


@computer_monitor_api.get("/today-summary")
def today_summary():
    return jsonify(get_computer_summary_for_date(get_local_today()))


@computer_monitor_api.post("/clear-data")
def clear_data():
    try:
        payload = _payload()
    except ComputerValidationError as exc:
        return jsonify(error=str(exc)), 400
    if payload != {"confirm": True}:
        return jsonify(error="Confirme explicitamente a limpeza dos dados."), 400
    agent = _agent()
    resume_after = agent is not None and agent.status()["status"] == "running"
    if resume_after:
        agent.pause()
    deleted = delete_all_computer_data()
    if resume_after:
        agent.resume()
    return jsonify(ok=True, deleted=deleted)


@computer_monitor_api.get("/projects")
def projects():
    return jsonify(projects=list_project_rules(include_usage=True))


@computer_monitor_api.post("/projects")
def create_project():
    try:
        return jsonify(project=create_project_rule(_payload())), 201
    except ComputerValidationError as exc:
        return jsonify(error=str(exc)), 400


@computer_monitor_api.patch("/projects/<int:rule_id>")
def update_project(rule_id: int):
    try:
        return jsonify(project=update_project_rule(rule_id, _payload()))
    except ComputerValidationError as exc:
        return jsonify(error=str(exc)), 400
    except LookupError:
        return jsonify(error="Projeto não encontrado."), 404


@computer_monitor_api.delete("/projects/<int:rule_id>")
def delete_project(rule_id: int):
    try:
        delete_project_rule(rule_id)
        return jsonify(ok=True)
    except LookupError:
        return jsonify(error="Projeto não encontrado."), 404
