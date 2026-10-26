from datetime import date, time
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models import (
    HydrationRecord,
    MealRecord,
    SessionRecord,
    SleepRecord,
    StudyRecord,
    TrainingRecord,
)
from app.services.scoring_service import (
    calculate_computer_score,
    calculate_daily_score,
    calculate_nutrition_score,
    calculate_session_bonus,
    calculate_sleep_score,
    calculate_study_score,
    calculate_training_score,
    get_score_coverage,
    get_score_message,
)


REFERENCE_DATE = date(2026, 7, 27)


def criterion(result: dict, key: str) -> dict:
    return next(item for item in result["breakdown"] if item["key"] == key)


def study(**overrides):
    values = {
        "record_date": REFERENCE_DATE,
        "subject": "Matemática",
        "topic": "Geometria",
        "duration_minutes": 60,
        "questions_count": 0,
        "correct_answers": None,
        "focus_quality": "good",
        "learned_text": "Aprendi o conteúdo.",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def training(**overrides):
    values = {
        "record_date": REFERENCE_DATE,
        "training_type": "strength",
        "activity_name": "Treino A",
        "duration_minutes": 40,
        "intensity": 6,
        "perceived_performance": "good",
        "exercises_text": "Supino",
        "discomfort_level": "none",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def sleep(**overrides):
    values = {
        "sleep_start": time(23, 0),
        "sleep_end": time(7, 0),
        "duration_minutes": 480,
        "perceived_quality": "good",
        "awakenings_count": 1,
        "woke_restored": "yes",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def meal(**overrides):
    values = {
        "meal_type": "lunch",
        "meal_time": time(12, 0),
        "foods_text": "Arroz, feijão e salada",
        "perceived_quality": "good",
        "has_protein": "yes",
        "has_fruits_or_vegetables": "yes",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def hydration(amount_ml: int):
    return SimpleNamespace(amount_ml=amount_ml)


def session(**overrides):
    values = {
        "status": "completed",
        "focus_percentage": 80,
        "result_text": "Objetivo concluído.",
        "learned_text": "Reflexão.",
        "difficulty_text": None,
        "self_rating": None,
        "actual_duration_seconds": 600,
        "productive_seconds": 500,
        "distracted_seconds": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_unevaluated_categories_do_not_receive_zero_as_an_evaluation():
    results = [
        calculate_study_score([]),
        calculate_training_score([]),
        calculate_sleep_score(None),
        calculate_nutrition_score([], []),
        calculate_computer_score(None),
    ]

    assert all(result["evaluated"] is False for result in results)
    assert all(result["score"] == 0 for result in results)
    assert all(result["max_score"] == 20 for result in results)


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(0, 0), (1, 2), (29, 2), (30, 4), (59, 4), (60, 6), (89, 6), (90, 7), (119, 7), (120, 8)],
)
def test_study_duration_bands(minutes, expected):
    result = calculate_study_score([study(duration_minutes=minutes)])
    assert criterion(result, "duration")["score"] == expected


@pytest.mark.parametrize(
    ("focus", "expected"),
    [("low", 0), ("regular", 2), ("good", 3), ("very_good", 4), ("excellent", 5)],
)
def test_study_focus_bands(focus, expected):
    result = calculate_study_score([study(focus_quality=focus)])
    assert criterion(result, "focus")["score"] == expected


@pytest.mark.parametrize(
    ("questions", "expected"),
    [(0, 0), (1, 1), (5, 1), (6, 2), (15, 2), (16, 3), (30, 3), (31, 4)],
)
def test_study_practice_bands(questions, expected):
    result = calculate_study_score(
        [study(questions_count=questions, correct_answers=questions)]
    )
    assert criterion(result, "practice")["score"] == expected


@pytest.mark.parametrize(
    ("questions", "correct", "expected"),
    [(None, None, 0), (10, 3, 0), (10, 4, 1), (10, 5, 1), (10, 6, 2)],
)
def test_study_result_bands_and_neutral_state(questions, correct, expected):
    result = calculate_study_score(
        [study(questions_count=questions, correct_answers=correct)]
    )
    item = criterion(result, "result")
    assert item["score"] == expected
    assert item.get("neutral", False) is (questions is None)


def test_study_complete_record_and_maximum():
    incomplete = calculate_study_score([study(learned_text=None)])
    maximum = calculate_study_score(
        [
            study(
                duration_minutes=120,
                focus_quality="excellent",
                questions_count=31,
                correct_answers=31,
            )
        ]
    )
    assert criterion(incomplete, "complete_record")["score"] == 0
    assert maximum["score"] == 20


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(1, 2), (19, 2), (20, 4), (39, 4), (40, 5), (59, 5), (60, 6)],
)
def test_training_duration_bands(minutes, expected):
    result = calculate_training_score([training(duration_minutes=minutes)])
    assert criterion(result, "duration")["score"] == expected


@pytest.mark.parametrize(
    ("intensity", "expected"),
    [(1, 1), (2, 1), (3, 2), (4, 2), (5, 4), (8, 4), (9, 3), (10, 3)],
)
def test_training_intensity_bands(intensity, expected):
    result = calculate_training_score([training(intensity=intensity)])
    assert criterion(result, "intensity")["score"] == expected


@pytest.mark.parametrize(
    ("performance", "expected"),
    [("bad", 0), ("regular", 1), ("good", 2), ("very_good", 3), ("excellent", 3)],
)
def test_training_performance_bands(performance, expected):
    result = calculate_training_score(
        [training(perceived_performance=performance)]
    )
    assert criterion(result, "performance")["score"] == expected


def test_training_completion_approximation_and_consistency():
    no_exercises = calculate_training_score(
        [training(exercises_text=None)],
        [training(record_date=REFERENCE_DATE)],
    )
    four_days = [
        training(record_date=date(2026, 7, day)) for day in (24, 25, 26, 27)
    ]
    maximum = calculate_training_score(
        [
            training(
                duration_minutes=60,
                intensity=8,
                perceived_performance="excellent",
            )
        ],
        four_days,
    )

    assert criterion(no_exercises, "completion")["score"] == 1
    assert criterion(no_exercises, "completion")["approximate"] is True
    assert criterion(maximum, "weekly_consistency")["score"] == 3
    assert maximum["score"] == 20


@pytest.mark.parametrize(("days", "expected"), [(1, 0), (2, 1), (3, 2), (4, 3)])
def test_training_consistency_bands(days, expected):
    weekly = [
        training(record_date=REFERENCE_DATE.replace(day=27 - index))
        for index in range(days)
    ]
    result = calculate_training_score([weekly[0]], weekly)
    assert criterion(result, "weekly_consistency")["score"] == expected


def test_training_discomfort_adds_warning_without_penalty():
    safe = calculate_training_score([training()])
    discomfort = calculate_training_score(
        [training(discomfort_level="strong")]
    )

    assert discomfort["score"] == safe["score"]
    assert discomfort["warnings"]


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(287, 0), (288, 3), (359, 3), (360, 6), (431, 6), (432, 8), (528, 8), (529, 6), (600, 6), (601, 4)],
)
def test_sleep_duration_bands(minutes, expected):
    result = calculate_sleep_score(sleep(duration_minutes=minutes), 480)
    assert criterion(result, "duration")["score"] == expected


@pytest.mark.parametrize(
    ("quality", "expected"),
    [("terrible", 0), ("bad", 1), ("regular", 3), ("good", 4), ("excellent", 5)],
)
def test_sleep_quality_bands(quality, expected):
    result = calculate_sleep_score(sleep(perceived_quality=quality))
    assert criterion(result, "quality")["score"] == expected


@pytest.mark.parametrize(
    ("restored", "expected"),
    [("no", 0), ("partially", 2), ("yes", 4)],
)
def test_sleep_restored_bands(restored, expected):
    result = calculate_sleep_score(sleep(woke_restored=restored))
    assert criterion(result, "restored")["score"] == expected


@pytest.mark.parametrize(
    ("awakenings", "expected"),
    [(0, 2), (1, 1), (2, 1), (3, 0)],
)
def test_sleep_continuity_bands(awakenings, expected):
    result = calculate_sleep_score(sleep(awakenings_count=awakenings))
    assert criterion(result, "continuity")["score"] == expected


def test_sleep_configurable_target_and_maximum(app):
    with app.app_context():
        app.config["DEFAULT_SLEEP_TARGET_MINUTES"] = 600
        configured = calculate_sleep_score(sleep(duration_minutes=540))
        maximum = calculate_sleep_score(
            sleep(
                duration_minutes=600,
                perceived_quality="excellent",
                woke_restored="yes",
                awakenings_count=0,
            )
        )

    assert criterion(configured, "duration")["score"] == 8
    assert maximum["score"] == 20


@pytest.mark.parametrize(
    ("meal_count", "expected"),
    [(0, 0), (1, 1), (2, 2), (3, 3), (5, 3)],
)
def test_nutrition_regularity_bands(meal_count, expected):
    result = calculate_nutrition_score([meal() for _ in range(meal_count)], [hydration(1)])
    assert criterion(result, "regularity")["score"] == expected


@pytest.mark.parametrize(
    ("quality", "expected"),
    [("very_bad", 0), ("bad", 1), ("regular", 3), ("good", 4), ("excellent", 5)],
)
def test_nutrition_quality_bands(quality, expected):
    result = calculate_nutrition_score([meal(perceived_quality=quality)], [])
    assert criterion(result, "quality")["score"] == expected


def test_nutrition_protein_produce_unknown_and_maximum():
    unknown = calculate_nutrition_score(
        [
            meal(
                has_protein="unknown",
                has_fruits_or_vegetables="unknown",
            )
        ],
        [],
    )
    maximum = calculate_nutrition_score(
        [
            meal(meal_type="breakfast", perceived_quality="excellent"),
            meal(meal_type="lunch", perceived_quality="excellent"),
            meal(meal_type="dinner", perceived_quality="excellent"),
        ],
        [hydration(2000)],
    )

    assert criterion(unknown, "protein")["score"] == 0
    assert criterion(unknown, "produce")["score"] == 0
    assert "neutra" in criterion(unknown, "protein")["detail"]
    assert maximum["score"] == 20


@pytest.mark.parametrize(("yes_count", "expected"), [(0, 0), (1, 2), (2, 4)])
def test_nutrition_protein_and_produce_bands(yes_count, expected):
    meals = [
        meal(
            has_protein="yes" if index < yes_count else "no",
            has_fruits_or_vegetables="yes" if index < yes_count else "no",
        )
        for index in range(2)
    ]
    result = calculate_nutrition_score(meals, [])
    assert criterion(result, "protein")["score"] == expected
    assert criterion(result, "produce")["score"] == expected


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(0, 0), (799, 0), (800, 1), (1399, 1), (1400, 2), (1999, 2), (2000, 3), (4000, 3)],
)
def test_nutrition_hydration_bands(amount, expected):
    result = calculate_nutrition_score([], [hydration(amount)], 2000)
    assert criterion(result, "hydration")["score"] == expected


@pytest.mark.parametrize(
    ("productive", "distracted", "expected"),
    [(24, 76, 0), (25, 75, 3), (40, 60, 5), (55, 45, 7), (70, 30, 9), (85, 15, 10)],
)
def test_computer_productive_ratio_bands(productive, distracted, expected):
    result = calculate_computer_score(
        {
            "productive_seconds": productive,
            "distracted_seconds": distracted,
        }
    )
    assert criterion(result, "productive_ratio")["score"] == expected


@pytest.mark.parametrize(
    ("distracted", "expected"),
    [(100, 4), (101, 2), (125, 2), (126, 1), (150, 1), (151, 0)],
)
def test_computer_distraction_bands(distracted, expected):
    result = calculate_computer_score(
        {
            "productive_seconds": 100,
            "distracted_seconds": distracted,
        },
        100,
    )
    assert criterion(result, "controlled_distraction")["score"] == expected


@pytest.mark.parametrize(("sessions", "expected"), [(0, 0), (1, 2), (2, 4)])
def test_computer_focused_session_bands(sessions, expected):
    result = calculate_computer_score(
        {
            "productive_seconds": 100,
            "distracted_seconds": 1,
            "focused_sessions_count": sessions,
        }
    )
    assert criterion(result, "focused_sessions")["score"] == expected


@pytest.mark.parametrize(
    ("classified", "expected"),
    [(49, 0), (50, 1), (79, 1), (80, 2)],
)
def test_computer_classification_bands(classified, expected):
    result = calculate_computer_score(
        {
            "productive_seconds": 100,
            "distracted_seconds": 1,
            "classified_apps_percentage": classified,
        }
    )
    assert criterion(result, "app_classification")["score"] == expected


def test_computer_neutral_time_is_ignored_and_score_is_limited():
    result = calculate_computer_score(
        {
            "productive_seconds": 850,
            "distracted_seconds": 150,
            "neutral_seconds": 100_000,
            "focused_sessions_count": 2,
            "classified_apps_percentage": 100,
        }
    )
    assert criterion(result, "productive_ratio")["score"] == 10
    assert result["score"] == 20


def test_session_bonus_criteria_and_duration_do_not_change_it():
    short = calculate_session_bonus([session(actual_duration_seconds=1)])
    long = calculate_session_bonus(
        [
            session(
                actual_duration_seconds=100_000,
                productive_seconds=90_000,
                distracted_seconds=10_000,
            )
        ]
    )
    cancelled = calculate_session_bonus([session(status="cancelled")])

    assert short["score"] == 5
    assert long["score"] == 5
    assert cancelled["score"] == 0
    assert short["sessions"][0]["score"] == 5


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"status": "configured"}, 0),
        ({"focus_percentage": 69}, 4),
        ({"result_text": None}, 4),
        ({"learned_text": None}, 4),
    ],
)
def test_session_bonus_each_criterion(overrides, expected):
    result = calculate_session_bonus([session(**overrides)])
    assert result["sessions"][0]["score"] == expected


def test_session_bonus_has_daily_limit_of_ten():
    result = calculate_session_bonus([session(), session(), session()])
    assert result["score"] == 10


def test_score_coverage_and_messages():
    categories = {
        name: {"evaluated": name != "computer"}
        for name in ("study", "training", "sleep", "nutrition", "computer")
    }
    assert get_score_coverage(categories) == {
        "evaluated_categories": 4,
        "total_categories": 5,
        "coverage_percentage": 80,
    }
    assert get_score_coverage({"study": {"evaluated": True}})["total_categories"] == 5
    assert get_score_message(39) == "Seu dia ainda precisa de atenção."
    assert get_score_message(40) == "Você começou, mas ainda pode avançar."
    assert get_score_message(60) == "Bom progresso no dia."
    assert get_score_message(75) == "Seu dia está muito bom."
    assert get_score_message(90) == "Excelente equilíbrio hoje."
    assert get_score_message(101) == "Dia excepcional. Você superou sua meta."


def add_daily_records(*, include_session: bool = False):
    db.session.add_all(
        [
            StudyRecord(
                record_date=REFERENCE_DATE,
                subject="Matemática",
                topic="Geometria",
                duration_minutes=120,
                questions_count=31,
                correct_answers=31,
                focus_quality="excellent",
                learned_text="Aprendizado",
                difficulty_text=None,
                record_origin="manual",
            ),
            TrainingRecord(
                record_date=REFERENCE_DATE,
                training_type="strength",
                activity_name="Treino A",
                duration_minutes=60,
                intensity=8,
                perceived_performance="excellent",
                exercises_text="Supino",
                discomfort_level="none",
            ),
            SleepRecord(
                record_date=REFERENCE_DATE,
                sleep_start=time(23, 0),
                sleep_end=time(7, 0),
                duration_minutes=480,
                perceived_quality="excellent",
                awakenings_count=0,
                woke_restored="yes",
                record_origin="manual",
            ),
            MealRecord(
                record_date=REFERENCE_DATE,
                meal_type="breakfast",
                meal_time=time(8, 0),
                foods_text="Ovos e fruta",
                has_protein="yes",
                has_fruits_or_vegetables="yes",
                perceived_quality="excellent",
            ),
            MealRecord(
                record_date=REFERENCE_DATE,
                meal_type="lunch",
                meal_time=time(12, 0),
                foods_text="Arroz, feijão e salada",
                has_protein="yes",
                has_fruits_or_vegetables="yes",
                perceived_quality="excellent",
            ),
            MealRecord(
                record_date=REFERENCE_DATE,
                meal_type="dinner",
                meal_time=time(19, 0),
                foods_text="Sopa e frango",
                has_protein="yes",
                has_fruits_or_vegetables="yes",
                perceived_quality="excellent",
            ),
            HydrationRecord(
                record_date=REFERENCE_DATE,
                amount_ml=2000,
                consumed_at=time(18, 0),
            ),
            *[
                TrainingRecord(
                    record_date=date(2026, 7, day),
                    training_type="strength",
                    activity_name=f"Treino {day}",
                    duration_minutes=20,
                    intensity=6,
                    perceived_performance="good",
                    exercises_text="Exercícios",
                    discomfort_level="none",
                )
                for day in (24, 25, 26)
            ],
        ]
    )
    if include_session:
        db.session.add_all(
            [
                SessionRecord(
                    record_date=REFERENCE_DATE,
                    session_type="focus",
                    title=f"Sessão {index}",
                    related_category="study",
                    status="completed",
                    focus_percentage=90,
                    result_text="Objetivo concluído",
                    learned_text="Reflexão",
                )
                for index in range(2)
            ]
        )
    db.session.commit()


def test_daily_score_with_no_evaluated_category(app):
    with app.app_context():
        result = calculate_daily_score(REFERENCE_DATE)

    assert result["raw_base_score"] == 0
    assert result["raw_base_max"] == 0
    assert result["normalized_base_score"] == 0
    assert result["evaluated_categories"] == 0
    assert result["coverage_percentage"] == 0
    assert result["final_score"] == 0


def test_daily_score_normalizes_one_evaluated_category(app):
    with app.app_context():
        db.session.add(
            StudyRecord(
                record_date=REFERENCE_DATE,
                subject="Matemática",
                topic="Geometria",
                duration_minutes=60,
                questions_count=None,
                correct_answers=None,
                focus_quality="good",
                learned_text="Aprendizado",
                difficulty_text=None,
                record_origin="manual",
            )
        )
        db.session.commit()
        result = calculate_daily_score(REFERENCE_DATE)

    assert result["evaluated_categories"] == 1
    assert result["raw_base_max"] == 20
    assert result["normalized_base_score"] == result["raw_base_score"] * 5
    assert result["coverage_percentage"] == 20


def test_daily_score_normalizes_four_of_five_categories(app):
    with app.app_context():
        add_daily_records()
        result = calculate_daily_score(REFERENCE_DATE)

    assert result["evaluated_categories"] == 4
    assert result["total_categories"] == 5
    assert result["coverage_percentage"] == 80
    assert result["raw_base_max"] == 80
    assert result["normalized_base_score"] == round(
        result["raw_base_score"] / 80 * 100
    )
    assert result["categories"]["computer"]["evaluated"] is False


def test_daily_score_five_categories_bonus_and_maximum_110(app):
    with app.app_context():
        add_daily_records(include_session=True)
        result = calculate_daily_score(
            REFERENCE_DATE,
            {
                "productive_seconds": 850,
                "distracted_seconds": 150,
                "focused_sessions_count": 2,
                "classified_apps_percentage": 100,
            },
        )

    assert result["evaluated_categories"] == 5
    assert result["raw_base_score"] <= 100
    assert result["normalized_base_score"] <= 100
    assert result["session_bonus"] == 10
    assert result["final_score"] == 110
    assert result["max_final_score"] == 110
    assert result["day_closed"] is False
