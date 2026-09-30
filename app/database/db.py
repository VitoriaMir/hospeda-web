import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "conpec.db"
# CONPEC_DATABASE_URL permite apontar para outra base SQLite (ex.: build da demo).
DATABASE_URL = os.environ.get("CONPEC_DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def init_database():
    from app.models.models import (
        User, Employee, RoomType, Room, Guest, Stay, StayHistory, Booking, Payment,
        Expense, LaundryMachine, LaundryBooking, Maintenance,
        Cleaning, Notification, Document, AuditLog, InstitutionSettings, BackupSettings
    )
    Base.metadata.create_all(bind=engine)
    # Pequenas migrações compatíveis com bancos locais já existentes.
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
        if "permissions" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN permissions TEXT"))
        stay_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(stays)"))}
        if "has_expected_check_out" not in stay_cols:
            conn.execute(text("ALTER TABLE stays ADD COLUMN has_expected_check_out BOOLEAN NOT NULL DEFAULT 1"))
        guest_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(guests)"))}
        if "room_id" not in guest_cols:
            conn.execute(text("ALTER TABLE guests ADD COLUMN room_id INTEGER REFERENCES rooms(id)"))
        room_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(rooms)"))}
        if "daily" not in room_cols:
            conn.execute(text("ALTER TABLE rooms ADD COLUMN daily BOOLEAN NOT NULL DEFAULT 0"))
        booking_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(bookings)"))}
        if "booking_type" not in booking_cols:
            conn.execute(text("ALTER TABLE bookings ADD COLUMN booking_type TEXT NOT NULL DEFAULT 'HOSPEDAGEM'"))
        room_type_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(room_types)"))}
        if "rent_value" not in room_type_cols:
            conn.execute(text("ALTER TABLE room_types ADD COLUMN rent_value NUMERIC(12,2) NOT NULL DEFAULT 0"))
        if "daily_value" not in room_type_cols:
            conn.execute(text("ALTER TABLE room_types ADD COLUMN daily_value NUMERIC(12,2) NOT NULL DEFAULT 0"))
        employee_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(employees)"))}
        if "birth_date" not in employee_cols:
            conn.execute(text("ALTER TABLE employees ADD COLUMN birth_date DATE"))
        if "address" not in employee_cols:
            conn.execute(text("ALTER TABLE employees ADD COLUMN address VARCHAR(255)"))
        if "salary" not in employee_cols:
            conn.execute(text("ALTER TABLE employees ADD COLUMN salary NUMERIC(12,2) NOT NULL DEFAULT 0"))
