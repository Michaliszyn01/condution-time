from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


EXPECTED_TABLES = (
    "health_import_runs",
    "body_measurements",
    "daily_health_summaries",
    "study_subject_progress",
    "user_profile",
    "project_rules",
    "experience_events",
    "achievement_unlocks",
)
EXPECTED_COLUMNS = {
    "user_profile": ("avatar_initials",),
    "sleep_records": (
        "sleep_started_at",
        "sleep_ended_at",
        "sleep_stages_json",
        "average_heart_rate",
        "minimum_heart_rate",
        "average_spo2",
        "minimum_spo2",
        "source_provider",
        "source_record_id",
        "source_hash",
        "imported_at",
        "last_source_update_at",
        "suggestion_status",
    ),
    "training_records": (
        "record_origin",
        "training_started_at",
        "training_ended_at",
        "distance_meters",
        "calories",
        "average_heart_rate",
        "maximum_heart_rate",
        "average_pace_seconds_per_km",
        "average_speed_mps",
        "steps",
        "segments_summary_json",
        "source_provider",
        "source_record_id",
        "source_hash",
        "imported_at",
        "last_source_update_at",
        "source_exercise_type",
        "suggestion_status",
    ),
    "computer_activity_blocks": (
        "project_rule_id",
        "project_key",
        "project_display_name",
        "site_key",
        "context_source",
    ),
}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: diagnose_real_database.py <banco.db>")
    database = Path(sys.argv[1]).resolve(strict=True)
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        actual_columns = {
            table: {
                row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
            for table in EXPECTED_COLUMNS
            if table in tables
        }
        null_counts = {}
        for table, columns in (
            ("sleep_records", ("perceived_quality", "woke_restored")),
            (
                "training_records",
                ("intensity", "perceived_performance", "discomfort_level"),
            ),
            ("computer_activity_blocks", ("project_key", "site_key")),
        ):
            if table not in tables:
                continue
            null_counts[table] = {
                column: connection.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL'
                ).fetchone()[0]
                for column in columns
            }
        migration = (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            if "alembic_version" in tables
            else None
        )
        import_statuses = (
            dict(
                connection.execute(
                    "SELECT status, COUNT(*) FROM health_import_runs GROUP BY status"
                )
            )
            if "health_import_runs" in tables
            else {}
        )
    print(
        json.dumps(
            {
                "migration": migration,
                "missing_tables": sorted(set(EXPECTED_TABLES) - tables),
                "missing_columns": {
                    table: sorted(set(expected) - actual_columns.get(table, set()))
                    for table, expected in EXPECTED_COLUMNS.items()
                },
                "null_counts": null_counts,
                "import_statuses": import_statuses,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
