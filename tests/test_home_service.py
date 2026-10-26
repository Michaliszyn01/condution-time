from datetime import date, datetime, time, timedelta, timezone

from app.extensions import db
from app.models import (
    ComputerActivityBlock,
    HydrationRecord,
    MealRecord,
    SessionRecord,
    SleepRecord,
    StudyRecord,
    TrainingRecord,
)
from app.services.home_service import (
    get_consistency_summary,
    get_daily_accomplishments,
    get_home_cta_state,
    get_home_month_calendar,
    get_home_page_data,
    get_yesterday_summary,
)
from app.services.analytics_utils import get_local_today
from app.services.scoring_service import calculate_daily_score


REFERENCE_DATE = date(2026, 7, 27)


def add_study(
    target_date: date,
    *,
    duration: int = 120,
    created_hour: int = 10,
) -> StudyRecord:
    record = StudyRecord(
        record_date=target_date,
        subject="Matemática",
        topic="Geometria",
        duration_minutes=duration,
        questions_count=31,
        correct_answers=31,
        focus_quality="excellent",
        learned_text="Aprendizado",
        difficulty_text=None,
        record_origin="manual",
        created_at=datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            created_hour + 3,
            tzinfo=timezone.utc,
        ),
    )
    db.session.add(record)
    return record


def add_training(
    target_date: date,
    *,
    duration: int = 60,
    created_hour: int = 11,
) -> TrainingRecord:
    record = TrainingRecord(
        record_date=target_date,
        training_type="strength",
        activity_name="Peito e tríceps",
        duration_minutes=duration,
        intensity=8,
        perceived_performance="excellent",
        exercises_text="Supino e tríceps pulley",
        discomfort_level="none",
        created_at=datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            created_hour + 3,
            tzinfo=timezone.utc,
        ),
    )
    db.session.add(record)
    return record


def add_sleep(
    target_date: date,
    *,
    duration: int = 480,
    quality: str = "excellent",
    created_hour: int = 9,
) -> SleepRecord:
    record = SleepRecord(
        record_date=target_date,
        sleep_start=time(23, 0),
        sleep_end=time(7, 0),
        duration_minutes=duration,
        perceived_quality=quality,
        awakenings_count=0,
        woke_restored="yes",
        record_origin="manual",
        created_at=datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            created_hour + 3,
            tzinfo=timezone.utc,
        ),
    )
    db.session.add(record)
    return record


def add_meal(
    target_date: date,
    *,
    meal_type: str = "lunch",
    meal_time: time = time(12, 0),
    quality: str = "excellent",
) -> MealRecord:
    record = MealRecord(
        record_date=target_date,
        meal_type=meal_type,
        meal_time=meal_time,
        foods_text="Refeição completa",
        has_protein="yes",
        has_fruits_or_vegetables="yes",
        perceived_quality=quality,
    )
    db.session.add(record)
    return record


def add_hydration(
    target_date: date,
    *,
    amount_ml: int = 2000,
    consumed_at: time = time(13, 0),
) -> HydrationRecord:
    record = HydrationRecord(
        record_date=target_date,
        amount_ml=amount_ml,
        consumed_at=consumed_at,
    )
    db.session.add(record)
    return record


def add_session(
    target_date: date,
    *,
    title: str = "Revisar geometria",
    finished_hour: int = 14,
) -> SessionRecord:
    record = SessionRecord(
        record_date=target_date,
        session_type="focus",
        title=title,
        related_category="study",
        status="completed",
        focus_percentage=90,
        result_text="Objetivo concluído",
        learned_text="Reflexão",
        finished_at=datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            finished_hour + 3,
            tzinfo=timezone.utc,
        ),
    )
    db.session.add(record)
    return record


def add_max_nutrition(target_date: date) -> None:
    add_meal(target_date, meal_type="breakfast", meal_time=time(8, 0))
    add_meal(target_date, meal_type="lunch", meal_time=time(12, 0))
    add_meal(target_date, meal_type="dinner", meal_time=time(19, 0))
    add_hydration(target_date)


def add_four_max_categories(target_date: date) -> None:
    add_study(target_date)
    for offset in range(4):
        add_training(
            target_date - timedelta(days=offset),
            duration=60 if offset == 0 else 20,
        )
    add_sleep(target_date)
    add_max_nutrition(target_date)
    db.session.commit()


def test_home_service_empty_database(app):
    with app.app_context():
        data = get_home_page_data(REFERENCE_DATE)

    assert data["score"]["value"] == 0
    assert data["score"]["base"] == 0
    assert data["score"]["bonus"] == 0
    assert data["score"]["ring_value"] == 0
    assert data["score"]["coverage"] == "0 de 5 categorias avaliadas"
    assert all(not category["evaluated"] for category in data["categories"])
    assert all(category["display_score"] == "—" for category in data["categories"])
    assert data["accomplishments"] == []
    assert data["yesterday_summary"]["available"] is False
    assert data["consistency"]["days"] == 0
    assert all(day["level"] == 0 for day in data["calendar"]["days"])
    assert data["cta"]["title"] == "Vamos começar hoje?"


def test_home_page_empty_state_and_unevaluated_dash(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Nenhum registro hoje" in response.text
    assert "Não há dados suficientes de ontem." in response.text
    assert "0 de 5 categorias avaliadas" in response.text
    assert "—" in response.text
    assert "9 / 20" not in response.text


def test_home_with_one_evaluated_category_uses_official_score(app):
    with app.app_context():
        add_study(REFERENCE_DATE)
        db.session.commit()
        data = get_home_page_data(REFERENCE_DATE)
        official = calculate_daily_score(REFERENCE_DATE)

    assert data["score"]["value"] == official["final_score"]
    assert data["score"]["base"] == official["normalized_base_score"]
    assert data["score"]["ring_value"] == official["normalized_base_score"]
    assert data["categories"][0]["score"] == 20
    assert data["categories"][0]["evaluated"] is True
    assert data["categories"][1]["display_score"] == "—"
    assert data["cta"]["title"] == "Continue construindo seu dia"


def test_home_four_of_five_normalizes_without_claiming_complete_day(app):
    with app.app_context():
        add_four_max_categories(REFERENCE_DATE)
        data = get_home_page_data(REFERENCE_DATE)

    assert data["score"]["base"] == 100
    assert data["score"]["value"] == 100
    assert data["score"]["coverage"] == "4 de 5 categorias avaliadas"
    assert data["score"]["coverage_note"] == "100 pontos nas categorias avaliadas"
    assert data["categories"][3]["key"] == "computer"
    assert data["categories"][3]["evaluated"] is False
    assert data["categories"][3]["display_score"] == "—"


def test_home_bonus_total_110_and_ring_stays_at_100(client, app):
    today = get_local_today()
    with app.app_context():
        add_four_max_categories(today)
        add_session(today, title="Sessão 1")
        add_session(today, title="Sessão 2", finished_hour=15)
        db.session.commit()

    response = client.get("/")

    assert response.status_code == 200
    assert '<strong class="score-value">110</strong>' in response.text
    assert "Base normalizada: 100%" in response.text
    assert "Base normalizada: 110%" not in response.text
    assert "+10 bônus" in response.text


def test_home_comparison_mentions_lower_coverage(app):
    yesterday = REFERENCE_DATE - timedelta(days=1)
    with app.app_context():
        add_four_max_categories(yesterday)
        add_study(REFERENCE_DATE)
        add_session(REFERENCE_DATE)
        add_session(REFERENCE_DATE, finished_hour=15)
        db.session.commit()
        data = get_home_page_data(REFERENCE_DATE)

    assert data["score"]["value"] == 110
    assert data["yesterday"]["daily_score"]["final_score"] == 100
    assert data["score"]["comparison"] == (
        "+10 vs ontem, com 3 categorias a menos avaliadas"
    )
    assert data["score"]["coverage_comparison"] == "Cobertura: -3 categorias"


def test_home_without_yesterday_has_no_comparison(app):
    with app.app_context():
        add_study(REFERENCE_DATE)
        db.session.commit()
        data = get_home_page_data(REFERENCE_DATE)

    assert data["score"]["comparison"] == "Sem comparação com ontem"


def test_consistency_uses_three_categories_and_base_sixty(app):
    with app.app_context():
        for offset in range(4):
            target_date = REFERENCE_DATE - timedelta(days=offset)
            add_study(target_date, duration=60)
            add_sleep(target_date)
            add_meal(target_date)
        db.session.commit()
        result = get_consistency_summary(REFERENCE_DATE)

    assert result["days"] == 4
    assert result["message"] == "Boa consistência"
    assert sum(day["is_consistent"] for day in result["weekdays"]) == 4
    assert "3 categorias" in result["rule"]


def test_accomplishments_are_combined_recent_first_and_limited(app):
    with app.app_context():
        add_sleep(REFERENCE_DATE, created_hour=9)
        add_study(REFERENCE_DATE, created_hour=10)
        add_training(REFERENCE_DATE, created_hour=11)
        add_meal(REFERENCE_DATE, meal_time=time(12, 0))
        add_hydration(REFERENCE_DATE, consumed_at=time(13, 0))
        add_session(REFERENCE_DATE, finished_hour=14)
        db.session.commit()
        accomplishments = get_daily_accomplishments(REFERENCE_DATE)

    assert len(accomplishments) == 5
    assert accomplishments[0]["text"] == "Concluiu a sessão Revisar geometria"
    assert accomplishments[1]["text"] == "Registrou 2 L de água"
    assert accomplishments[2]["text"] == "Registrou Almoço"
    assert accomplishments[-1]["text"] == "Estudou Matemática por 2h"
    assert all(item["endpoint"].startswith("main.") for item in accomplishments)


def test_yesterday_summary_uses_only_evaluated_categories_for_extremes(app):
    yesterday = REFERENCE_DATE - timedelta(days=1)
    with app.app_context():
        add_study(yesterday)
        add_sleep(
            yesterday,
            duration=300,
            quality="bad",
        )
        db.session.commit()
        summary = get_yesterday_summary(REFERENCE_DATE)

    assert summary["available"] is True
    assert summary["title"].startswith("Ontem você fez")
    assert summary["best_category"] == "Estudo — 20/20"
    assert summary["lowest_category"].startswith("Sono —")
    assert "Computador" not in summary["lowest_category"]


def test_month_calendar_is_dynamic_and_reduces_low_coverage_level(app):
    with app.app_context():
        add_study(date(2026, 7, 10))
        db.session.commit()
        result = get_home_month_calendar(
            2026,
            7,
            reference_date=REFERENCE_DATE,
        )

    day = result["days"][9]
    assert result["month"] == "Julho de 2026"
    assert day["level"] == 4
    assert "100 pontos" in day["title"]
    assert "Cobertura 20%" in day["title"]
    assert result["days"][26]["is_highlighted"] is True


def test_home_cta_states_for_zero_partial_and_full_coverage():
    empty = get_home_cta_state({"evaluated_categories": 0})
    partial = get_home_cta_state({"evaluated_categories": 4})
    complete = get_home_cta_state({"evaluated_categories": 5})

    assert empty["primary_label"] == "Registrar"
    assert partial["title"] == "Continue construindo seu dia"
    assert partial["description"] == "Você avaliou 4 de 5 categorias."
    assert complete["title"] == "Seu dia está completo"
    assert complete["primary_label"] == "Ver detalhes"


def test_home_computer_stays_unevaluated_without_real_summary(app):
    with app.app_context():
        add_four_max_categories(REFERENCE_DATE)
        data = get_home_page_data(REFERENCE_DATE)

    computer = next(
        item for item in data["categories"] if item["key"] == "computer"
    )
    assert computer["evaluated"] is False
    assert computer["score"] == 0
    assert computer["display_score"] == "—"
    assert computer["status"] == "Ainda não avaliada hoje"


def test_home_reaches_five_of_five_with_real_computer_data(app):
    with app.app_context():
        add_four_max_categories(REFERENCE_DATE)
        started = datetime(
            REFERENCE_DATE.year,
            REFERENCE_DATE.month,
            REFERENCE_DATE.day,
            15,
            tzinfo=timezone.utc,
        )
        db.session.add(
            ComputerActivityBlock(
                record_date=REFERENCE_DATE,
                executable_name="code.exe",
                friendly_name="Visual Studio Code",
                classification="productive",
                category="programming",
                classification_source="default_rule",
                started_at=started,
                ended_at=started + timedelta(minutes=30),
                duration_seconds=1800,
                was_idle=False,
            )
        )
        db.session.commit()
        data = get_home_page_data(REFERENCE_DATE)

    computer = next(item for item in data["categories"] if item["key"] == "computer")
    assert computer["evaluated"] is True
    assert data["score"]["coverage"] == "5 de 5 categorias avaliadas"
    assert data["cta"]["title"] == "Seu dia está completo"


def test_home_keeps_responsive_structure(client):
    response = client.get("/")

    assert response.status_code == 200
    assert 'class="dashboard-grid"' in response.text
    assert 'class="category-grid"' in response.text
    assert 'class="action-card grid-span-12"' in response.text
