#Запуск: python -m app.create_schema

from sqlalchemy import text

from app.database import engine
from app.models import Base


def main() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    Base.metadata.create_all(bind=engine)

    print("Схема создана.")
    print("Таблицы:")
    for table in Base.metadata.sorted_tables:
        print(f"  - {table.name}")


if __name__ == "__main__":
    main()