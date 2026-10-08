"""
Замеры времени ответа операций API (замена scripts/measure.py).

Запуск (перед КАЖДОЙ серией заново наполняйте базу: seed_small или seed_large):
    python -m scripts.measure --label small --output measure_small.csv
    python -m scripts.measure --label large --output measure_large.csv
"""

import argparse
import csv
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class Operation:
    name: str
    method: str
    # path/params/json могут зависеть от номера вызова (create/cancel)
    build: callable = field(repr=False)


def minutes(t: str) -> int:
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


def die(msg: str):
    print(msg, file=sys.stderr)
    sys.exit(1)


def login(client, username, password) -> str:
    r = client.post("/auth/login", data={"username": username, "password": password})
    if r.status_code != 200:
        die(f"Логин не удался: {r.status_code} {r.text}")
    return r.json()["access_token"]


def get_json(client, path, **params):
    r = client.get(path, params=params)
    if r.status_code != 200:
        die(f"GET {path} {params}: код {r.status_code}: {r.text[:200]}")
    return r.json()


def prepare(client, need: int) -> dict:
    """Опорные данные: по одному id для чтения и пулы для create/cancel (по `need` штук)."""
    if need > 100:
        die("warmup + repeats не должно превышать 100 (ограничение page_size)")

    spec = get_json(client, "/specialists/", page=1, page_size=1)["items"]
    first_slot = get_json(client, "/slots/", page=1, page_size=1)["items"]
    first_appt = get_json(client, "/appointments/", page=1, page_size=1)["items"]
    if not (spec and first_slot and first_appt):
        die("В базе нет специалистов, слотов или записей — наполните базу.")

    # услуга с минимальной длительностью: она точно помещается в слот
    services = get_json(client, "/services/", page=1, page_size=100)["items"]
    service = min(services, key=lambda s: s["duration_minutes"])

    free = get_json(client, "/slots/", page=1, page_size=100, status="free")["items"]
    free = [s for s in free
            if minutes(s["end_time"]) - minutes(s["start_time"]) >= service["duration_minutes"]]
    if len(free) < need:
        die(f"Свободных подходящих слотов {len(free)}, нужно {need}.")

    active = get_json(client, "/appointments/", page=1, page_size=100, status="active")["items"]
    if len(active) < need:
        die(f"Активных записей {len(active)}, нужно {need}.")

    return {
        "specialist_id": spec[0]["id"],
        "slot_date": first_slot[0]["slot_date"],
        "appointment_id": first_appt[0]["id"],
        "service_id": service["id"],
        "free_slot_ids": [s["id"] for s in free[:need]],
        "active_ids": [a["id"] for a in active[:need]],
    }


def build_operations(ids: dict, date_from: str, date_to: str) -> list[Operation]:
    def fixed(method, path, params=None):
        return lambda i: (method, path, params, None)

    free_iter = ids["free_slot_ids"]
    active_iter = ids["active_ids"]

    return [
        Operation("list_specialists", "GET", fixed("GET", "/specialists/", {"page": 1, "page_size": 20})),
        Operation("list_services", "GET", fixed("GET", "/services/", {"page": 1, "page_size": 20})),
        Operation("list_slots", "GET", fixed("GET", "/slots/", {"page": 1, "page_size": 20})),
        Operation("list_slots_filtered", "GET", fixed("GET", "/slots/", {
            "page": 1, "page_size": 20, "specialist_id": ids["specialist_id"],
            "slot_date": ids["slot_date"], "status": "free"})),
        Operation("list_appointments", "GET", fixed("GET", "/appointments/", {"page": 1, "page_size": 20})),
        Operation("list_appointments_active", "GET", fixed("GET", "/appointments/",
                                                           {"page": 1, "page_size": 20, "status": "active"})),
        Operation("get_appointment", "GET", fixed("GET", f"/appointments/{ids['appointment_id']}")),
        Operation("summary", "GET", fixed("GET", "/summary/", {"date_from": date_from, "date_to": date_to})),
        # операции записи — в конце, чтобы не менять данные для чтения
        Operation("create_appointment", "POST", lambda i: (
            "POST", "/appointments/", None,
            {"slot_id": free_iter[i], "service_id": ids["service_id"], "client_name": "measure-probe"})),
        Operation("cancel_appointment", "DELETE", lambda i: (
            "DELETE", f"/appointments/{active_iter[i]}", None, None)),
    ]


def call(client, op: Operation, i: int) -> float:
    method, path, params, body = op.build(i)
    start = time.perf_counter()
    r = client.request(method, path, params=params, json=body)
    ms = (time.perf_counter() - start) * 1000.0
    if r.status_code != 200:
        raise RuntimeError(f"{op.name}: код {r.status_code} вместо 200: {r.text[:200]}")
    return ms


def measure_series(client, op: Operation, repeats: int, warmup: int) -> dict:
    n = 0
    for _ in range(warmup):          # прогрев; для create/cancel тоже расходует свой слот/запись
        call(client, op, n)
        n += 1
    samples = []
    for _ in range(repeats):
        samples.append(call(client, op, n))
        n += 1
    s = sorted(samples)
    idx = max(0, min(len(s) - 1, int(round(0.95 * (len(s) - 1)))))
    return {
        "name": op.name,
        "median_ms": round(statistics.median(s), 2),
        "p95_ms": round(s[idx], 2),
        "max_ms": round(s[-1], 2),
        "samples": len(s),
    }


def main():
    ap = argparse.ArgumentParser(description="Замеры времени ответа API")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--username", default="demo")
    ap.add_argument("--password", default="demo")
    ap.add_argument("--repeats", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--date-from", default="2026-01-01")
    ap.add_argument("--date-to", default="2026-02-28")
    ap.add_argument("--output", default="measurements.csv")
    ap.add_argument("--label", default="", help="метка серии: small или large")
    args = ap.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        client.headers["Authorization"] = "Bearer " + login(client, args.username, args.password)
        total = get_json(client, "/appointments/", page=1, page_size=1)["total"]
        ids = prepare(client, args.warmup + args.repeats)
        print(f"Записей в базе: {total}. Опорные данные: "
              f"specialist={ids['specialist_id']}, service={ids['service_id']}, "
              f"slot_date={ids['slot_date']}, appointment={ids['appointment_id']}")
        print(f"Серия: {args.label or '-'} | повторов {args.repeats} | прогрев {args.warmup} | "
              f"период сводки {args.date_from}..{args.date_to}\n")
        print(f"{'операция':<26} {'медиана, мс':>12} {'p95, мс':>10} {'max, мс':>10}")
        print("-" * 62)

        rows = []
        for op in build_operations(ids, args.date_from, args.date_to):
            try:
                st = measure_series(client, op, args.repeats, args.warmup)
            except Exception as exc:
                die(f"{op.name:<26} ПАДЕНИЕ: {exc}")
            print(f"{st['name']:<26} {st['median_ms']:>12} {st['p95_ms']:>10} {st['max_ms']:>10}")
            st["label"] = args.label
            rows.append(st)

        after = get_json(client, "/appointments/", page=1, page_size=1)["total"]
        print(f"\nЗаписей в базе после замеров: {after} (добавлено {after - total})")

        with open(args.output, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["label", "name", "median_ms", "p95_ms", "max_ms", "samples"])
            w.writeheader()
            w.writerows(rows)
        print(f"Результаты сохранены в {args.output}")


if __name__ == "__main__":
    main()