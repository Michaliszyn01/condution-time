from pathlib import Path

from flask import Flask

from app.config import Config
from app.extensions import db, migrate


def create_app(test_config: dict | None = None) -> Flask:
    """Cria e configura a aplicação Flask."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    configured_instance_path = app.config.pop("INSTANCE_PATH", None)
    if configured_instance_path:
        app.instance_path = str(Path(configured_instance_path).resolve())
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    # A importação registra os modelos no metadata usado pelo ORM e migrações.
    from app import models  # noqa: F401
    from app.api.records import records_api
    from app.api.sessions import sessions_api
    from app.api.desktop import desktop_api
    from app.api.system import system_api
    from app.api.computer_monitor import computer_monitor_api
    from app.api.health_import import health_import_api
    from app.api.profile import profile_api
    from app.api.hydration import hydration_api
    from app.api.notifications import notifications_api

    from app.routes import main

    app.register_blueprint(main)
    app.register_blueprint(records_api)
    app.register_blueprint(sessions_api)
    app.register_blueprint(system_api)
    app.register_blueprint(desktop_api)
    app.register_blueprint(computer_monitor_api)
    app.register_blueprint(health_import_api)
    app.register_blueprint(profile_api)
    app.register_blueprint(hydration_api)
    app.register_blueprint(notifications_api)
    from app.errors import register_error_handlers

    register_error_handlers(app)

    @app.context_processor
    def inject_header_state():
        from app.services.analytics_utils import (
            format_local_date_label,
            get_local_today,
        )
        from app.services.header_service import get_header_state

        header_state = get_header_state()
        return {
            "header_state": header_state,
            "user_identity": header_state["profile"],
            "current_date_label": format_local_date_label(get_local_today()),
        }

    return app
