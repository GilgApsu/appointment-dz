"""
Разложение времени операций между приложением и базой данных (раздел 2.6 ДЗ1).

Как работает: приложение запускается внутри этого процесса (FastAPI TestClient), к движку SQLAlchemy
подключены события before_cursor_execute / after_cursor_execute. За один вызов операции считаются
  * время операции целиком (перед/после client.request),
  * суммарное время выполнения SQL-запросов («в базе»),
  * число SQL-запросов (включая запрос пользователя при проверке токена).
«В коде» = время операции − время в базе. Работает с базой из .env — той же, что у сервиса;
запускать при НАПОЛНЕННОЙ рабочей базе, сервер uvicorn для этого не нужен.

Запуск (положить в scripts/, из корня проекта):
    python -m scripts.profile_db --username demo --password demo --repeats 20 --output profile_large.csv
"""

import argparse
import csv
import statistics
import sys
import time

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import engine
from app.main import app

from scripts.measure import build_operations, get_json, login, prepare  # те же операции, что и в замерах

COUNTER = {"n": 0, "t": 0.0}


@event.listens_for(engine, "before_cursor_execute")
def _before(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("_q_start", []).append(time.perf_counter())


@event.listens_for(engine, "after_cursor_execute")
def _after(conn, cursor, statement, parameters, context, executemany):
    COUNTER["t"] += time.perf_counter() - conn.info["_q_start"].pop()
    COUNTER["n"] += 1


def one_call(client, op, i):
    method, path, params, body = op.build(i)
    COUNTER["n"], COUNTER["t"] = 0, 0.0
    start = time.perf_counter()
    r = client.request(method, path, params=params, json=body)
    total = (time.perf_counter() - start) * 1000.0
    if r.status_code != 200:
        sys.exit(f"{op.name}: код {r.status_code} вместо 200: {r.text[:200]}")
    return total, COUNTER["t"] * 1000.0, COUNTER["n"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default="demo")
    ap.add_argument("--password", default="demo")
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--date-from", default="2026-01-01")
    ap.add_argument("--date-to", default="2026-02-28")
    ap.add_argument("--output", default="profile.csv")
    args = ap.parse_args()

    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + login(client, args.username, args.password)
        ids = prepare(client, args.warmup + args.repeats)
        ops = build_operations(ids, args.date_from, args.date_to)

        print(f"{'операция':<26} {'всего, мс':>10} {'в базе, мс':>11} {'в коде, мс':>11} {'запросов':>9} {'доля БД':>8}")
        print("-" * 80)
        rows = []
        for op in ops:
            k = 0
            for _ in range(args.warmup):
                one_call(client, op, k); k += 1
            res = []
            for _ in range(args.repeats):
                res.append(one_call(client, op, k)); k += 1
            total = statistics.median(r[0] for r in res)
            db = statistics.median(r[1] for r in res)
            nq = int(statistics.median(r[2] for r in res))
            code = total - db
            share = 100 * db / total if total else 0
            print(f"{op.name:<26} {total:>10.2f} {db:>11.2f} {code:>11.2f} {nq:>9} {share:>7.0f}%")
            rows.append({"name": op.name, "total_ms": round(total, 2), "db_ms": round(db, 2),
                         "code_ms": round(code, 2), "queries": nq, "db_share_pct": round(share)})

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nСохранено в {args.output}")


if __name__ == "__main__":
    main()
