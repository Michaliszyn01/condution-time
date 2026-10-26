from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import HealthImportRun


health_import_api = Blueprint(
    "health_import_api",
    __name__,
    url_prefix="/api/health-import",
)


def _watcher():
    return current_app.config.get("HEALTH_IMPORT_WATCHER")


def _bridge():
    return current_app.config.get("DESKTOP_BRIDGE")


def _history_item(run: HealthImportRun) -> dict:
    return {
        "id": run.id,
        "source_filename": run.source_filename,
        "source_modified_at": (
            run.source_modified_at.isoformat() if run.source_modified_at else None
        ),
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "imported_count": run.imported_count,
        "updated_count": run.updated_count,
        "skipped_count": run.skipped_count,
        "error_count": run.error_count,
        "error_summary": run.error_summary,
    }


@health_import_api.get("/status")
def status():
    watcher = _watcher()
    bridge = _bridge()
    settings = bridge.get_settings() if bridge else {}
    state = (
        watcher.status()
        if watcher
        else {
            "status": "unavailable",
            "last_file": None,
            "last_import_at": None,
            "imported_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "recent_errors": [],
        }
    )
    latest = db.session.scalar(
        db.select(HealthImportRun)
        .order_by(HealthImportRun.started_at.desc(), HealthImportRun.id.desc())
        .limit(1)
    )
    if latest and not state.get("last_import_at"):
        state.update(
            last_file=latest.source_filename,
            last_import_at=(
                latest.finished_at.isoformat() if latest.finished_at else None
            ),
            imported_count=latest.imported_count,
            updated_count=latest.updated_count,
            skipped_count=latest.skipped_count,
        )
        if latest.status == "failed" and latest.error_summary:
            state["recent_errors"] = [latest.error_summary]
    return jsonify(
        **state,
        enabled=bool(settings.get("health_import_enabled")),
        folder_configured=bool(settings.get("health_import_folder")),
        folder_name=(
            settings.get("health_import_folder", "").rstrip("\\/").split("\\")[-1]
            if settings.get("health_import_folder")
            else None
        ),
        poll_seconds=settings.get("health_import_poll_seconds", 60),
        stability_seconds=settings.get("health_import_stability_seconds", 20),
    )


@health_import_api.post("/select-folder")
def select_folder():
    bridge = _bridge()
    if bridge is None:
        return jsonify(error="Seleção disponível apenas no aplicativo Windows."), 503
    try:
        selected = bridge.select_health_import_folder()
    except (OSError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(selected=bool(selected), folder_name=selected and selected.split("\\")[-1])


@health_import_api.post("/import-now")
def import_now():
    watcher = _watcher()
    if watcher is None:
        return jsonify(error="Importador de saúde indisponível."), 503
    try:
        return jsonify(watcher.import_now())
    except FileNotFoundError as exc:
        return jsonify(error=str(exc)), 404
    except (OSError, ValueError) as exc:
        current_app.logger.exception("Falha ao importar dados de saúde.")
        return jsonify(error=str(exc)), 400


@health_import_api.patch("/settings")
def update_settings():
    bridge = _bridge()
    if bridge is None:
        return jsonify(error="Configuração disponível apenas no aplicativo."), 503
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Envie um objeto JSON válido."), 400
    allowed = {
        "health_import_enabled",
        "health_import_poll_seconds",
        "health_import_stability_seconds",
    }
    if set(payload) - allowed:
        return jsonify(error="Há configurações de saúde não permitidas."), 400
    try:
        settings = bridge.update_settings(payload)
        watcher = _watcher()
        if watcher is not None and "health_import_enabled" in payload:
            if settings["health_import_enabled"]:
                watcher.start()
            else:
                watcher.stop()
                watcher.state.update(status="disabled")
        return jsonify(settings)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@health_import_api.get("/history")
def history():
    limit = min(max(request.args.get("limit", 20, type=int), 1), 100)
    runs = db.session.scalars(
        db.select(HealthImportRun)
        .order_by(HealthImportRun.started_at.desc(), HealthImportRun.id.desc())
        .limit(limit)
    )
    return jsonify(items=[_history_item(run) for run in runs])
