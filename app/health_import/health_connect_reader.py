from __future__ import annotations

import bisect
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from app.health_import.schema_detector import HealthSchema, detect_schema


def epoch_millis_to_datetime(value: int | float) -> datetime:
    return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)


@contextmanager
def open_health_database(path: Path) -> Iterator[tuple[sqlite3.Connection, HealthSchema]]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        yield connection, detect_schema(connection)
    finally:
        connection.close()


class HealthConnectReader:
    def __init__(
        self,
        connection: sqlite3.Connection,
        schema: HealthSchema,
        *,
        timezone_name: str = "America/Sao_Paulo",
    ) -> None:
        self.connection = connection
        self.schema = schema
        self.timezone = ZoneInfo(timezone_name)
        self._heart_samples: tuple[list[int], list[int]] | None = None
        self._spo2_samples: tuple[list[int], list[float]] | None = None
        self._speed_samples: tuple[list[int], list[float]] | None = None

    def rows(self, table: str) -> Iterator[sqlite3.Row]:
        if not self.schema.has(table):
            return iter(())
        return iter(self.connection.execute(f'SELECT * FROM "{table}"'))

    def sleep_rows(self) -> Iterator[sqlite3.Row]:
        return self.rows("sleep_session_record_table")

    def training_rows(self) -> Iterator[sqlite3.Row]:
        return self.rows("exercise_session_record_table")

    def weight_rows(self) -> Iterator[sqlite3.Row]:
        return self.rows("weight_record_table")

    def body_fat_rows(self) -> Iterator[sqlite3.Row]:
        return self.rows("body_fat_record_table")

    def stages_for(self, parent_key: int) -> list[dict]:
        if not self.schema.has("sleep_stages_table"):
            return []
        return [
            {
                "type": int(row["stage_type"]),
                "start": epoch_millis_to_datetime(row["stage_start_time"]).isoformat(),
                "end": epoch_millis_to_datetime(row["stage_end_time"]).isoformat(),
            }
            for row in self.connection.execute(
                "SELECT stage_type, stage_start_time, stage_end_time "
                "FROM sleep_stages_table WHERE parent_key=? "
                "ORDER BY stage_start_time",
                (parent_key,),
            )
        ]

    def segments_for(self, parent_key: int) -> list[dict]:
        if not self.schema.has("exercise_segments_table"):
            return []
        return [
            {
                "type": int(row["segment_type"]),
                "repetitions": int(row["repetitions_count"] or 0),
                "duration_seconds": max(
                    0,
                    int((row["segment_end_time"] - row["segment_start_time"]) / 1000),
                ),
            }
            for row in self.connection.execute(
                "SELECT segment_type, repetitions_count, segment_start_time, "
                "segment_end_time FROM exercise_segments_table "
                "WHERE parent_key=? ORDER BY segment_start_time",
                (parent_key,),
            )
        ]

    def _series(self, kind: str) -> tuple[list[int], list[float]]:
        cached = self._heart_samples if kind == "heart" else self._spo2_samples
        if cached is not None:
            return cached
        if kind == "heart" and self.schema.has("heart_rate_record_series_table"):
            rows = self.connection.execute(
                "SELECT epoch_millis, beats_per_minute "
                "FROM heart_rate_record_series_table ORDER BY epoch_millis"
            )
            pairs = [(int(row[0]), float(row[1])) for row in rows]
        elif kind == "spo2" and self.schema.has("oxygen_saturation_record_table"):
            rows = self.connection.execute(
                "SELECT time, percentage FROM oxygen_saturation_record_table "
                "ORDER BY time"
            )
            pairs = [(int(row[0]), float(row[1])) for row in rows]
        else:
            pairs = []
        result = ([pair[0] for pair in pairs], [pair[1] for pair in pairs])
        if kind == "heart":
            self._heart_samples = result
        else:
            self._spo2_samples = result
        return result

    def series_stats(self, kind: str, start_ms: int, end_ms: int) -> dict:
        times, values = self._series(kind)
        left = bisect.bisect_left(times, start_ms)
        right = bisect.bisect_right(times, end_ms)
        selected = values[left:right]
        if not selected:
            return {}
        return {
            "average": round(sum(selected) / len(selected), 2),
            "minimum": min(selected),
            "maximum": max(selected),
        }

    def speed_stats(self, start_ms: int, end_ms: int) -> dict:
        if self._speed_samples is None:
            if self.schema.has("speed_record_table"):
                rows = self.connection.execute(
                    "SELECT epoch_millis, speed FROM speed_record_table "
                    "ORDER BY epoch_millis"
                )
                pairs = [(int(row[0]), float(row[1])) for row in rows]
            else:
                pairs = []
            self._speed_samples = (
                [pair[0] for pair in pairs],
                [pair[1] for pair in pairs],
            )
        times, values = self._speed_samples
        left = bisect.bisect_left(times, start_ms)
        right = bisect.bisect_right(times, end_ms)
        selected = values[left:right]
        return (
            {
                "average": round(sum(selected) / len(selected), 3),
                "minimum": min(selected),
                "maximum": max(selected),
            }
            if selected
            else {}
        )

    def point_average(
        self,
        table: str,
        time_column: str,
        value_column: str,
        start_ms: int,
        end_ms: int,
    ) -> float | None:
        if not self.schema.has(table):
            return None
        value = self.connection.execute(
            f'SELECT AVG("{value_column}") FROM "{table}" '
            f'WHERE "{time_column}" BETWEEN ? AND ?',
            (start_ms, end_ms),
        ).fetchone()[0]
        return round(float(value), 2) if value is not None else None

    def overlapping_sum(
        self,
        table: str,
        column: str,
        start_ms: int,
        end_ms: int,
    ) -> float | None:
        if not self.schema.has(table):
            return None
        value = self.connection.execute(
            f'SELECT SUM("{column}") FROM "{table}" '
            "WHERE start_time < ? AND end_time > ?",
            (end_ms, start_ms),
        ).fetchone()[0]
        return float(value) if value is not None else None

    def daily_summaries(self) -> dict:
        days: dict = defaultdict(dict)

        def add_sum(table: str, column: str, key: str) -> None:
            if not self.schema.has(table):
                return
            for row in self.connection.execute(
                f'SELECT local_date, SUM("{column}") FROM "{table}" '
                "GROUP BY local_date"
            ):
                day = self._date_from_local_date(row[0])
                if day:
                    days[day][key] = float(row[1] or 0)

        add_sum("steps_record_table", "count", "steps")
        add_sum("distance_record_table", "distance", "distance_meters")
        add_sum("active_calories_burned_record_table", "energy", "active_calories")
        add_sum("total_calories_burned_record_table", "energy", "total_calories")
        if self.schema.has("exercise_session_record_table"):
            for row in self.connection.execute(
                "SELECT local_date, SUM(end_time-start_time) "
                "FROM exercise_session_record_table GROUP BY local_date"
            ):
                day = self._date_from_local_date(row[0])
                if day:
                    days[day]["active_minutes"] = round(float(row[1] or 0) / 60000)
        if self.schema.has("heart_rate_record_table") and self.schema.has(
            "heart_rate_record_series_table"
        ):
            for row in self.connection.execute(
                "SELECT r.local_date, AVG(s.beats_per_minute), "
                "MAX(s.beats_per_minute) FROM heart_rate_record_table r "
                "JOIN heart_rate_record_series_table s ON s.parent_key=r.row_id "
                "GROUP BY r.local_date"
            ):
                day = self._date_from_local_date(row[0])
                if day:
                    days[day]["average_heart_rate"] = round(float(row[1]), 2)
                    days[day]["max_heart_rate"] = float(row[2])
        if self.schema.has("resting_heart_rate_record_table"):
            for row in self.connection.execute(
                "SELECT local_date, AVG(beats_per_minute) "
                "FROM resting_heart_rate_record_table GROUP BY local_date"
            ):
                day = self._date_from_local_date(row[0])
                if day:
                    days[day]["resting_heart_rate"] = round(float(row[1]), 2)
        if self.schema.has("vo2_max_record_table"):
            for row in self.connection.execute(
                "SELECT local_date, AVG(vo2_milliliters_per_minute_kilogram) "
                "FROM vo2_max_record_table GROUP BY local_date"
            ):
                day = self._date_from_local_date(row[0])
                if day:
                    days[day]["vo2_max"] = round(float(row[1]), 2)
        return dict(days)

    def _date_from_local_date(self, value: int | None):
        if value is None:
            return None
        # Health Connect exports local_date as epoch day.
        return datetime.fromtimestamp(
            int(value) * 86400,
            tz=timezone.utc,
        ).date()
