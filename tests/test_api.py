"""
Тесты операций интерфейса (API contract tests).

Проверяют:
  - код ответа;
  - состав полей ответа;
  - поведение без авторизации (401);
  - поведение при неверных параметрах (422, 404, 400).

Сервер не запускается: TestClient общается с ASGI-приложением
через httpx напрямую.
запуск: pytest tests/test_api.py -v
"""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Appointment, Service, Slot, Specialist


# ---------------------------------------------------------------------------
# Локальные фабрики данных
# ---------------------------------------------------------------------------

def _make_specialist(db, name="Иванов Иван", specialization="Терапевт"):
    obj = Specialist(name=name, specialization=specialization)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def _make_service(db, name="Первичная консультация", duration_minutes=30):
    obj = Service(name=name, duration_minutes=duration_minutes)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def _make_slot(
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


def _make_appointment(db, slot, service, client_name="Клиент 1", status="active"):
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


# ---------------------------------------------------------------------------
# Фикстура «клиент без авторизации» (реальный get_current_user не подменяется)
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_unauth(db_session):
    """
    Клиент, у которого get_db подменён на тестовую сессию,
    а get_current_user НЕ подменён. Используется для проверки 401.
    """
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    # get_current_user не переопределяем — хотим видеть реальную реакцию
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ===========================================================================
# 1. Служебный эндпоинт
# ===========================================================================

def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ===========================================================================
# 2. /specialists
# ===========================================================================

def test_list_specialists_returns_paginated_payload(client, db_session):
    _make_specialist(db_session, name="Первый")
    _make_specialist(db_session, name="Второй")

    response = client.get("/specialists/")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "page", "page_size", "total"}
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 10

    item = body["items"][0]
    assert set(item.keys()) == {"id", "name", "specialization"}


def test_list_specialists_pagination(client, db_session):
    for i in range(5):
        _make_specialist(db_session, name=f"Специалист {i}")

    response = client.get("/specialists/", params={"page": 2, "page_size": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_list_specialists_search(client, db_session):
    _make_specialist(db_session, name="Иванов Иван")
    _make_specialist(db_session, name="Петров Пётр")

    response = client.get("/specialists/", params={"search": "Иванов"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Иванов Иван"


def test_list_specialists_unauthorized(client_unauth):
    response = client_unauth.get("/specialists/")
    assert response.status_code == 401


# ===========================================================================
# 3. /services
# ===========================================================================

def test_list_services_returns_paginated_payload(client, db_session):
    _make_service(db_session, name="Осмотр", duration_minutes=15)
    _make_service(db_session, name="Приём", duration_minutes=30)

    response = client.get("/services/")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "page", "page_size", "total"}
    assert body["total"] == 2

    item = body["items"][0]
    assert set(item.keys()) == {"id", "name", "duration_minutes"}


def test_list_services_search(client, db_session):
    _make_service(db_session, name="Первичная консультация")
    _make_service(db_session, name="Повторная консультация")
    _make_service(db_session, name="Осмотр")

    response = client.get("/services/", params={"search": "консультац"})

    assert response.status_code == 200
    assert response.json()["total"] == 2


def test_list_services_unauthorized(client_unauth):
    response = client_unauth.get("/services/")
    assert response.status_code == 401


# ===========================================================================
# 4. /slots
# ===========================================================================

def test_list_slots_returns_paginated_payload(client, db_session):
    spec = _make_specialist(db_session)
    _make_slot(db_session, spec, start_time=time(9, 0), end_time=time(9, 30))
    _make_slot(db_session, spec, start_time=time(9, 30), end_time=time(10, 0))

    response = client.get("/slots/")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "page", "page_size", "total"}
    assert body["total"] == 2

    item = body["items"][0]
    assert set(item.keys()) == {
        "id", "specialist_id", "slot_date", "start_time", "end_time", "status"
    }


def test_list_slots_filter_by_specialist(client, db_session):
    spec_a = _make_specialist(db_session, name="A")
    spec_b = _make_specialist(db_session, name="B")
    _make_slot(db_session, spec_a, start_time=time(9, 0), end_time=time(9, 30))
    _make_slot(db_session, spec_b, start_time=time(10, 0), end_time=time(10, 30))

    response = client.get("/slots/", params={"specialist_id": spec_a.id})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["specialist_id"] == spec_a.id


def test_list_slots_filter_by_date_and_status(client, db_session):
    spec = _make_specialist(db_session)
    _make_slot(
        db_session, spec,
        slot_date=date(2026, 1, 15),
        start_time=time(9, 0), end_time=time(9, 30),
        status="free",
    )
    _make_slot(
        db_session, spec,
        slot_date=date(2026, 1, 16),
        start_time=time(9, 0), end_time=time(9, 30),
        status="booked",
    )

    response = client.get(
        "/slots/",
        params={"slot_date": "2026-01-15", "status": "free"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "free"
    assert body["items"][0]["slot_date"] == "2026-01-15"


def test_list_slots_unauthorized(client_unauth):
    response = client_unauth.get("/slots/")
    assert response.status_code == 401


# ===========================================================================
# 5. /appointments — создание
# ===========================================================================

def test_create_appointment_success(client, db_session):
    spec = _make_specialist(db_session)
    service = _make_service(db_session, duration_minutes=30)
    slot = _make_slot(db_session, spec, start_time=time(9, 0), end_time=time(10, 0))

    response = client.post(
        "/appointments/",
        json={"slot_id": slot.id, "service_id": service.id, "client_name": "Alice"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "id", "slot_id", "service_id", "client_name", "status", "created_at"
    }
    assert body["slot_id"] == slot.id
    assert body["service_id"] == service.id
    assert body["client_name"] == "Alice"
    assert body["status"] == "active"


def test_create_appointment_missing_params_returns_422(client):
    # ни один параметр не передан — FastAPI отдаёт 422
    response = client.post("/appointments/", json={})
    assert response.status_code == 422


def test_create_appointment_unknown_slot_returns_404(client, db_session):
    service = _make_service(db_session)

    response = client.post(
        "/appointments/",
        json={"slot_id": 424242, "service_id": service.id, "client_name": "Alice"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Slot not found"


def test_create_appointment_unknown_service_returns_404(client, db_session):
    spec = _make_specialist(db_session)
    slot = _make_slot(db_session, spec)

    response = client.post(
        "/appointments/",
        json={"slot_id": slot.id, "service_id": 424242, "client_name": "Alice"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Service not found"


def test_create_appointment_booked_slot_returns_400(client, db_session):
    spec = _make_specialist(db_session)
    service = _make_service(db_session)
    slot = _make_slot(db_session, spec, status="booked")

    response = client.post(
        "/appointments/",
        json={"slot_id": slot.id, "service_id": service.id, "client_name": "Alice"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Slot is not available"


def test_create_appointment_unauthorized(client_unauth):
    response = client_unauth.post(
        "/appointments/",
        params={"slot_id": 1, "service_id": 1, "client_name": "Alice"},
    )
    assert response.status_code == 401


# ===========================================================================
# 6. /appointments — список
# ===========================================================================

def test_list_appointments_returns_paginated_payload(client, db_session):
    spec = _make_specialist(db_session)
    service = _make_service(db_session)
    slot = _make_slot(db_session, spec)
    _make_appointment(db_session, slot, service, client_name="Alice")

    response = client.get("/appointments/")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "page", "page_size", "total"}
    assert body["total"] == 1
    item = body["items"][0]
    assert set(item.keys()) == {
        "id", "slot_id", "service_id", "client_name", "status", "created_at"
    }


def test_list_appointments_filter_by_status(client, db_session):
    spec = _make_specialist(db_session)
    service = _make_service(db_session)
    slot_a = _make_slot(db_session, spec, start_time=time(9, 0), end_time=time(9, 30))
    slot_b = _make_slot(db_session, spec, start_time=time(9, 30), end_time=time(10, 0))
    _make_appointment(db_session, slot_a, service, status="active")
    _make_appointment(db_session, slot_b, service, status="cancelled")

    response = client.get("/appointments/", params={"status": "active"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "active"


def test_list_appointments_unauthorized(client_unauth):
    # ВНИМАНИЕ: этот роут сейчас без авторизации. Тест это фиксирует.
    response = client_unauth.get("/appointments/")
    assert response.status_code == 401

# ===========================================================================
# 6.5. /appointments — карточка
# ===========================================================================

def test_get_appointment_returns_card(client, db_session):
    spec = _make_specialist(db_session, name="Иванов Иван")
    service = _make_service(db_session, name="Осмотр", duration_minutes=30)
    slot = _make_slot(db_session, spec, start_time=time(9, 0), end_time=time(10, 0))
    appointment = _make_appointment(db_session, slot, service, client_name="Alice")

    response = client.get(f"/appointments/{appointment.id}")

    assert response.status_code == 200
    body = response.json()

    # верхний уровень
    assert set(body.keys()) == {
        "id", "client_name", "status", "created_at",
        "slot", "service", "specialist",
    }
    assert body["id"] == appointment.id
    assert body["client_name"] == "Alice"
    assert body["status"] == "active"

    # вложенные сущности
    assert body["slot"]["id"] == slot.id
    assert body["slot"]["status"] == "free"
    assert body["service"]["id"] == service.id
    assert body["service"]["duration_minutes"] == 30
    assert body["specialist"]["id"] == spec.id
    assert body["specialist"]["name"] == "Иванов Иван"


def test_get_appointment_unknown_returns_404(client):
    response = client.get("/appointments/424242")
    assert response.status_code == 404
    assert response.json()["detail"] == "Appointment not found"


def test_get_appointment_unauthorized(client_unauth):
    response = client_unauth.get("/appointments/1")
    assert response.status_code == 401


# ===========================================================================
# 7. /appointments — отмена
# ===========================================================================

def test_cancel_appointment_success(client, db_session):
    spec = _make_specialist(db_session)
    service = _make_service(db_session)
    slot = _make_slot(db_session, spec, status="booked")
    appointment = _make_appointment(db_session, slot, service)

    response = client.delete(f"/appointments/{appointment.id}")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"message", "appointment_id"}
    assert body["appointment_id"] == appointment.id


def test_cancel_appointment_unknown_returns_404(client):
    response = client.delete("/appointments/424242")
    assert response.status_code == 404
    assert response.json()["detail"] == "Appointment not found"


def test_cancel_appointment_twice_returns_400(client, db_session):
    spec = _make_specialist(db_session)
    service = _make_service(db_session)
    slot = _make_slot(db_session, spec)
    appointment = _make_appointment(db_session, slot, service, status="cancelled")

    response = client.delete(f"/appointments/{appointment.id}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Appointment is already cancelled"


def test_cancel_appointment_unauthorized(client_unauth):
    # ВНИМАНИЕ: этот роут сейчас без авторизации. Тест это фиксирует.
    response = client_unauth.delete("/appointments/1")
    assert response.status_code == 401


# ===========================================================================
# 8. /summary
# ===========================================================================

def test_summary_returns_expected_shape(client, db_session):
    spec = _make_specialist(db_session)
    service = _make_service(db_session)
    day = date(2026, 1, 15)

    _make_slot(db_session, spec, slot_date=day, start_time=time(9, 0), end_time=time(9, 30), status="booked")
    _make_slot(db_session, spec, slot_date=day, start_time=time(9, 30), end_time=time(10, 0), status="free")

    slot_a = db_session.query(Slot).first()
    _make_appointment(db_session, slot_a, service, status="active")

    response = client.get(
        "/summary/",
        params={"date_from": day.isoformat(), "date_to": day.isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"date_from", "date_to", "items"}
    assert len(body["items"]) == 1

    item = body["items"][0]
    assert set(item.keys()) == {
        "specialist_id", "specialist_name", "specialization",
        "total_slots", "booked_slots", "cancelled_slots", "cancellation_share",
    }


def test_summary_missing_dates_returns_422(client):
    response = client.get("/summary/")
    assert response.status_code == 422


def test_summary_unauthorized(client_unauth):
    response = client_unauth.get(
        "/summary/",
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
    )
    assert response.status_code == 401