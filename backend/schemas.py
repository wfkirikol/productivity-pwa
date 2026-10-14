from datetime import date, datetime, timezone
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models import (
    ActivityPriority,
    ActivityStatus,
    EnergyLevel,
    Recurrence,
    ReflectionSection,
    TransactionKind,
)


class ActivityFields(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    due_date: datetime


class ActivityCreate(ActivityFields):
    status: ActivityStatus = ActivityStatus.PENDING
    progress: int = Field(default=0, ge=0, le=100)
    recurrence: Recurrence = Recurrence.ONCE
    priority: ActivityPriority = ActivityPriority.NORMAL
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    energy_level: EnergyLevel = EnergyLevel.MEDIUM


class ActivityPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    due_date: datetime | None = None
    status: ActivityStatus | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    recurrence: Recurrence | None = None
    priority: ActivityPriority | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    energy_level: EnergyLevel | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class ActivityRead(ActivityCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    focus_seconds: int
    parent_activity_id: int | None
    next_occurrence_id: int | None
    checklist_items: list["ActivityChecklistItemRead"] = []


class ActivityChecklistItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ActivityChecklistItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    completed: bool | None = None


class ActivityChecklistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    completed: bool
    position: int


class FocusSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_id: int | None
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int


class DailyPlanUpdate(BaseModel):
    available_minutes: int = Field(ge=30, le=1440)


class DailyPlanRead(BaseModel):
    plan_date: date
    available_minutes: int
    planned_minutes: int
    selected: list[ActivityRead]
    deferred: list[ActivityRead]


class MotivationRequest(BaseModel):
    current_goal: str = Field(default="", max_length=300)
    available_minutes: int = Field(default=15, ge=1, le=240)


class TimeManagementRequest(BaseModel):
    available_minutes: int = Field(ge=1, le=1440)


class DecompositionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=3000)


class AIResponseRead(BaseModel):
    text: str
    fallback: bool
    scenario: Literal["motivation", "time_management", "decomposition"]


class TransactionCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    kind: TransactionKind = TransactionKind.EXPENSE
    category: str = Field(min_length=1, max_length=100)
    linked_activity_id: int | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str | None = Field(default=None, max_length=2000)


class TransactionRead(TransactionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int


class ReflectionCreate(BaseModel):
    section: ReflectionSection
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)


class ReflectionRead(ReflectionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
