# Сервис записи на приём к специалисту

Хранит расписание специалистов слотами. По выбранной услуге показывает
свободные слоты подходящей длительности и бронирует один из них, не допуская
наложения на существующие записи. Отмена записи возвращает слот в свободные.
Сводка показывает загрузку специалистов за период и долю отменённых записей.
Учебный сервис курсовой работы по дисциплине «Оптимизация клиент-серверных
приложений».

## Требования

- Python 3.14;
- PostgreSQL 18;

## Установка и запуск

    git clone https://github.com/GilgApsu/appointment-dz.git
    cd appointment-dz
    cp .env.example .env              # заполнить переменные
    
    python -m venv .venv
    #Windows
    .venv\Scripts\activate
    #Linux/macOS
    source .venv/bin/activate

    pip install -r requirements.txt
    psql -U postgres -c "CREATE DATABASE fedor_sokolov;"
    python -m app.create_schema
    python -m app.seed_users

    # малое наполнение (для ручной проверки)
    python -m app.seed_small

    # рабочее наполнение (для замеров; перезаписывает таблицы)
    python -m app.seed_large

    uvicorn app.main:app

## Переменные окружения

| Переменная     | Назначение                | Пример                      |
|----------------|---------------------------|-----------------------------|
| DATABASE_URL   | подключение к базе данных | postgresql+psycopg2://postgres:123@localhost:changeme/fedor_sokolov |


## Проверка работоспособности

Интерфейс открывается по адресу http://localhost:8000/, учётная запись для
проверки — demo / demo. На главной странице виден список записей.

## Тесты

    pytest -v

## Программный интерфейс

Все операции, кроме `/auth/login` и `/health`, требуют авторизации.
Токен передаётся в заголовке `Authorization: Bearer <token>`.
Ответы — JSON. Даты — `YYYY-MM-DD`, время — `HH:MM:SS`.

### Служебные

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| `GET /health` | — | `{"status": "ok"}` | — |

### Аутентификация

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| `POST /auth/login` | form: `username`, `password` | {"access_token": "...", "token_type": "bearer"} | 401, 422 |

### Специалисты

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| `GET /specialists/` | `page`, `page_size`, `search` | `{"items": [{"id", "name", "specialization"}], "page", "page_size", "total"}` | 401, 422 |

### Услуги

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| `GET /services/` | `page`, `page_size`, `search` | `{"items": [{"id", "name", "duration_minutes"}], "page", "page_size", "total"}` | 401, 422 |

### Слоты

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| `GET /slots/` | `page`, `page_size`, `specialist_id`, `slot_date`, `status` | `{"items": [{"id", "specialist_id", "slot_date", "start_time", "end_time", "status"}], "page", "page_size", "total"}` | 401, 422 |

### Записи

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| `POST /appointments/` | body: `slot_id`, `service_id`, `client_name` | `{"id", "slot_id", "service_id", "client_name", "status", "created_at"}` | 400, 401, 404, 422 |
| `GET /appointments/` | `page`, `page_size`, `status` | `{"items": [...], "page", "page_size", "total"}` | 401, 422 |
| `GET /appointments/{id}` | — (id в пути) | `{"id", "client_name", "status", "created_at", "slot": {...}, "service": {...}, "specialist": {...}}` | 401, 404 |
| `DELETE /appointments/{id}` | — (id в пути) | `{"message": "...", "appointment_id": N}` | 400, 401, 404 |

### Сводка

| Метод и путь | Параметры | Ответ | Ошибки |
|---|---|---|---|
| `GET /summary/` | `date_from`, `date_to` (`YYYY-MM-DD`) | `{"date_from", "date_to", "items": [{"specialist_id", "specialist_name", "specialization", "total_slots", "booked_slots", "cancelled_slots", "cancellation_share"}]}` | 401, 422 |

### Коды ошибок

| Код | Когда возвращается |
|---|---|
| 400 | бизнес-правило нарушено: слот занят, слот короче услуги, запись уже отменена |
| 401 | отсутствует или недействителен токен доступа |
| 404 | сущность не найдена по id |
| 422 | параметр отсутствует или имеет неверный формат |