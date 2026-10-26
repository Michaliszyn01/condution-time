from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from flask_migrate import upgrade

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from desktop.paths import get_app_data_dir, get_database_path, resource_path, sqlite_uri


PRESERVED_TABLES = (
    "study_records",
    "training_records",
    "sleep_records",
    "meal_records",
    "hydration_records",
    "session_records",
    "computer_activity_blocks",
    "application_rules",
    "monitor_settings",
    "health_import_runs",
    "body_measurements",
    "daily_health_summaries",
    "study_subject_progress",
    "user_profile",
    "project_rules",
)
EXPECTED_HEAD = "e6b9c3d7f204"


def counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    with sqlite3.connect(path) as connection:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return {
            table: int(
                connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )
            for table in PRESERVED_TABLES
            if table in existing
        }


def create_consistent_backup(source_path: Path, backup_path: Path) -> None:
    with sqlite3.connect(
        f"file:{source_path.as_posix()}?mode=ro",
        uri=True,
    ) as source:
        with sqlite3.connect(backup_path) as destination:
            source.backup(destination)


def main() -> int:
    database = get_database_path()
    backup = None
    before = counts(database)
    if database.exists():
        backup_dir = get_app_data_dir() / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / (
            "condution_time-before-stage2-"
            + datetime.now().strftime("%Y%m%d-%H%M%S")
            + ".db"
        )
        create_consistent_backup(database, backup)

    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": sqlite_uri(database),
            "INSTANCE_PATH": str(database.parent),
        }
    )
    with app.app_context():
        upgrade(directory=str(resource_path("migrations")))
        if backup is not None:
            from app.services.notification_service import create_notification

            create_notification(
                notification_key=f"backup-created:{backup.stem}",
                type="backup_created",
                title="Backup de segurança criado",
                message="Seus dados foram protegidos antes da atualização.",
                action_url="/configuracoes",
                severity="success",
                source_type="database_migration",
            )

    after = counts(database)
    if before != after:
        raise RuntimeError(
            f"Contagens dos registros existentes mudaram: {before!r} -> {after!r}"
        )
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    required = {
        "computer_activity_blocks",
        "health_import_runs",
        "body_measurements",
        "daily_health_summaries",
        "study_subject_progress",
        "user_profile",
        "project_rules",
        "experience_events",
        "achievement_unlocks",
        "app_notifications",
    }
    if not required.issubset(tables):
        raise RuntimeError("O schema esperado não está completo após a migration.")
    with sqlite3.connect(database) as connection:
        head = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    if head != EXPECTED_HEAD:
        raise RuntimeError(f"Migration inesperada: {head!r}.")

    print(f"database={database}")
    print(f"backup={backup or 'not-needed'}")
    print(f"preserved_counts={after}")
    print(f"migration_head={head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
