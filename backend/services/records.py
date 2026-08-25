from sqlalchemy import select, desc, asc, or_

from db.session import get_db_session
from db.models import HealthRecord, StaffAssignment
from services.bmi import calc_bmi
from services.parsing import parse_date


def list_records(get_user_ids, search: str = "", sort: str = "record_date desc", filters=None):
    session = get_db_session()
    try:
        filters = filters or {}
        from_date = filters.get("from_date")
        to_date = filters.get("to_date")

        # get_user_ids can be either a callable or a precomputed list
        user_ids = get_user_ids() if callable(get_user_ids) else get_user_ids


        q = select(HealthRecord).where(
            HealthRecord.user_id.in_(user_ids)
        )

        if search:
            like = f"%{search}%"
            q = q.where(
                or_(
                    HealthRecord.food.ilike(like),
                    HealthRecord.exercise.ilike(like),
                )
            )

        if from_date:
            q = q.where(HealthRecord.record_date >= str(from_date))

        if to_date:
            q = q.where(HealthRecord.record_date <= str(to_date))

        if sort == "record_date asc":
            q = q.order_by(asc(HealthRecord.record_date))
        else:
            q = q.order_by(desc(HealthRecord.record_date))

        rows = session.execute(q).scalars().all()

        return [
            {
                "id": r.id,
                "user_id": r.user_id,
                "record_date": r.record_date,
                "height_cm": r.height_cm,
                "weight_kg": r.weight_kg,
                "bmi": r.bmi,
                "food": r.food,
                "calories": r.calories,
                "water_liters": r.water_liters,
                "sleep_hours": r.sleep_hours,
                "exercise": r.exercise,
            }
            for r in rows
        ]

    finally:
        session.close()


def create_record_from_form(rec: dict):
    session = get_db_session()
    try:
        iso_date = parse_date(rec.get("record_date"))
        if not iso_date:
            raise ValueError("Invalid date. Use YYYY-MM-DD")

        bmi = calc_bmi(rec.get("height_cm"), rec.get("weight_kg"))

        record = HealthRecord(
            user_id=rec["target_user_id"],
            record_date=iso_date,
            height_cm=rec.get("height_cm"),
            weight_kg=rec.get("weight_kg"),
            bmi=bmi,
            food=rec.get("food"),
            calories=rec.get("calories"),
            water_liters=rec.get("water_liters"),
            sleep_hours=rec.get("sleep_hours"),
            exercise=rec.get("exercise"),
            created_by_user_id=rec.get("created_by_user_id"),
        )

        session.add(record)
        session.commit()

        return record.id

    finally:
        session.close()


def update_record_from_form(record_id: int, rec: dict, user_ids):
    """Update an existing health record.

    Args:
        record_id: ID of the record to update
        rec: dict of fields to update (record_date, height_cm, weight_kg, etc.)
        user_ids: list (or callable) of user_ids the current user may edit

    Returns:
        The updated record id

    Raises:
        ValueError: if record not found or not in the user's scope
    """
    session = get_db_session()
    try:
        ids = user_ids() if callable(user_ids) else user_ids

        record = session.execute(
            select(HealthRecord).where(
                HealthRecord.id == record_id,
                HealthRecord.user_id.in_(ids),
            )
        ).scalar_one_or_none()

        if not record:
            raise ValueError("Record not found")

        iso_date = parse_date(rec.get("record_date"))
        if not iso_date:
            raise ValueError("Invalid date. Use YYYY-MM-DD")

        new_height = rec.get("height_cm") if rec.get("height_cm") is not None else record.height_cm
        new_weight = rec.get("weight_kg") if rec.get("weight_kg") is not None else record.weight_kg
        bmi = calc_bmi(new_height, new_weight)

        record.record_date = iso_date
        record.height_cm = new_height
        record.weight_kg = new_weight
        record.bmi = bmi
        record.food = rec.get("food", record.food)
        record.calories = rec.get("calories", record.calories)
        record.water_liters = rec.get("water_liters", record.water_liters)
        record.sleep_hours = rec.get("sleep_hours", record.sleep_hours)
        record.exercise = rec.get("exercise", record.exercise)

        session.commit()
        return record.id

    finally:
        session.close()


def delete_record_by_id(record_id: int, user_ids):
    """Delete a health record.

    Args:
        record_id: ID of the record to delete
        user_ids: list (or callable) of user_ids the current user may edit

    Returns:
        True if deleted, False if not found

    Raises:
        ValueError: if record not found or not in scope
    """
    session = get_db_session()
    try:
        ids = user_ids() if callable(user_ids) else user_ids

        record = session.execute(
            select(HealthRecord).where(
                HealthRecord.id == record_id,
                HealthRecord.user_id.in_(ids),
            )
        ).scalar_one_or_none()

        if not record:
            raise ValueError("Record not found")

        session.delete(record)
        session.commit()
        return True

    finally:
        session.close()
