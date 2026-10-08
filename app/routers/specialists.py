from fastapi import APIRouter, Depends
from fastapi import Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Specialist

from app.auth import get_current_user

router = APIRouter(
    prefix="/specialists",
    tags=["Specialists"]
)


@router.get("/")
def get_specialists(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = db.query(Specialist)

    if search:
        query = query.filter(
            Specialist.name.ilike(f"%{search}%")
        )

    total = query.count()

    specialists = (
        query
        .order_by(Specialist.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": specialists,
        "page": page,
        "page_size": page_size,
        "total": total
    }