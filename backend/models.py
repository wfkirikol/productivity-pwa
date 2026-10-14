from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, Date, DateTime, Enum as SqlEnum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [value.value for value in enum_type]


class ActivityStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class Recurrence(str, Enum):
    ONCE = "ONCE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class ActivityPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class EnergyLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TransactionKind(str, Enum):
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"


class ReflectionSection(str, Enum):
    CONFLICT = "CONFLICT"
    PSYCHOLOGY = "PSYCHOLOGY"
    THOUGHT = "THOUGHT"


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (CheckConstraint("progress >= 0 AND progress <= 100", name="ck_activity_progress"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ActivityStatus] = mapped_column(
        SqlEnum(ActivityStatus, values_callable=_enum_values, native_enum=False),
        default=ActivityStatus.PENDING,
        nullable=False,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recurrence: Mapped[Recurrence] = mapped_column(
        SqlEnum(Recurrence, values_callable=_enum_values, native_enum=False),
        default=Recurrence.ONCE,
        nullable=False,
    )
    priority: Mapped[ActivityPriority] = mapped_column(
        SqlEnum(ActivityPriority, values_callable=_enum_values, native_enum=False),
        default=ActivityPriority.NORMAL,
        nullable=False,
    )
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    energy_level: Mapped[EnergyLevel] = mapped_column(
        SqlEnum(EnergyLevel, values_callable=_enum_values, native_enum=False),
        default=EnergyLevel.MEDIUM,
        nullable=False,
    )
    focus_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent_activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
    next_occurrence_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="activity", passive_deletes=True
    )
    checklist_items: Mapped[list["ActivityChecklistItem"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ActivityChecklistItem.position",
    )
    focus_sessions: Mapped[list["FocusSession"]] = relationship(
        back_populates="activity", passive_deletes=True
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    kind: Mapped[TransactionKind] = mapped_column(
        SqlEnum(TransactionKind, values_callable=_enum_values, native_enum=False),
        default=TransactionKind.EXPENSE,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    linked_activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    activity: Mapped[Activity | None] = relationship(back_populates="transactions")


class Reflection(Base):
    __tablename__ = "reflections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    section: Mapped[ReflectionSection] = mapped_column(
        SqlEnum(ReflectionSection, values_callable=_enum_values, native_enum=False),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class ActivityChecklistItem(Base):
    __tablename__ = "activity_checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    completed: Mapped[bool] = mapped_column(default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activity: Mapped[Activity] = relationship(back_populates="checklist_items")


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), index=True, nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activity: Mapped[Activity | None] = relationship(back_populates="focus_sessions")


class DailyPlan(Base):
    __tablename__ = "daily_plans"
    __table_args__ = (UniqueConstraint("user_id", "plan_date", name="uq_daily_plan_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    plan_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    available_minutes: Mapped[int] = mapped_column(Integer, default=360, nullable=False)
