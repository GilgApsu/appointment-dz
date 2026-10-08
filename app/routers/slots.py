from datetime import date
from fastapi import Query
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Slot

from app.auth import get_current_user

router = APIRouter(
    prefix="/slots",
    tags=["Slots"]
)


@router.get("/")
def get_slots(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    specialist_id: int | None = None,
    slot_date: date | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = db.query(Slot)

    if specialist_id:
        query = query.filter(
            Slot.specialist_id == specialist_id
        )

    if slot_date:
        query = query.filter(
            Slot.slot_date == slot_date
        )

    if status:
        query = query.filter(
            Slot.status == status
        )

    total = query.count()

    slots = (
        query
        .order_by(Slot.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": slots,
        "page": page,
        "page_size": page_size,
        "total": total
    }