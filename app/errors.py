from __future__ import annotations

import secrets
from datetime import datetime, timezone

from flask import Flask, render_template, request
from werkzeug.exceptions import InternalServerError
from sqlalchemy.exc import SQLAlchemyError


def _local_error_code() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"CT-{timestamp}-{secrets.token_hex(3).upper()}"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(500)
    def internal_server_error(error: InternalServerError):
        code = _local_error_code()
        original = getattr(error, "original_exception", None)
        if original is not None:
            app.logger.error(
                "Erro local %s em %s %s",
                code,
                request.method,
                request.path,
                exc_info=(
                    type(original),
                    original,
                    original.__traceback__,
                ),
            )
        else:
            app.logger.error(
                "Erro local %s em %s %s sem exceção original disponível.",
                code,
                request.method,
                request.path,
            )
        try:
            from app.services.notification_service import (
                create_cooldown_notification,
            )

            create_cooldown_notification(
                notification_key="application-error",
                type="application_error",
                title="O aplicativo encontrou um erro",
                message=(
                    "Uma página falhou, mas o restante do aplicativo "
                    "continua disponível."
                ),
                action_url="/configuracoes",
                severity="error",
                source_type="application",
                cooldown_minutes=60,
            )
        except SQLAlchemyError:
            # O erro original continua sendo a fonte principal; evita recursão
            # quando a própria base ainda está indisponível.
            from app.extensions import db

            db.session.rollback()
        return (
            render_template(
                "pages/error.html",
                active_page=None,
                page_title="Não foi possível abrir esta página",
                page_description="O restante do aplicativo continua disponível.",
                error_code=code,
            ),
            500,
        )
