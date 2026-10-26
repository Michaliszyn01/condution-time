from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import ApplicationRule, ComputerActivityBlock, ProjectRule, SessionRecord
from desktop.monitoring.state import BlockDraft, SessionContext


class MonitoringRepository:
    def __init__(self, app: Any, *, logger: logging.Logger | None = None) -> None:
        self.app = app
        self.logger = logger or logging.getLogger(__name__)

    def get_application_rule(self, executable_name: str) -> ApplicationRule | None:
        with self.app.app_context():
            return db.session.scalar(
                db.select(ApplicationRule)
                .where(
                    db.func.lower(ApplicationRule.executable_name)
                    == executable_name.lower(),
                    ApplicationRule.enabled.is_(True),
                )
                .order_by(ApplicationRule.priority.desc(), ApplicationRule.id)
                .limit(1)
            )

    def get_active_session(self, record_date: date) -> SessionContext | None:
        with self.app.app_context():
            session = db.session.scalar(
                db.select(SessionRecord)
                .where(
                    SessionRecord.record_date == record_date,
                    SessionRecord.status == "running",
                    SessionRecord.computer_monitoring_enabled.is_(True),
                )
                .order_by(SessionRecord.created_at.desc(), SessionRecord.id.desc())
                .limit(1)
            )
            if session is None:
                return None
            return SessionContext(
                id=session.id,
                session_type=session.session_type,
                related_category=session.related_category,
            )

    def get_project_rules(self) -> list[ProjectRule]:
        with self.app.app_context():
            return list(
                db.session.scalars(
                    db.select(ProjectRule)
                    .where(ProjectRule.enabled.is_(True))
                    .order_by(ProjectRule.priority.desc(), ProjectRule.id)
                )
            )

    def save_block(self, draft: BlockDraft) -> ComputerActivityBlock | None:
        if draft.ended_at is None:
            return None
        duration = int((draft.ended_at - draft.started_at).total_seconds())
        if duration <= 0:
            return None
        with self.app.app_context():
            block = ComputerActivityBlock(
                record_date=draft.record_date,
                executable_name=draft.executable_name,
                friendly_name=draft.friendly_name,
                classification=draft.classification,
                category=draft.category,
                classification_source=draft.classification_source,
                started_at=draft.started_at,
                ended_at=draft.ended_at,
                duration_seconds=duration,
                was_idle=draft.was_idle,
                session_id=draft.session_id,
                project_rule_id=draft.project_rule_id,
                project_key=draft.project_key,
                project_display_name=draft.project_display_name,
                site_key=draft.site_key,
                context_source=draft.context_source,
            )
            try:
                db.session.add(block)
                db.session.commit()
                return block
            except SQLAlchemyError:
                db.session.rollback()
                self.logger.exception("Erro de banco ao persistir bloco do monitor.")
                raise
            finally:
                db.session.remove()
