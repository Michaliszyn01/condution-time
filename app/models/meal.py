from app.extensions import db
from app.models.base import RecordMixin


class MealRecord(RecordMixin, db.Model):
    __tablename__ = "meal_records"

    meal_type = db.Column(db.String(20), nullable=False)
    meal_time = db.Column(db.Time, nullable=False)
    foods_text = db.Column(db.String(2000), nullable=False)
    approximate_amount = db.Column(db.String(500))
    has_protein = db.Column(db.String(10), nullable=False)
    has_fruits_or_vegetables = db.Column(db.String(10), nullable=False)
    perceived_quality = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.String(2000))
