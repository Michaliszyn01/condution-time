from datetime import date, time, timedelta

from app.extensions import db
from app.models import SleepRecord
from app.services.sleep_service import (
    calculate_provisional_sleep_score,
    get_monthly_sleep_heatmap,
    get_sleep_page_data,
    get_sleep_summary_for_date,
    get_weekly_sleep_data,
)


REFERENCE_DATE = date(2026, 7, 27)


def add_sleep(
    target_date: date,
    *,
    start: time = time(23, 0),
    end: time = time(7, 0),
    duration: int = 480,
    quality: str = "good",
    awakenings: int = 1,
    restored: str = "yes",
    notes: str | None = None,
) -> SleepRecord:
    record = SleepRecord(
        record_date=target_date,
        sleep_start=start,
        sleep_end=end,
        duration_minutes=duration,
        perceived_quality=quality,
        awakenings_count=awakenings,
        woke_restored=restored,
        notes=notes,
        record_origin="manual",
    )
    db.session.add(record)
    db.session.commit()
    return record


def test_sleep_page_without_record_has_real_empty_state(client, app):
    with app.app_context():
        summary = get_sleep_summary_for_date(REFERENCE_DATE)

    response = client.get("/sono")

    assert summary["record"] is None
    assert summary["duration"] == "—"
    assert summary["score"] == 0
    assert response.status_code == 200
    assert "Nenhum sono registrado para hoje" in response.text
    assert "Indicadores do sono" in response.text
    assert "Sono profundo" not in response.text
    assert "Sono REM" not in response.text
    assert "Sem estágios nesta noite" in response.text


def test_provisional_sleep_score_uses_duration_quality_rest_and_interruptions(app):
    with app.app_context():
        record = add_sleep(
            REFERENCE_DATE,
            duration=480,
            quality="excellent",
            awakenings=0,
            restored="yes",
        )
        score = calculate_provisional_sleep_score(record)

    assert score == 20


def test_sleep_page_compares_duration_score_and_wake_time(app):
    with app.app_context():
        add_sleep(
            REFERENCE_DATE - timedelta(days=1),
            end=time(6, 40),
            duration=420,
            quality="regular",
            awakenings=3,
            restored="partially",
        )
        add_sleep(
            REFERENCE_DATE,
            end=time(7, 0),
            duration=480,
            quality="excellent",
            awakenings=0,
            restored="yes",
        )
        data = get_sleep_page_data(REFERENCE_DATE)

    assert data["score"]["raw_value"] == 20
    assert data["score"]["previous_raw_value"] == 12
    assert data["score"]["comparison"] == "+8 pts vs ontem"
    assert data["metrics"][0]["helper"] == "+1h vs ontem"
    assert data["metrics"][3]["helper"] == "20 min mais tarde que ontem"


def test_sleep_summary_and_indicators_use_manual_fields(app):
    with app.app_context():
        add_sleep(
            REFERENCE_DATE,
            start=time(0, 30),
            end=time(7, 30),
            duration=420,
            quality="regular",
            awakenings=2,
            restored="partially",
            notes="Acordei com barulho.",
        )
        data = get_sleep_page_data(REFERENCE_DATE)

    assert data["metrics"][2]["value"] == "00:30 – 07:30"
    assert data["list"]["items"][3]["value"] == "2 vezes"
    assert any(item["value"] == "Regular" for item in data["list"]["items"])
    assert any(item["value"] == "Parcialmente" for item in data["list"]["items"])
    assert any("Acordei com barulho." in item["meta"] for item in data["list"]["items"])
    assert [item["name"] for item in data["progress"]["items"]] == [
        "Duração",
        "Qualidade percebida",
        "Descanso ao acordar",
        "Continuidade",
    ]


def test_weekly_sleep_data_and_monthly_heatmap(app):
    with app.app_context():
        add_sleep(
            REFERENCE_DATE - timedelta(days=6),
            duration=300,
            quality="bad",
            restored="no",
            awakenings=4,
        )
        add_sleep(
            REFERENCE_DATE,
            duration=480,
            quality="excellent",
            restored="yes",
            awakenings=0,
        )
        weekly = get_weekly_sleep_data(REFERENCE_DATE)
        heatmap = get_monthly_sleep_heatmap(2026, 7, REFERENCE_DATE)

    assert len(weekly) == 7
    assert weekly[1]["score"] == 0
    assert weekly[-1]["score"] == 100
    assert weekly[-1]["tooltip_lines"] == [
        "8h",
        "Qualidade excelente",
        "Descansado: Sim",
    ]
    assert heatmap["month"] == "Julho de 2026"
    assert heatmap["days"][26]["level"] == 5
    assert "20 de 20 pontos" in heatmap["days"][26]["title"]


def test_sleep_crossing_midnight_is_rendered_from_real_record(client):
    response = client.post(
        "/api/records/sleep",
        json={
            "record_date": date.today().isoformat(),
            "sleep_start": "22:30",
            "sleep_end": "06:00",
            "perceived_quality": "Boa",
            "awakenings_count": 1,
            "woke_restored": "Sim",
            "notes": "",
            "record_origin": "Manual",
        },
    )
    page = client.get("/sono")

    assert response.status_code == 201
    assert "7h 30min" in page.text
    assert "22:30 – 06:00" in page.text
