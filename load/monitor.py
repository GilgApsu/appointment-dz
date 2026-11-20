import argparse, csv, os, time
import psutil, psycopg2
from dotenv import load_dotenv

load_dotenv()
ap = argparse.ArgumentParser()
ap.add_argument("--app-pid", type=int, required=True)
ap.add_argument("--out", default="load/results/resources.csv")
a = ap.parse_args()

app = psutil.Process(a.app_pid)
pg = [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower().startswith("postgres")]
dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
conn = psycopg2.connect(dsn); conn.autocommit = True
cur = conn.cursor()

def tree(p): 
    return [p] + p.children(recursive=True)

procs_app = tree(app)
for p in procs_app + pg: p.cpu_percent(None)
os.makedirs(os.path.dirname(a.out), exist_ok=True)
with open(a.out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t", "app_cpu_pct", "db_cpu_pct", "app_mem_mb", "db_mem_mb", "db_conn_all", "db_conn_active"])
    t0 = time.time()
    while True:
        time.sleep(1)
        try:
            procs_app = tree(app)
            ac = sum(p.cpu_percent(None) for p in procs_app)
            dc = sum(p.cpu_percent(None) for p in pg)
            am = sum(p.memory_info().rss for p in procs_app) / 2**20
            dm = sum(p.memory_info().rss for p in pg) / 2**20
            cur.execute("select count(*), count(*) filter (where state='active') "
                        "from pg_stat_activity where datname=current_database() and pid<>pg_backend_pid()")
            ca, cact = cur.fetchone()
            w.writerow([round(time.time() - t0), round(ac, 1), round(dc, 1), round(am), round(dm), ca, cact])
            f.flush()
        except psutil.NoSuchProcess:
            break
