from datetime import date, time, timedelta

from app.extensions import db
from app.models import HydrationRecord, MealRecord
from app.services.nutrition_service import (
    calculate_provisional_nutrition_score,
    format_hydration,
    get_monthly_nutrition_heatmap,
    get_nutrition_indicators,
    get_nutrition_page_data,
    get_nutrition_summary_for_date,
    get_weekly_nutrition_data,
)


REFERENCE_DATE = date(2026, 7, 27)


def add_meal(
    target_date: date,
    *,
    meal_type: str = "lunch",
    meal_time: time = time(12, 30),
    foods: str = "Frango, arroz e salada",
    protein: str = "yes",
    produce: str = "yes",
    quality: str = "good",
) -> MealRecord:
    meal = MealRecord(
        record_date=target_date,
        meal_type=meal_type,
        meal_time=meal_time,
        foods_text=foods,
        approximate_amount=None,
        has_protein=protein,
        has_fruits_or_vegetables=produce,
        perceived_quality=quality,
        notes=None,
    )
    db.session.add(meal)
    db.session.commit()
    return meal


def add_hydration(
    target_date: date,
    amount_ml: int,
    *,
    consumed_at: time = time(15, 0),
) -> HydrationRecord:
    record = HydrationRecord(
        record_date=target_date,
        amount_ml=amount_ml,
        consumed_at=consumed_at,
        notes=None,
    )
    db.session.add(record)
    db.session.commit()
    return record


def test_nutrition_page_without_records_has_empty_state(client, app):
    with app.app_context():
        summary = get_nutrition_summary_for_date(REFERENCE_DATE)

    response = client.get("/alimentacao")

    assert summary["meals"] == 0
    assert summary["hydration_ml"] == 0
    assert summary["quality_average"] is None
    assert summary["score"] == 0
    assert response.status_code == 200
    assert "Nenhuma refeição registrada hoje" in response.text
    assert "Nenhum registro de alimentação nos últimos 30 dias." in response.text
    assert "82 g" not in response.text
    assert "Excessos" not in response.text
    assert "sugestão personalizada" not in response.text.casefold()


def test_nutrition_summary_counts_meals_hydration_protein_produce_and_quality(app):
    with app.app_context():
        add_meal(REFERENCE_DATE, quality="good")
        add_meal(
            REFERENCE_DATE,
            meal_type="snack",
            meal_time=time(16, 0),
            protein="unknown",
            produce="no",
            quality="excellent",
        )
        add_hydration(REFERENCE_DATE, 500)
        add_hydration(REFERENCE_DATE, 750, consumed_at=time(18, 0))
        summary = get_nutrition_summary_for_date(REFERENCE_DATE)

    assert summary["meals"] == 2
    assert summary["hydration_ml"] == 1250
    assert summary["hydration"] == "1,2 L"
    assert summary["protein_meals"] == 1
    assert summary["produce_meals"] == 1
    assert summary["quality_average"] == 90


def test_hydration_visual_format_handles_ml_and_liters():
    assert format_hydration(500) == "500 ml"
    assert format_hydration(1800) == "1,8 L"
    assert format_hydration(2500) == "2,5 L"


def test_provisional_nutrition_score_is_limited_to_twenty(app):
    with app.app_context():
        meals = [
            add_meal(
                REFERENCE_DATE,
                meal_type=meal_type,
                meal_time=time(8 + index * 3, 0),
                quality="excellent",
            )
            for index, meal_type in enumerate(
                ("breakfast", "lunch", "snack", "dinner")
            )
        ]
        hydration = [add_hydration(REFERENCE_DATE, 2000)]
        score = calculate_provisional_nutrition_score(meals, hydration)

    assert score == 20


def test_nutrition_page_comparison_and_unknown_translation(app):
    with app.app_context():
        add_meal(
            REFERENCE_DATE - timedelta(days=1),
            protein="no",
            produce="no",
            quality="regular",
        )
        add_hydration(REFERENCE_DATE - timedelta(days=1), 500)
        add_meal(
            REFERENCE_DATE,
            meal_type="snack",
            protein="unknown",
            produce="unknown",
            quality="good",
        )
        add_meal(
            REFERENCE_DATE,
            meal_type="dinner",
            meal_time=time(19, 0),
            quality="excellent",
        )
        add_hydration(REFERENCE_DATE, 1500)
        data = get_nutrition_page_data(REFERENCE_DATE)

    assert data["metrics"][0]["value"] == "2 refeições"
    assert data["metrics"][0]["helper"] == "+1 vs ontem"
    assert data["metrics"][2]["helper"] == "+1 L vs ontem"
    assert data["metrics"][3]["value"] == "90%"
    assert "Proteína: Não sei" in data["list"]["items"][0]["meta"]
    assert "Frutas/verduras: Não sei" in data["list"]["items"][0]["meta"]


def test_weekly_nutrition_data_contains_meals_and_water(app):
    with app.app_context():
        add_meal(REFERENCE_DATE - timedelta(days=6))
        add_hydration(REFERENCE_DATE - timedelta(days=6), 500)
        add_meal(REFERENCE_DATE)
        add_meal(
            REFERENCE_DATE,
            meal_type="dinner",
            meal_time=time(19, 0),
        )
        add_hydration(REFERENCE_DATE, 2000)
        weekly = get_weekly_nutrition_data(REFERENCE_DATE)

    assert len(weekly) == 7
    assert weekly[1]["score"] == 0
    assert weekly[-1]["meals"] == 2
    assert weekly[-1]["hydration"] == "2 L"
    assert weekly[-1]["tooltip_lines"] == ["2 refeições", "Água: 2 L"]


def test_nutrition_indicators_use_real_thirty_day_data(app):
    start_date = REFERENCE_DATE - timedelta(days=29)
    with app.app_context():
        add_meal(REFERENCE_DATE, protein="yes", produce="yes", quality="good")
        add_meal(
            REFERENCE_DATE,
            meal_type="snack",
            meal_time=time(16, 0),
            protein="no",
            produce="unknown",
            quality="excellent",
        )
        add_hydration(REFERENCE_DATE, 3000)
        indicators = get_nutrition_indicators(start_date, REFERENCE_DATE)

    assert indicators[0]["score"] == 50
    assert indicators[1]["score"] == 50
    assert indicators[2]["value"] == "100 ml por dia"
    assert indicators[3]["score"] == 3
    assert indicators[4]["score"] == 90
    assert all(item["name"] != "Excessos" for item in indicators)


def test_monthly_nutrition_heatmap_uses_daily_score(app):
    with app.app_context():
        add_meal(
            date(2026, 7, 2),
            quality="excellent",
        )
        add_hydration(date(2026, 7, 2), 2000)
        for index, meal_type in enumerate(("snack", "dinner"), start=1):
            add_meal(
                date(2026, 7, 2),
                meal_type=meal_type,
                meal_time=time(12 + index * 3, 0),
                quality="excellent",
            )
        heatmap = get_monthly_nutrition_heatmap(2026, 7, REFERENCE_DATE)

    assert heatmap["month"] == "Julho de 2026"
    assert heatmap["days"][1]["level"] == 5
    assert "3 refeições" in heatmap["days"][1]["title"]
    assert "Água: 2 L" in heatmap["days"][1]["title"]
    assert heatmap["days"][26]["is_highlighted"] is True

