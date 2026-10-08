"""
Тесты бизнес-правил варианта 3.
Никакого запущенного сервера: TestClient общается с ASGI-приложением
через httpx.ASGITransport напрямую.
запуск: pytest -v
"""

from datetime import date, time

import pytest

from app.models import Appointment, Service, Slot, Specialist


# ---------- фабрики тестовых данных ----------

def make_specialist(db, name="Eirin", specialization="Diagnostics"):
    obj = Specialist(name=name, specialization=specialization)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def make_service(db, name="Consultation", duration_minutes=30):
    obj = Service(name=name, duration_minutes=duration_minutes)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def make_slot(
    db,
    specialist,
    slot_date=date(2026, 1, 15),
    start_time=time(9, 0),
    end_time=time(10, 0),
    status="free",
):
    obj = Slot(
        specialist_id=specialist.id,
        slot_date=slot_date,
        start_time=start_time,
        end_time=end_time,
        status=status,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def make_appointment(db, slot, service, client_name="Reisen", status="active"):
    obj = Appointment(
        slot_id=slot.id,
        service_id=service.id,
        client_name=client_name,
        status=status,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# ---------- правило 1: бронирование свободного слота ----------

def test_create_appointment_on_free_slot_succeeds(client, db_session):
    """Свободный слот подходящей длительности → запись создаётся, слот занят."""
    specialist = make_specialist(db_session)
    service = make_service(db_session, duration_minutes=30)
    slot = make_slot(db_session, specialist)  # 09:00–10:00 = 60 мин

    response = client.post(
    "/appointments/",
    json={"slot_id": slot.id, "service_id": service.id, "client_name": "Alice"},
)

    assert response.status_code == 200
    body = response.json()
    assert body["slot_id"] == slot.id
    assert body["service_id"] == service.id
    assert body["client_name"] == "Alice"
    assert body["status"] == "active"

    db_session.refresh(slot)
    assert slot.status == "booked"


# ---------- правило 2: слот не найден ----------

def test_create_appointment_with_unknown_slot_returns_404(client, db_session):
    service = make_service(db_session)

    response = client.post(
        "/appointments/",
        json={
            "slot_id": 999_999,
            "service_id": service.id,
            "client_name": "Alice",
        },
    )

    assert response.status_code == 404
    assert "Slot not found" in response.json()["detail"]


# ---------- правило 3: услуга не найдена ----------

def test_create_appointment_with_unknown_service_returns_404(client, db_session):
    specialist = make_specialist(db_session)
    slot = make_slot(db_session, specialist)

    response = client.post(
        "/appointments/",
        json={
            "slot_id": slot.id,
            "service_id": 999_999,
            "client_name": "Alice",
        },
    )

    assert response.status_code == 404
    assert "Service not found" in response.json()["detail"]


# ---------- правило 4: слот уже занят ----------

def test_create_appointment_on_booked_slot_returns_400(client, db_session):
    """Наложение на существующую запись запрещено."""
    specialist = make_specialist(db_session)
    service = make_service(db_session)
    slot = make_slot(db_session, specialist, status="booked")

    response = client.post(
        "/appointments/",
        json={
            "slot_id": slot.id,
            "service_id": service.id,
            "client_name": "Alice",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Slot is not available"

    db_session.refresh(slot)
    assert slot.status == "booked"  # состояние не испорчено


# ---------- правило 5: слот короче услуги ----------

def test_create_appointment_when_slot_too_short_returns_400(client, db_session):
    specialist = make_specialist(db_session)
    service = make_service(db_session, duration_minutes=120)
    slot = make_slot(
        db_session,
        specialist,
        start_time=time(9, 0),
        end_time=time(10, 0),  # 60 минут < 120
    )

    response = client.post(
        "/appointments/",
        json={
            "slot_id": slot.id,
            "service_id": service.id,
            "client_name": "Alice",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Slot is too short for this service"

    db_session.refresh(slot)
    assert slot.status == "free"  # слот остался свободным


# ---------- правило 6: отмена возвращает слот ----------

def test_cancel_appointment_frees_slot(client, db_session):
    specialist = make_specialist(db_session)
    service = make_service(db_session)
    slot = make_slot(db_session, specialist, status="booked")
    appointment = make_appointment(db_session, slot, service)

    response = client.delete(f"/appointments/{appointment.id}")

    assert response.status_code == 200
    assert response.json()["appointment_id"] == appointment.id

    db_session.refresh(appointment)
    db_session.refresh(slot)
    assert appointment.status == "cancelled"
    assert slot.status == "free"


# ---------- правило 7: повторная отмена запрещена ----------

def test_cancel_already_cancelled_appointment_returns_400(client, db_session):
    specialist = make_specialist(db_session)
    service = make_service(db_session)
    slot = make_slot(db_session, specialist, status="free")
    appointment = make_appointment(db_session, slot, service, status="cancelled")

    response = client.delete(f"/appointments/{appointment.id}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Appointment is already cancelled"


# ---------- правило 8: отмена несуществующей записи ----------

def test_cancel_unknown_appointment_returns_404(client):
    response = client.delete("/appointments/424242")

    assert response.status_code == 404
    assert response.json()["detail"] == "Appointment not found"


# ---------- правило 9: сводка считает долю отменённых ----------

def test_summary_cancellation_share(client, db_session):
    """
    Сводка показывает загрузку специалистов за период
    и долю отменённых записей.
    """
    specialist = make_specialist(db_session)
    service = make_service(db_session)
    day = date(2026, 1, 15)

    slot1 = make_slot(db_session, specialist, slot_date=day, start_time=time(9, 0), end_time=time(10, 0), status="booked")
    slot2 = make_slot(db_session, specialist, slot_date=day, start_time=time(10, 0), end_time=time(11, 0), status="free")
    slot3 = make_slot(db_session, specialist, slot_date=day, start_time=time(11, 0), end_time=time(12, 0), status="free")
    slot4 = make_slot(db_session, specialist, slot_date=day, start_time=time(12, 0), end_time=time(13, 0), status="free")

    make_appointment(db_session, slot1, service, status="active")
    make_appointment(db_session, slot2, service, status="cancelled")

    response = client.get(
        "/summary/",
        params={"date_from": day.isoformat(), "date_to": day.isoformat()},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1

    row = items[0]
    assert row["specialist_id"] == specialist.id
    assert row["total_slots"] == 4
    assert row["booked_slots"] == 1
    assert row["cancelled_slots"] == 1
    # 1 отмена из 2 записей = 0.5
    assert row["cancellation_share"] == 0.5


# ---------- правило 10: фильтр по статусу в списке записей ----------

def test_list_appointments_filters_by_status(client, db_session):
    specialist = make_specialist(db_session)
    service = make_service(db_session)
    slot_a = make_slot(db_session, specialist, start_time=time(9, 0), end_time=time(10, 0))
    slot_b = make_slot(db_session, specialist, start_time=time(10, 0), end_time=time(11, 0))

    make_appointment(db_session, slot_a, service, status="active")
    make_appointment(db_session, slot_b, service, status="cancelled")

    response = client.get("/appointments/", params={"status": "active"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "active"