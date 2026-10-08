"""
Создание учётной записи для проверки.
Запуск: python -m app.seed_users
"""

import bcrypt
from app.auth import hash_password

from app.database import SessionLocal
from app.models import User


def ensure_user(db, username: str, password: str) -> None:
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        print(f"  пользователь '{username}' уже существует, пропускаем")
        return
    db.add(User(username=username, password_hash=hash_password(password)))
    db.commit()
    print(f"  пользователь '{username}' создан")


def main() -> None:
    db = SessionLocal()
    try:
        print("Создание учётных записей:")
        ensure_user(db, "demo", "demo")
        ensure_user(db, "tester", "tester")
    finally:
        db.close()


if __name__ == "__main__":
    main()