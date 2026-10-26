from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def scalar(connection: sqlite3.Connection, query: str):
    return connection.execute(query).fetchone()[0]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: verify_health_import.py <condution_time.db>")
    database = Path(sys.argv[1]).resolve(strict=True)
    uri = f"file:{database.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        tracked = [
            "health_import_runs",
            "sleep_records",
            "training_records",
            "body_measurements",
            "daily_health_summaries",
            "project_rules",
            "study_subject_progress",
        ]
        counts = {
            table: scalar(connection, f'SELECT COUNT(*) FROM "{table}"')
            for table in tracked
            if table in tables
        }
        imported = {
            "sleep": scalar(
                connection,
                "SELECT COUNT(*) FROM sleep_records "
                "WHERE source_provider='health_connect'",
            ),
            "training": scalar(
                connection,
                "SELECT COUNT(*) FROM training_records "
                "WHERE source_provider='health_connect'",
            ),
            "body": counts.get("body_measurements", 0),
            "daily": counts.get("daily_health_summaries", 0),
        }
        duplicate_sources = {
            "sleep": scalar(
                connection,
                "SELECT COUNT(*) FROM (SELECT source_record_id "
                "FROM sleep_records WHERE source_record_id IS NOT NULL "
                "GROUP BY source_record_id HAVING COUNT(*) > 1)",
            ),
            "training": scalar(
                connection,
                "SELECT COUNT(*) FROM (SELECT source_record_id "
                "FROM training_records WHERE source_record_id IS NOT NULL "
                "GROUP BY source_record_id HAVING COUNT(*) > 1)",
            ),
            "body": scalar(
                connection,
                "SELECT COUNT(*) FROM (SELECT source_provider, source_record_id "
                "FROM body_measurements GROUP BY source_provider, source_record_id "
                "HAVING COUNT(*) > 1)",
            ),
        }
        computer_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(computer_activity_blocks)"
            )
        }
        forbidden_columns = sorted(
            computer_columns.intersection(
                {
                    "window_title",
                    "tab_title",
                    "url",
                    "document_name",
                    "file_path",
                }
            )
        )
        version = scalar(connection, "SELECT version_num FROM alembic_version")
    print(
        json.dumps(
            {
                "migration": version,
                "counts": counts,
                "imported": imported,
                "duplicate_sources": duplicate_sources,
                "forbidden_computer_columns": forbidden_columns,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
