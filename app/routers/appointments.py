from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Appointment, Slot, Service, Specialist

from app.auth import get_current_user

from app.models import AppointmentCreate 

router = APIRouter(
    prefix="/appointments",
    tags=["Appointments"]
)


# Создание записи
@router.post("/")
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    slot = db.query(Slot).filter(Slot.id == payload.slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    service = db.query(Service).filter(Service.id == payload.service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    if slot.status != "free":
        raise HTTPException(status_code=400, detail="Slot is not available")

    start_minutes = slot.start_time.hour * 60 + slot.start_time.minute
    end_minutes = slot.end_time.hour * 60 + slot.end_time.minute
    if (end_minutes - start_minutes) < service.duration_minutes:
        raise HTTPException(
            status_code=400,
            detail="Slot is too short for this service",
        )

    appointment = Appointment(
        slot_id=slot.id,
        service_id=service.id,
        client_name=payload.client_name,
    )
    slot.status = "booked"

    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


# Получение списка записей
@router.get("/")
def get_appointments(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = db.query(Appointment)

    if status:
        query = query.filter(
            Appointment.status == status
        )

    total = query.count()

    appointments = (
        query
        .order_by(Appointment.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": appointments,
        "page": page,
        "page_size": page_size,
        "total": total
    }

# Карточка записи со связанными сущностями
@router.get("/{appointment_id}")
def get_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    appointment = (
        db.query(Appointment)
        .filter(Appointment.id == appointment_id)
        .first()
    )

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found",
        )

    slot = (
        db.query(Slot)
        .filter(Slot.id == appointment.slot_id)
        .first()
    )
    service = (
        db.query(Service)
        .filter(Service.id == appointment.service_id)
        .first()
    )
    specialist = (
        db.query(Specialist)
        .filter(Specialist.id == slot.specialist_id)
        .first()
        if slot
        else None
    )

    return {
        "id": appointment.id,
        "client_name": appointment.client_name,
        "status": appointment.status,
        "created_at": appointment.created_at,
        "slot": (
            {
                "id": slot.id,
                "slot_date": slot.slot_date,
                "start_time": slot.start_time,
                "end_time": slot.end_time,
                "status": slot.status,
            }
            if slot
            else None
        ),
        "service": (
            {
                "id": service.id,
                "name": service.name,
                "duration_minutes": service.duration_minutes,
            }
            if service
            else None
        ),
        "specialist": (
            {
                "id": specialist.id,
                "name": specialist.name,
                "specialization": specialist.specialization,
            }
            if specialist
            else None
        ),
    }

# Отмена записи
@router.delete("/{appointment_id}")
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found"
        )

    if appointment.status == "cancelled":
        raise HTTPException(
            status_code=400,
            detail="Appointment is already cancelled"
        )

    slot = db.query(Slot).filter(
        Slot.id == appointment.slot_id
    ).first()

    appointment.status = "cancelled"

    if slot:
        slot.status = "free"

    db.commit()

    return {
        "message": "Appointment cancelled",
        "appointment_id": appointment.id
    }