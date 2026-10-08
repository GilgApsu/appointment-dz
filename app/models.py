from sqlalchemy import Column, Integer, String, Date, Time, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone 
from pydantic import BaseModel, Field

Base = declarative_base()



class AppointmentCreate(BaseModel):
    slot_id: int = Field(..., gt=0)
    service_id: int = Field(..., gt=0)
    client_name: str = Field(..., min_length=1, max_length=150)

class Specialist(Base):
    __tablename__ = "specialist"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    specialization = Column(String(100), nullable=False)

class Service(Base):
    __tablename__ = "service"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    duration_minutes = Column(Integer, nullable=False)

class Slot(Base):
    __tablename__ = "slot"

    id = Column(Integer, primary_key=True)
    specialist_id = Column(
        Integer,
        ForeignKey("specialist.id"),
        nullable=False
    )
    slot_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(String(20), nullable=False, default="free")

class Appointment(Base):
    __tablename__ = "appointment"

    id = Column(Integer, primary_key=True)
    slot_id = Column(
        Integer,
        ForeignKey("slot.id"),
        nullable=False
    )
    service_id = Column(
        Integer,
        ForeignKey("service.id"),
        nullable=False
    )
    client_name = Column(String(150), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)