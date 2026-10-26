from __future__ import annotations

import sqlite3
from pathlib import Path


EXPECTED_COLUMNS = {
    "id",
    "record_date",
    "executable_name",
    "friendly_name",
    "classification",
    "category",
    "classification_source",
    "started_at",
    "ended_at",
    "duration_seconds",
    "was_idle",
    "session_id",
    "created_at",
    "updated_at",
}
FORBIDDEN_COLUMNS = {
    "window_title",
    "title",
    "url",
    "executable_path",
    "document_name",
    "keystrokes",
    "mouse_coordinates",
}


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    profile = project_root / ".desktop-smoke" / "CondutionTime"
    database = profile / "data" / "condution_time.db"
    log_path = profile / "logs" / "condution_time.log"
    with sqlite3.connect(database) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(computer_activity_blocks)"
            )
        }
    assert columns == EXPECTED_COLUMNS
    assert not (columns & FORBIDDEN_COLUMNS)
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    lowered = log_text.casefold()
    assert "https://" not in lowered
    assert "window_title" not in lowered
    assert "executable_path" not in lowered
    print("computer_block_schema=privacy_minimal")
    print("logs_without_titles_urls_paths=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
