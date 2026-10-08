from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Specialist, Slot, Appointment

from app.auth import get_current_user

router = APIRouter(
    prefix="/summary",
    tags=["Summary"]
)


@router.get("/")
def get_summary(
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    specialists = db.query(Specialist).all()

    result = []

    for specialist in specialists:
        total_slots = (
            db.query(func.count(Slot.id))
            .filter(
                Slot.specialist_id == specialist.id,
                Slot.slot_date >= date_from,
                Slot.slot_date <= date_to
            )
            .scalar()
        )

        booked_slots = (
            db.query(func.count(Appointment.id))
            .join(Slot, Appointment.slot_id == Slot.id)
            .filter(
                Slot.specialist_id == specialist.id,
                Slot.slot_date >= date_from,
                Slot.slot_date <= date_to,
                Appointment.status == "active"
            )
            .scalar()
        )

        cancelled_slots = (
            db.query(func.count(Appointment.id))
            .join(Slot, Appointment.slot_id == Slot.id)
            .filter(
                Slot.specialist_id == specialist.id,
                Slot.slot_date >= date_from,
                Slot.slot_date <= date_to,
                Appointment.status == "cancelled"
            )
            .scalar()
        )

        total_appointments = booked_slots + cancelled_slots

        cancellation_share = (
            cancelled_slots / total_appointments
            if total_appointments > 0
            else 0
        )

        result.append({
            "specialist_id": specialist.id,
            "specialist_name": specialist.name,
            "specialization": specialist.specialization,
            "total_slots": total_slots,
            "booked_slots": booked_slots,
            "cancelled_slots": cancelled_slots,
            "cancellation_share": round(cancellation_share, 4)
        })

    return {
        "date_from": date_from,
        "date_to": date_to,
        "items": result
    }