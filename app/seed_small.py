"""
Малое наполнение БД.
Пропорции:
  специалисты — 10
  услуги      — 10
  слоты       — 500
  записи      — 300

Наполнение воспроизводимое: seed фиксирован.
Запуск: python -m app.seed_small
"""

import random
from datetime import date, datetime, time, timedelta, timezone

from app.database import SessionLocal
from app.models import Appointment, Service, Slot, Specialist

SEED = 42

SPECIALISTS = [
    ("Иванов Иван", "Терапевт"),
    ("Петров Пётр", "Хирург"),
    ("Сидорова Анна", "Кардиолог"),
    ("Кузнецов Олег", "Невролог"),
    ("Смирнова Ольга", "Окулист"),
    ("Попов Дмитрий", "Стоматолог"),
    ("Волкова Мария", "Дерматолог"),
    ("Соколов Артём", "ЛОР"),
    ("Морозова Елена", "Эндокринолог"),
    ("Лебедев Сергей", "Психотерапевт"),
]

SERVICES = [
    ("Первичная консультация", 30),
    ("Повторная консультация", 30),
    ("Осмотр", 15),
    ("Расширенный приём", 60),
    ("Процедура", 45),
    ("Диагностика", 60),
    ("Профилактический осмотр", 30),
    ("Экспресс-приём", 15),
    ("Комплексный приём", 90),
    ("Онлайн-консультация", 30),
]

WORK_START = time(9, 0)
WORK_END = time(18, 0)
SLOT_LENGTH_MIN = 30  # длительность слота в минутах
DAYS_AHEAD = 5        # расписание на 5 дней вперёд


def make_slots_for_specialist(specialist: Specialist, base_day: date):
    """Возвращает список слотов одного специалиста на DAYS_AHEAD дней."""
    slots = []
    for day_offset in range(DAYS_AHEAD):
        slot_date = base_day + timedelta(days=day_offset)
        current = datetime.combine(slot_date, WORK_START)
        end_of_day = datetime.combine(slot_date, WORK_END)
        while current + timedelta(minutes=SLOT_LENGTH_MIN) <= end_of_day:
            slots.append(
                Slot(
                    specialist_id=specialist.id,
                    slot_date=slot_date,
                    start_time=current.time(),
                    end_time=(current + timedelta(minutes=SLOT_LENGTH_MIN)).time(),
                    status="free",
                )
            )
            current += timedelta(minutes=SLOT_LENGTH_MIN)
    return slots


def main() -> None:
    random.seed(SEED)
    db = SessionLocal()
    try:
        # очистка в правильном порядке
        db.query(Appointment).delete()
        db.query(Slot).delete()
        db.query(Service).delete()
        db.query(Specialist).delete()
        db.commit()

        # специалисты
        specialists = []
        for name, spec in SPECIALISTS:
            s = Specialist(name=name, specialization=spec)
            db.add(s)
            specialists.append(s)
        db.commit()
        for s in specialists:
            db.refresh(s)

        # услуги
        services = []
        for name, duration in SERVICES:
            srv = Service(name=name, duration_minutes=duration)
            db.add(srv)
            services.append(srv)
        db.commit()
        for s in services:
            db.refresh(s)

        # слоты: на каждого специалиста — 5 дней × 18 слотов = 90 слотов
        # на 10 специалистов — 900. Методичка просит 500,
        # поэтому обрежем до 500 равномерно.
        base_day = date(2026, 1, 15)
        all_slots: list[Slot] = []
        for sp in specialists:
            all_slots.extend(make_slots_for_specialist(sp, base_day))

        random.shuffle(all_slots)
        all_slots = all_slots[:500]

        # сортируем обратно по (специалист, дата, время), чтобы было удобно
        all_slots.sort(key=lambda s: (s.specialist_id, s.slot_date, s.start_time))
        db.add_all(all_slots)
        db.commit()
        for s in all_slots:
            db.refresh(s)

        # записи: 300 на случайные слоты
        # ~80% активные, ~20% отменённые
        chosen_slots = random.sample(all_slots, 300)
        appointments = []
        for i, slot in enumerate(chosen_slots):
            is_cancelled = i % 5 == 0  # каждая пятая — отменённая
            slot.status = "free" if is_cancelled else "booked"
            appointments.append(
                Appointment(
                    slot_id=slot.id,
                    service_id=random.choice(services).id,
                    client_name=f"Клиент {i + 1:04d}",
                    status="cancelled" if is_cancelled else "active",
                )
            )
        db.add_all(appointments)
        db.commit()

        # итоговые счётчики
        print("Малое наполнение завершено.")
        print(f"  специалисты: {db.query(Specialist).count()}")
        print(f"  услуги:      {db.query(Service).count()}")
        print(f"  слоты:       {db.query(Slot).count()}")
        print(f"  записи:      {db.query(Appointment).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()