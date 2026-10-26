from app.extensions import db
from app.models.base import RecordMixin


class HydrationRecord(RecordMixin, db.Model):
    __tablename__ = "hydration_records"
    __table_args__ = (
        db.CheckConstraint("amount_ml > 0", name="ck_hydration_amount_positive"),
    )

    amount_ml = db.Column(db.Integer, nullable=False)
    consumed_at = db.Column(db.Time, nullable=False)
    notes = db.Column(db.String(2000))
