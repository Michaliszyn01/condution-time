from __future__ import annotations

import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.extensions import db
from app.health_import.archive import HealthArchiveError, prepare_database
from app.health_import.importer import HealthImporter
from app.health_import.schema_detector import (
    UnsupportedHealthSchema,
    detect_schema,
)
from app.health_import.watcher import HealthImportWatcher
from app.models import (
    BodyMeasurement,
    DailyHealthSummary,
    HealthImportRun,
    SleepRecord,
    TrainingRecord,
)
from desktop.config import DesktopSettingsStore


def _health_database(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE sleep_session_record_table (
            row_id INTEGER, uuid BLOB, last_modified_time INTEGER,
            start_time INTEGER, end_time INTEGER
        );
        CREATE TABLE sleep_stages_table (
            parent_key INTEGER, stage_start_time INTEGER,
            stage_end_time INTEGER, stage_type INTEGER
        );
        CREATE TABLE exercise_session_record_table (
            row_id INTEGER, uuid BLOB, last_modified_time INTEGER,
            start_time INTEGER, end_time INTEGER, exercise_type INTEGER,
            title TEXT, local_date INTEGER
        );
        CREATE TABLE exercise_segments_table (
            parent_key INTEGER, segment_start_time INTEGER,
            segment_end_time INTEGER, segment_type INTEGER,
            repetitions_count INTEGER
        );
        CREATE TABLE weight_record_table (
            uuid BLOB, last_modified_time INTEGER, time INTEGER,
            weight REAL, local_date INTEGER
        );
        CREATE TABLE body_fat_record_table (
            uuid BLOB, last_modified_time INTEGER, time INTEGER,
            percentage REAL, local_date INTEGER
        );
        CREATE TABLE steps_record_table (
            start_time INTEGER, end_time INTEGER, count INTEGER,
            local_date INTEGER
        );
        CREATE TABLE distance_record_table (
            start_time INTEGER, end_time INTEGER, distance REAL,
            local_date INTEGER
        );
        CREATE TABLE total_calories_burned_record_table (
            start_time INTEGER, end_time INTEGER, energy REAL,
            local_date INTEGER
        );
        CREATE TABLE heart_rate_record_table (
            row_id INTEGER, local_date INTEGER
        );
        CREATE TABLE heart_rate_record_series_table (
            parent_key INTEGER, epoch_millis INTEGER, beats_per_minute INTEGER
        );
        CREATE TABLE oxygen_saturation_record_table (
            time INTEGER, percentage REAL, local_date INTEGER
        );
        CREATE TABLE vo2_max_record_table (
            local_date INTEGER,
            vo2_milliliters_per_minute_kilogram REAL
        );
        """
    )
    start = 1_720_000_000_000
    end = start + 8 * 60 * 60 * 1000
    day = start // 86_400_000
    connection.execute(
        "INSERT INTO sleep_session_record_table VALUES (1, ?, ?, ?, ?)",
        (b"sleep-1", end, start, end),
    )
    connection.execute(
        "INSERT INTO sleep_stages_table VALUES (1, ?, ?, 1)",
        (start + 1000, start + 2000),
    )
    connection.execute(
        "INSERT INTO exercise_session_record_table "
        "VALUES (2, ?, ?, ?, ?, 16, 'Corrida', ?)",
        (b"training-1", end, start, start + 3_600_000, day),
    )
    connection.execute(
        "INSERT INTO weight_record_table VALUES (?, ?, ?, 80000, ?)",
        (b"weight-1", end, end, day),
    )
    connection.execute(
        "INSERT INTO body_fat_record_table VALUES (?, ?, ?, 0.2, ?)",
        (b"fat-1", end, end, day),
    )
    connection.execute(
        "INSERT INTO steps_record_table VALUES (?, ?, 5000, ?)",
        (start, end, day),
    )
    connection.execute(
        "INSERT INTO distance_record_table VALUES (?, ?, 5000, ?)",
        (start, end, day),
    )
    connection.execute(
        "INSERT INTO total_calories_burned_record_table VALUES (?, ?, 400, ?)",
        (start, end, day),
    )
    connection.execute("INSERT INTO heart_rate_record_table VALUES (3, ?)", (day,))
    connection.executemany(
        "INSERT INTO heart_rate_record_series_table VALUES (3, ?, ?)",
        [(start + 1000, 60), (start + 2000, 80)],
    )
    connection.execute(
        "INSERT INTO oxygen_saturation_record_table VALUES (?, 98, ?)",
        (start + 1000, day),
    )
    connection.execute(
        "INSERT INTO vo2_max_record_table VALUES (?, 42.5)",
        (day,),
    )
    connection.commit()
    connection.close()
    return path


def _archive(database: Path, archive: Path) -> Path:
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.write(database, "Health Connect/health_connect_export.db")
    return archive


def test_prepare_database_accepts_valid_zip(tmp_path):
    database = _health_database(tmp_path / "source.db")
    result = prepare_database(
        _archive(database, tmp_path / "health.zip"),
        tmp_path / "work",
    )
    assert result.name == "health_connect_export.db"
    assert result.is_file()


def test_prepare_database_rejects_path_traversal(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("../health_connect_export.db", b"unsafe")
    with pytest.raises(HealthArchiveError, match="inseguros"):
        prepare_database(archive, tmp_path / "work")


def test_prepare_database_rejects_corrupt_zip(tmp_path):
    archive = tmp_path / "corrupt.zip"
    archive.write_bytes(b"not-a-zip")
    with pytest.raises(HealthArchiveError, match="corrompido"):
        prepare_database(archive, tmp_path / "work")


def test_prepare_database_rejects_missing_database(tmp_path):
    archive = tmp_path / "missing.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("readme.txt", "x")
    with pytest.raises(HealthArchiveError, match="exatamente um"):
        prepare_database(archive, tmp_path / "work")


def test_schema_detector_rejects_unknown_schema():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE unrelated (id INTEGER)")
    with pytest.raises(UnsupportedHealthSchema):
        detect_schema(connection)


def test_importer_imports_and_deduplicates_real_shapes(app, tmp_path):
    database = _health_database(tmp_path / "source.db")
    archive = _archive(database, tmp_path / "health.zip")
    result = HealthImporter(app).import_file(archive)
    assert result["status"] == "completed"
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(SleepRecord.id))) == 1
        assert db.session.scalar(db.select(db.func.count(TrainingRecord.id))) == 1
        assert db.session.scalar(db.select(db.func.count(BodyMeasurement.id))) == 2
        assert db.session.scalar(db.select(db.func.count(DailyHealthSummary.record_date))) == 1
        sleep = db.session.scalar(db.select(SleepRecord))
        assert sleep.perceived_quality is None
        assert sleep.average_heart_rate == 70
        training = db.session.scalar(db.select(TrainingRecord))
        assert training.intensity is None
        assert training.distance_meters == 5000
    duplicate = HealthImporter(app).import_file(archive)
    assert duplicate["status"] == "unchanged"
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(HealthImportRun.id))) == 1


def test_watcher_requires_two_equal_observations(app, tmp_path):
    source = tmp_path / "health.zip"
    source.write_bytes(b"x")

    class Settings:
        health_import_folder = str(tmp_path)
        health_import_enabled = True
        health_import_poll_seconds = 30
        health_import_stability_seconds = 5

    class Store:
        def load(self):
            return Settings()

    old = datetime.now(timezone.utc).timestamp() - 30
    import os

    os.utime(source, (old, old))
    watcher = HealthImportWatcher(app, Store())
    assert watcher._is_stable(source) is False
    assert watcher._is_stable(source) is True
    watcher.stop()


def test_desktop_settings_accepts_powershell_utf8_bom(tmp_path):
    path = tmp_path / "desktop.json"
    path.write_bytes(
        b"\xef\xbb\xbf"
        + b'{"health_import_enabled":true,"health_import_folder":"G:\\\\Meu Drive"}'
    )
    settings = DesktopSettingsStore(path).load()
    assert settings.health_import_enabled is True
    assert settings.health_import_folder == r"G:\Meu Drive"
