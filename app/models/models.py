from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.db import Base

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="FUNCIONARIO", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    permissions: Mapped[str | None] = mapped_column(Text, nullable=True)

class Employee(TimestampMixin, Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    function: Mapped[str] = mapped_column(String(80), nullable=False)
    birth_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(30), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True, nullable=True)

class RoomType(TimestampMixin, Base):
    __tablename__ = "room_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    bathroom: Mapped[str] = mapped_column(String(40), nullable=False)
    kitchen: Mapped[str] = mapped_column(String(40), nullable=False)
    rent_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    daily_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    rooms = relationship("Room", back_populates="room_type")

class Room(TimestampMixin, Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="DISPONÍVEL", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    daily: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    room_type = relationship("RoomType", back_populates="rooms")

class Guest(TimestampMixin, Base):
    __tablename__ = "guests"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    cpf: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    rg: Mapped[str | None] = mapped_column(String(30), nullable=True)
    birth_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)

class Stay(TimestampMixin, Base):
    __tablename__ = "stays"
    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    check_in: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expected_check_out: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    has_expected_check_out: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    actual_check_out: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    deposit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ATIVA", nullable=False)

class StayHistory(TimestampMixin, Base):
    __tablename__ = "stay_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    stay_id: Mapped[int] = mapped_column(ForeignKey("stays.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    old_room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"))
    new_room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"))
    old_checkout: Mapped[datetime | None] = mapped_column(DateTime)
    new_checkout: Mapped[datetime | None] = mapped_column(DateTime)
    old_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    new_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    reason: Mapped[str | None] = mapped_column(Text)

class Booking(TimestampMixin, Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    check_in: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    check_out: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    booking_type: Mapped[str] = mapped_column(String(20), default="HOSPEDAGEM", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PRÉ-RESERVA", nullable=False)

class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int | None] = mapped_column(ForeignKey("guests.id"))
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"))
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    method: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="PENDENTE", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

class Expense(TimestampMixin, Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30), default="PENDENTE", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    receipt_path: Mapped[str | None] = mapped_column(String(500))

class LaundryMachine(TimestampMixin, Base):
    __tablename__ = "laundry_machines"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    type: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="DISPONÍVEL", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

class LaundryBooking(TimestampMixin, Base):
    __tablename__ = "laundry_bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), nullable=False)
    machine_id: Mapped[int] = mapped_column(ForeignKey("laundry_machines.id"), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

class Maintenance(TimestampMixin, Base):
    __tablename__ = "maintenance"
    id: Mapped[int] = mapped_column(primary_key=True)
    location: Mapped[str] = mapped_column(String(100), nullable=False)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="MÉDIA", nullable=False)
    responsible: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), default="ABERTO", nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    photos: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

class Cleaning(TimestampMixin, Base):
    __tablename__ = "cleaning"
    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    responsible: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), default="PENDENTE", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_for_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int | None] = mapped_column(ForeignKey("guests.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class InstitutionSettings(TimestampMixin, Base):
    __tablename__ = "institution_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="Hospeda")
    subtitle: Mapped[str] = mapped_column(String(255), default="Gestão de hospedagem")
    city_state: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    whatsapp: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(160))
    logo_path: Mapped[str | None] = mapped_column(String(500))


class BackupSettings(TimestampMixin, Base):
    __tablename__ = "backup_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    automatic_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    directory: Mapped[str | None] = mapped_column(String(500))
    last_backup: Mapped[datetime | None] = mapped_column(DateTime)
