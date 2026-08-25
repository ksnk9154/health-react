"""Deterministic, source-attributed overview derived from records and observations.

Every displayed value remains traceable to its source: each observation stores a
document_id, original filename, and page. The LLM is used only for explanation/
summarisation elsewhere — nothing here is LLM-generated, so no AI output can become
a stored medical fact.
"""
from collections import defaultdict
from db.session import get_db_session
from db.models import HealthRecord, HealthObservation, Document, WeightGoal
from sqlalchemy import select

_ALERT_STATUSES = {"HIGH", "LOW", "ABNORMAL"}


def _source_name(observation) -> str:
    """Resolve the original filename for an observation's source document."""
    try:
        return observation.document.original_filename if observation.document else None
    except Exception:
        return None


def build_overview(user_ids):
    session = get_db_session()
    try:
        records = session.execute(select(HealthRecord).where(HealthRecord.user_id.in_(user_ids)).order_by(HealthRecord.record_date)).scalars().all()
        observations = session.execute(select(HealthObservation).where(HealthObservation.user_id.in_(user_ids)).order_by(HealthObservation.observation_date)).scalars().all()
        docs = session.execute(select(Document.id).where(Document.user_id.in_(user_ids))).all()
        weight = [{"date": r.record_date, "value": r.weight_kg} for r in records if r.weight_kg is not None]

        # Categorised observations with full source attribution.
        categories = defaultdict(list)
        for o in observations:
            categories[o.category].append({
                "id": o.id, "name": o.name,
                "value": o.value_text or o.value_numeric, "unit": o.unit,
                "date": o.observation_date, "document_id": o.document_id,
                "document_name": _source_name(o), "source_page": o.source_page,
                "status": o.status, "reference_text": o.reference_text,
            })

        # Alerts come ONLY from statuses explicitly reported in the source document.
        alerts = [{
            "type": "REFERENCE_RANGE",
            "observation_id": o.id,
            "title": f"{o.name} is reported as {o.status.lower()}",
            "detail": f"{o.value_text or o.value_numeric} {o.unit or ''}",
            "document_id": o.document_id,
            "document_name": _source_name(o),
            "source_page": o.source_page,
            "date": o.observation_date,
        } for o in observations if o.status in _ALERT_STATUSES]

        # Historical comparison: previous vs current value for the same metric.
        comparisons = []
        grouped = defaultdict(list)
        for o in observations:
            if o.value_numeric is not None:
                grouped[(o.name, o.unit)].append(o)
        for (name, unit), values in grouped.items():
            if len(values) >= 2:
                prev, latest = values[-2], values[-1]
                comparisons.append({
                    "name": name, "unit": unit,
                    "previous": prev.value_numeric, "current": latest.value_numeric,
                    "change": round(latest.value_numeric - prev.value_numeric, 4),
                    "previous_document_id": prev.document_id,
                    "previous_document_name": _source_name(prev),
                    "previous_date": prev.observation_date,
                    "document_id": latest.document_id,
                    "document_name": _source_name(latest),
                    "date": latest.observation_date,
                })

        # Trend data for charts: only metrics with >= 2 numeric observations over time.
        trends = {}
        for (name, unit), values in grouped.items():
            if len(values) < 2:
                continue
            series = []
            for v in values:
                if v.value_numeric is None:
                    continue
                series.append({
                    "value": v.value_numeric, "date": v.observation_date, "unit": unit,
                    "document_id": v.document_id, "document_name": _source_name(v),
                    "source_page": v.source_page,
                })
            if len(series) >= 2:
                trends[name] = series

        latest_weight = weight[-1]["value"] if weight else None
        goal=session.execute(select(WeightGoal).where(WeightGoal.user_id.in_(user_ids))).scalars().first()
        goal_data=None if not goal else {"target_weight_kg":goal.target_weight_kg,"target_date":goal.target_date,"remaining_kg":round(latest_weight-goal.target_weight_kg,2) if latest_weight is not None else None}
        return {"metrics": {"latest_weight": latest_weight, "weight_change": (weight[-1]["value"]-weight[0]["value"]) if len(weight)>1 else None, "average_water": round(sum(r.water_liters for r in records if r.water_liters is not None)/max(1, sum(r.water_liters is not None for r in records)),2) if any(r.water_liters is not None for r in records) else None, "average_sleep": round(sum(r.sleep_hours for r in records if r.sleep_hours is not None)/max(1, sum(r.sleep_hours is not None for r in records)),2) if any(r.sleep_hours is not None for r in records) else None, "document_count": len(docs), "observation_count": len(observations)}, "weight_goal":goal_data, "weight_trend": weight, "categories": dict(categories), "alerts": alerts, "comparisons": comparisons, "trends": trends}
    finally: session.close()
