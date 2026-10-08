"""
Рабочее наполнение БД для варианта 3.
Пропорции (см. таблицу 3 методички):
  специалисты — 200
  услуги      — 30
  слоты       — 200 000
  записи      — 50 000..100 000

Внутри стоит 75 000 записей — середина диапазона.
Используется bulk_insert_mappings: 200 000 ORM-объектов построчно
будут вставляться десятки минут.

Запуск: python -m app.seed_large
"""

import random
from datetime import date, datetime, time, timedelta

from app.database import SessionLocal
from app.models import Appointment, Service, Slot, Specialist

SEED = 7

N_SPECIALISTS = 200
N_SERVICES = 30
N_SLOTS = 200_000
N_APPOINTMENTS = 75_000

SLOT_LENGTH_MIN = 30
WORK_START = time(9, 0)
WORK_END = time(18, 0)
# слотов в день на специалиста: (18-9)*60/30 = 18
SLOTS_PER_SPECIALIST_PER_DAY = 18
# 200 000 / 200 специалистов / 18 слотов в день ≈ 56 дней расписания
DAYS_AHEAD = (N_SLOTS // N_SPECIALISTS) // SLOTS_PER_SPECIALIST_PER_DAY + 1
BASE_DAY = date(2026, 1, 1)

SPEC_NAMES = [
    "Терапевт", "Хирург", "Кардиолог", "Невролог", "Окулист",
    "Стоматолог", "Дерматолог", "ЛОР", "Эндокринолог", "Психотерапевт",
    "Гинеколог", "Уролог", "Ортопед", "Пульмонолог", "Гастроэнтеролог",
]

SERVICE_NAMES = [
    "Первичная консультация", "Повторная консультация", "Осмотр",
    "Расширенный приём", "Процедура", "Диагностика",
    "Профилактический осмотр", "Экспресс-приём", "Комплексный приём",
    "Онлайн-консультация", "УЗИ", "Рентген", "МРТ", "КТ",
    "Анализ крови", "Анализ мочи", "ЭКГ", "ЭЭГ", "Биопсия",
    "Физиотерапия", "Массаж", "Иглоукалывание", "Вакцинация",
    "Перевязка", "Снятие швов", "Консультация по питанию",
    "Психологическая консультация", "Стоматологическая чистка",
    "Пломбирование", "Удаление зуба",
]
assert len(SERVICE_NAMES) == N_SERVICES


def main() -> None:
    random.seed(SEED)
    db = SessionLocal()
    try:
        # ---- очистка ----
        print("Очистка таблиц...")
        db.query(Appointment).delete()
        db.query(Slot).delete()
        db.query(Service).delete()
        db.query(Specialist).delete()
        db.commit()

        # ---- специалисты ----
        print(f"Вставка специалистов: {N_SPECIALISTS}")
        specialists_payload = [
            {
                "name": f"Специалист {i + 1:04d}",
                "specialization": random.choice(SPEC_NAMES),
            }
            for i in range(N_SPECIALISTS)
        ]
        db.bulk_insert_mappings(Specialist, specialists_payload)
        db.commit()
        specialist_ids = [row[0] for row in db.query(Specialist.id).all()]
        print(f"  готово: {len(specialist_ids)}")

        # ---- услуги ----
        print(f"Вставка услуг: {N_SERVICES}")
        services_payload = [
            {
                "name": SERVICE_NAMES[i],
                "duration_minutes": random.choice([15, 30, 45, 60, 90]),
            }
            for i in range(N_SERVICES)
        ]
        db.bulk_insert_mappings(Service, services_payload)
        db.commit()
        service_ids = [row[0] for row in db.query(Service.id).all()]
        print(f"  готово: {len(service_ids)}")

        # ---- слоты ----
        # генерируем ровно N_SLOTS штук, распределяя по специалистам
        # в порядке round-robin по дням
        print(f"Вставка слотов: {N_SLOTS}")
        slots_payload = []
        per_spec = N_SLOTS // N_SPECIALISTS
        for sp_idx, spec_id in enumerate(specialist_ids):
            remaining = per_spec
            day_offset = 0
            while remaining > 0:
                slot_date = BASE_DAY + timedelta(days=day_offset)
                current = datetime.combine(slot_date, WORK_START)
                end_of_day = datetime.combine(slot_date, WORK_END)
                while (
                    current + timedelta(minutes=SLOT_LENGTH_MIN) <= end_of_day
                    and remaining > 0
                ):
                    slots_payload.append(
                        {
                            "specialist_id": spec_id,
                            "slot_date": slot_date,
                            "start_time": current.time(),
                            "end_time": (
                                current + timedelta(minutes=SLOT_LENGTH_MIN)
                            ).time(),
                            "status": "free",
                        }
                    )
                    current += timedelta(minutes=SLOT_LENGTH_MIN)
                    remaining -= 1
                day_offset += 1

        # bulk_insert_mappings на 200k строк — комфортно,
        # но лучше разбить на пачки, чтобы не держать всё в памяти
        BATCH = 10_000
        for i in range(0, len(slots_payload), BATCH):
            db.bulk_insert_mappings(Slot, slots_payload[i : i + BATCH])
            db.commit()
            print(f"  вставлено слотов: {min(i + BATCH, len(slots_payload))}")

        # ---- записи ----
        print(f"Вставка записей: {N_APPOINTMENTS}")
        # берём случайные id слотов
        slot_ids = [row[0] for row in db.query(Slot.id).all()]
        chosen = random.sample(slot_ids, N_APPOINTMENTS)

        appointments_payload = []
        booked_slot_ids = []
        for i, slot_id in enumerate(chosen):
            cancelled = (i % 5 == 0)
            appointments_payload.append(
                {
                    "slot_id": slot_id,
                    "service_id": random.choice(service_ids),
                    "client_name": f"Клиент {i + 1:06d}",
                    "status": "cancelled" if cancelled else "active",
                }
            )
            if not cancelled:
                booked_slot_ids.append(slot_id)

        for i in range(0, len(appointments_payload), BATCH):
            db.bulk_insert_mappings(
                Appointment, appointments_payload[i : i + BATCH]
            )
            db.commit()
            print(
                f"  вставлено записей: "
                f"{min(i + BATCH, len(appointments_payload))}"
            )

        # обновляем статус занятых слотов одним UPDATE
        print("Обновление статусов слотов...")
        CHUNK = 5_000
        for i in range(0, len(booked_slot_ids), CHUNK):
            db.query(Slot).filter(
                Slot.id.in_(booked_slot_ids[i : i + CHUNK])
            ).update({"status": "booked"}, synchronize_session=False)
            db.commit()
        print("  готово")

        # ---- итог ----
        print("Рабочее наполнение завершено.")
        print(f"  специалисты: {db.query(Specialist).count()}")
        print(f"  услуги:      {db.query(Service).count()}")
        print(f"  слоты:       {db.query(Slot).count()}")
        print(f"  записи:      {db.query(Appointment).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()