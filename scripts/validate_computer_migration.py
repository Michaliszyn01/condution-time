from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from flask_migrate import upgrade

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db
from app.models import StudyRecord


def app_for(path: Path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "migration-check",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path.resolve().as_posix()}",
        }
    )


def tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def main() -> int:
    project_root = PROJECT_ROOT
    smoke_dir = project_root / ".desktop-smoke"
    smoke_dir.mkdir(exist_ok=True)
    migrations = project_root / "migrations"
    empty_db = smoke_dir / "migration-empty.db"
    existing_db = smoke_dir / "migration-existing.db"
    for path in (empty_db, existing_db):
        if path.exists():
            path.unlink()

    empty_app = app_for(empty_db)
    with empty_app.app_context():
        upgrade(directory=str(migrations))
    assert {
        "computer_activity_blocks",
        "application_rules",
    }.issubset(tables(empty_db))

    existing_app = app_for(existing_db)
    with existing_app.app_context():
        upgrade(directory=str(migrations), revision="24f24f837fe5")
        db.session.add(
            StudyRecord(
                record_date=__import__("datetime").date(2026, 7, 28),
                subject="Registro preservado",
                topic="Migration",
                duration_minutes=30,
                focus_quality="good",
                record_origin="manual",
            )
        )
        db.session.commit()
        upgrade(directory=str(migrations))
        preserved = db.session.scalar(
            db.select(db.func.count(StudyRecord.id))
        )
        assert preserved == 1
    assert {
        "study_records",
        "computer_activity_blocks",
        "application_rules",
    }.issubset(tables(existing_db))

    print("migration_empty=ok")
    print("migration_existing_preserved=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
