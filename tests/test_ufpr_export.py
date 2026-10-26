import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "export_ufpr_data.py"
SPEC = importlib.util.spec_from_file_location("export_ufpr_data", SCRIPT_PATH)
assert SPEC and SPEC.loader
export_ufpr_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export_ufpr_data)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE alembic_version (version_num TEXT NOT NULL);
            INSERT INTO alembic_version VALUES ('e6b9c3d7f204');

            CREATE TABLE study_records (
                id INTEGER PRIMARY KEY,
                record_date TEXT NOT NULL,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                questions_count INTEGER,
                correct_answers INTEGER,
                focus_quality TEXT NOT NULL,
                learned_text TEXT,
                difficulty_text TEXT,
                record_origin TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE sleep_records (
                id INTEGER PRIMARY KEY,
                record_date TEXT NOT NULL,
                sleep_start TEXT NOT NULL,
                sleep_end TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                perceived_quality TEXT,
                awakenings_count INTEGER NOT NULL,
                woke_restored TEXT,
                notes TEXT,
                record_origin TEXT NOT NULL,
                sleep_started_at TEXT,
                sleep_ended_at TEXT,
                is_primary INTEGER NOT NULL,
                source_record_id TEXT UNIQUE
            );
            CREATE TABLE session_records (
                id INTEGER PRIMARY KEY,
                record_date TEXT NOT NULL,
                session_type TEXT NOT NULL,
                title TEXT NOT NULL,
                related_category TEXT NOT NULL,
                target_duration_minutes INTEGER,
                actual_duration_seconds INTEGER,
                computer_monitoring_enabled INTEGER NOT NULL,
                objective_text TEXT,
                result_text TEXT,
                learned_text TEXT,
                difficulty_text TEXT,
                self_rating INTEGER,
                focus_percentage INTEGER,
                productive_seconds INTEGER,
                distracted_seconds INTEGER,
                status TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );
            CREATE TABLE computer_activity_blocks (
                id INTEGER PRIMARY KEY,
                record_date TEXT NOT NULL,
                classification TEXT NOT NULL,
                category TEXT NOT NULL,
                classification_source TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                was_idle INTEGER NOT NULL,
                session_id INTEGER,
                FOREIGN KEY(session_id) REFERENCES session_records(id)
            );
            CREATE TABLE user_profile (
                id INTEGER PRIMARY KEY,
                academic_goal TEXT,
                weekly_study_minutes INTEGER,
                sleep_target_minutes INTEGER
            );

            INSERT INTO study_records VALUES
                (1, '2026-08-10', ' Matemática ', 'Funções', 60, 10, 8,
                 'excellent', 'Revisei funções.', '', 'manual',
                 '2026-08-10 18:00:00.000000'),
                (2, '2026-08-11', 'matemática', 'Geometria', 30, NULL, NULL,
                 'good', NULL, 'Rever área.', 'manual',
                 '2026-08-11 19:00:00.000000');
            INSERT INTO sleep_records VALUES
                (1, '2026-08-10', '23:00:00', '07:00:00', 480, 'good', 1,
                 'yes', NULL, 'health_connect',
                 '2026-08-10 02:00:00.000000',
                 '2026-08-10 10:00:00.000000', 1, 'sleep-1');
            INSERT INTO session_records VALUES
                (1, '2026-08-10', 'study', 'Revisão', 'study', 60, 3000, 1,
                 'Funções', 'Concluído', 'Aprendi', NULL, 8, 80, 2400, 600,
                 'completed', '2026-08-10 17:00:00.000000',
                 '2026-08-10 17:50:00.000000');
            INSERT INTO computer_activity_blocks VALUES
                (1, '2026-08-10', 'productive', 'study', 'session_context',
                 '2026-08-10 17:00:00.000000', '2026-08-10 17:20:00.000000',
                 1200, 0, 1),
                (2, '2026-08-10', 'distracting', 'social', 'default_rule',
                 '2026-08-10 17:20:00.000000', '2026-08-10 17:30:00.000000',
                 600, 0, 1),
                (3, '2026-08-10', 'neutral', 'other', 'fallback',
                 '2026-08-10 17:30:00.000000', '2026-08-10 17:35:00.000000',
                 300, 0, NULL),
                (4, '2026-08-10', 'ignored', 'system', 'fallback',
                 '2026-08-10 17:35:00.000000', '2026-08-10 17:40:00.000000',
                 300, 1, NULL);
            INSERT INTO user_profile VALUES (1, 'Aprovação na UFPR', 300, 480);
            """
        )


def test_export_is_read_only_and_preserves_selected_totals(tmp_path):
    database = tmp_path / "source.db"
    output = tmp_path / "ufpr.json"
    validation = tmp_path / "validation.json"
    _database(database)
    before = _hash(database)

    result = export_ufpr_data.run_export(database, output, validation)

    assert result["status"] == "aprovado"
    assert _hash(database) == before
    payload = json.loads(output.read_text(encoding="utf-8"))
    report = json.loads(validation.read_text(encoding="utf-8"))
    assert payload["metas"]["objetivo_academico"] == "Aprovação na UFPR"
    assert len(payload["sessoes_estudo"]) == 2
    assert payload["sessoes_estudo"][0]["materia"] == "Matemática"
    assert payload["sessoes_estudo"][0]["erros"] == 2
    assert payload["sessoes_estudo"][0]["taxa_acerto_percentual"] == 80.0
    assert payload["sessoes_estudo"][1]["erros"] is None
    assert len(payload["desempenho_por_materia"]) == 1
    assert payload["desempenho_por_materia"][0]["tempo_total_minutos"] == 90
    assert len(payload["periodos_computador"]) == 3
    assert {
        item["tipo_periodo"] for item in payload["periodos_computador"]
    } == {"foco_produtivo", "distracao", "ocioso"}
    assert len(payload["resumos_diarios"]) == 2
    day = payload["resumos_diarios"][0]
    assert day["computador"]["tempo_neutro_segundos"] == 300
    assert day["computador"]["taxa_foco_percentual"] == pytest.approx(66.67)
    assert report["validacao"]["status_geral"] == "aprovado"
    assert report["sha256_exportacao"] == _hash(output)


def test_export_rejects_incomplete_schema(tmp_path):
    database = tmp_path / "incomplete.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT)")
        connection.execute("INSERT INTO alembic_version VALUES ('old')")

    connection = export_ufpr_data._connect_read_only(database)
    try:
        with pytest.raises(export_ufpr_data.ExportError, match="tabelas ausentes"):
            export_ufpr_data.build_export(connection)
    finally:
        connection.rollback()
        connection.close()


def test_command_line_parser_accepts_default_help_text():
    args = export_ufpr_data._parser().parse_args([])

    assert args.database.name == "condution_time.db"
    assert args.output.name == "condution_time_ufpr.json"
