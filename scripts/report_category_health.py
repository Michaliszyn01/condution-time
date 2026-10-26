from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: report_category_health.py <condution_time.db>")
    database = Path(sys.argv[1]).resolve(strict=True)
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        training = connection.execute(
            "SELECT source_exercise_type, training_type, manual_training_type, "
            "record_origin, calories, distance_meters, average_heart_rate, "
            "maximum_heart_rate, average_speed_mps, vo2_max "
            "FROM training_records WHERE source_provider='health_connect'"
        ).fetchall()
        sleeps = connection.execute(
            "SELECT is_primary, awakenings_count, sleep_stages_json, "
            "average_heart_rate, minimum_heart_rate, maximum_heart_rate, "
            "average_spo2, minimum_spo2 FROM sleep_records "
            "WHERE source_provider='health_connect'"
        ).fetchall()
        duplicate_training = connection.execute(
            "SELECT COUNT(*) FROM (SELECT source_record_id FROM training_records "
            "WHERE source_record_id IS NOT NULL GROUP BY source_record_id "
            "HAVING COUNT(*) > 1)"
        ).fetchone()[0]
    output = {
        "database": str(database),
        "training_total": len(training),
        "training_by_source_code": dict(
            sorted(Counter(str(row["source_exercise_type"]) for row in training).items())
        ),
        "manual_training_classifications": sum(
            row["manual_training_type"] is not None for row in training
        ),
        "training_duplicates": duplicate_training,
        "training_metric_counts": {
            field: sum(row[field] is not None for row in training)
            for field in (
                "calories",
                "distance_meters",
                "average_heart_rate",
                "maximum_heart_rate",
                "average_speed_mps",
                "vo2_max",
            )
        },
        "sleep_total": len(sleeps),
        "sleep_primary": sum(bool(row["is_primary"]) for row in sleeps),
        "sleep_naps": sum(not bool(row["is_primary"]) for row in sleeps),
        "sleep_awakenings": {
            "minimum": min((row["awakenings_count"] for row in sleeps), default=0),
            "maximum": max((row["awakenings_count"] for row in sleeps), default=0),
            "average": round(
                sum(row["awakenings_count"] for row in sleeps) / len(sleeps), 2
            )
            if sleeps
            else 0,
        },
        "sleep_metric_counts": {
            field: sum(row[field] is not None for row in sleeps)
            for field in (
                "sleep_stages_json",
                "average_heart_rate",
                "minimum_heart_rate",
                "maximum_heart_rate",
                "average_spo2",
                "minimum_spo2",
            )
        },
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
