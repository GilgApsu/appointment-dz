from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from fastapi.responses import RedirectResponse

from app.routers import specialists
from app.routers import services
from app.routers import slots
from app.routers import appointments
from app.routers import summary
from app import auth

app = FastAPI(title="Appointment Service")

app.include_router(specialists.router)

app.include_router(services.router)

app.include_router(slots.router)

app.include_router(appointments.router)

app.include_router(summary.router)

app.include_router(auth.router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root():
    return RedirectResponse("/static/login.html")

@app.get("/health")
def health():
    return {
        "status": "ok"
    }