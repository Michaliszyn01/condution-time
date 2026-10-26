from flask import Blueprint, current_app, jsonify, request


desktop_api = Blueprint("desktop_api", __name__, url_prefix="/api/desktop")


def _bridge():
    if not current_app.config.get("DESKTOP_MODE"):
        return None
    return current_app.config.get("DESKTOP_BRIDGE")


def _unavailable():
    return jsonify(error="Recursos desktop indisponíveis neste modo."), 503


@desktop_api.get("/settings")
def get_settings():
    bridge = _bridge()
    if bridge is None:
        return _unavailable()
    return jsonify(bridge.get_settings())


@desktop_api.patch("/settings")
def update_settings():
    bridge = _bridge()
    if bridge is None:
        return _unavailable()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Envie um objeto JSON válido."), 400
    try:
        return jsonify(bridge.update_settings(payload))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except OSError:
        current_app.logger.exception("Não foi possível atualizar a configuração desktop.")
        return jsonify(error="Não foi possível atualizar a configuração desktop."), 500


@desktop_api.post("/open-data-folder")
def open_data_folder():
    bridge = _bridge()
    if bridge is None:
        return _unavailable()
    try:
        return jsonify(ok=bool(bridge.open_data_folder()))
    except OSError:
        current_app.logger.exception("Não foi possível abrir a pasta de dados.")
        return jsonify(error="Não foi possível abrir a pasta de dados."), 500


@desktop_api.post("/open-logs-folder")
def open_logs_folder():
    bridge = _bridge()
    if bridge is None:
        return _unavailable()
    try:
        return jsonify(ok=bool(bridge.open_logs_folder()))
    except OSError:
        current_app.logger.exception("Não foi possível abrir a pasta de logs.")
        return jsonify(error="Não foi possível abrir a pasta de logs."), 500


@desktop_api.post("/exit")
def exit_application():
    bridge = _bridge()
    if bridge is None:
        return _unavailable()
    bridge.request_exit()
    return jsonify(ok=True)
