from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.health_import.constants import SUPPORTED_TABLES


class UnsupportedHealthSchema(ValueError):
    pass


@dataclass(frozen=True)
class HealthSchema:
    tables: frozenset[str]
    user_version: int

    def has(self, table: str) -> bool:
        return table in self.tables


def detect_schema(connection: sqlite3.Connection) -> HealthSchema:
    tables = frozenset(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    )
    if not tables.intersection(SUPPORTED_TABLES):
        raise UnsupportedHealthSchema(
            "Schema incompatível: nenhuma tabela de saúde suportada foi encontrada."
        )
    required_columns = {
        "sleep_session_record_table": {"uuid", "start_time", "end_time"},
        "exercise_session_record_table": {"uuid", "start_time", "end_time"},
        "weight_record_table": {"uuid", "time", "weight"},
        "steps_record_table": {"start_time", "end_time", "count"},
    }
    for table, expected in required_columns.items():
        if table not in tables:
            continue
        columns = {
            row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        if not expected.issubset(columns):
            raise UnsupportedHealthSchema(
                f"Schema incompatível na tabela {table}."
            )
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    return HealthSchema(tables=tables, user_version=version)

