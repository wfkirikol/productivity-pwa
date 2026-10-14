from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import calendar
from typing import Annotated

from adapters.openrouter import OpenRouterAdapter
from adapters.prompts import (
    build_decomposition_prompt,
    build_motivation_prompt,
    build_time_management_prompt,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db, initialize_database
from backend.models import (
    Activity,
    ActivityChecklistItem,
    ActivityStatus,
    DailyPlan,
    FocusSession,
    Recurrence,
    Reflection,
    Transaction,
)
from backend.schemas import (
    AIResponseRead,
    ActivityCreate,
    ActivityPatch,
    ActivityRead,
    ActivityChecklistItemCreate,
    ActivityChecklistItemPatch,
    ActivityChecklistItemRead,
    DailyPlanRead,
    DailyPlanUpdate,
    DecompositionRequest,
    FocusSessionRead,
    MotivationRequest,
    ReflectionCreate,
    ReflectionRead,
    TransactionCreate,
    TransactionRead,
    TimeManagementRequest,
)
from core.config import get_settings
from core.logger import configure_logging, get_logger


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    get_logger("app").info("Application startup")
    initialize_database()
    yield
    get_logger("app").info("Application shutdown")


app = FastAPI(title="Productivity PWA API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UserId = Annotated[int, Header(alias="X-User-Id", gt=0)]


def get_ai_adapter() -> OpenRouterAdapter:
    return OpenRouterAdapter(get_settings())


def _next_due_date(activity: Activity) -> datetime:
    due_date = activity.due_date
    if activity.recurrence == Recurrence.DAILY:
        return due_date + timedelta(days=1)
    if activity.recurrence == Recurrence.WEEKLY:
        return due_date + timedelta(weeks=1)
    month_index = due_date.year * 12 + due_date.month
    year, month_offset = divmod(month_index, 12)
    month = month_offset + 1
    day = min(due_date.day, calendar.monthrange(year, month)[1])
    return due_date.replace(year=year, month=month, day=day)


def _daily_plan(db: Session, user_id: int) -> DailyPlanRead:
    today = datetime.now(timezone.utc).date()
    plan = db.scalar(
        select(DailyPlan).where(DailyPlan.user_id == user_id, DailyPlan.plan_date == today)
    )
    if plan is None:
        plan = DailyPlan(user_id=user_id, plan_date=today, available_minutes=360)
        db.add(plan)
        db.commit()
        db.refresh(plan)

    activities = list(
        db.scalars(
            select(Activity).where(
                Activity.user_id == user_id,
                Activity.status != ActivityStatus.COMPLETED,
                Activity.due_date
                < datetime.combine(today + timedelta(days=8), datetime.min.time(), timezone.utc),
            )
        )
    )
    priority_order = {"URGENT": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}
    activities.sort(key=lambda item: (priority_order[item.priority.value], item.due_date))

    selected: list[Activity] = []
    deferred: list[Activity] = []
    planned_minutes = 0
    for activity in activities:
        estimate = activity.estimated_minutes or 30
        if planned_minutes + estimate <= plan.available_minutes:
            selected.append(activity)
            planned_minutes += estimate
        else:
            deferred.append(activity)

    return DailyPlanRead(
        plan_date=today,
        available_minutes=plan.available_minutes,
        planned_minutes=planned_minutes,
        selected=[ActivityRead.model_validate(item) for item in selected],
        deferred=[ActivityRead.model_validate(item) for item in deferred],
    )


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Productivity PWA API is running"}


@app.get("/api/v1/activities", response_model=list[ActivityRead])
def list_activities(
    user_id: UserId = 1, db: Session = Depends(get_db)
) -> list[Activity]:
    return list(
        db.scalars(
            select(Activity).where(Activity.user_id == user_id).order_by(Activity.due_date)
        )
    )


@app.post(
    "/api/v1/activities",
    response_model=ActivityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_activity(
    payload: ActivityCreate, user_id: UserId = 1, db: Session = Depends(get_db)
) -> Activity:
    activity = Activity(user_id=user_id, **payload.model_dump())
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@app.get("/api/v1/activities/{activity_id}", response_model=ActivityRead)
def get_activity(
    activity_id: int, user_id: UserId = 1, db: Session = Depends(get_db)
) -> Activity:
    activity = db.scalar(
        select(Activity).where(Activity.id == activity_id, Activity.user_id == user_id)
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@app.patch("/api/v1/activities/{activity_id}", response_model=ActivityRead)
def update_activity(
    activity_id: int,
    payload: ActivityPatch,
    user_id: UserId = 1,
    db: Session = Depends(get_db),
) -> Activity:
    activity = db.scalar(
        select(Activity).where(Activity.id == activity_id, Activity.user_id == user_id)
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    previous_status = activity.status
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
        setattr(activity, field, value)
    if (
        previous_status != ActivityStatus.COMPLETED
        and activity.status == ActivityStatus.COMPLETED
        and activity.recurrence != Recurrence.ONCE
        and activity.next_occurrence_id is None
    ):
        next_activity = Activity(
            user_id=activity.user_id,
            title=activity.title,
            category=activity.category,
            due_date=_next_due_date(activity),
            recurrence=activity.recurrence,
            priority=activity.priority,
            estimated_minutes=activity.estimated_minutes,
            energy_level=activity.energy_level,
            parent_activity_id=activity.id,
        )
        db.add(next_activity)
        db.flush()
        activity.next_occurrence_id = next_activity.id
    db.commit()
    db.refresh(activity)
    return activity


@app.delete("/api/v1/activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    activity_id: int, user_id: UserId = 1, db: Session = Depends(get_db)
) -> Response:
    activity = db.scalar(
        select(Activity).where(Activity.id == activity_id, Activity.user_id == user_id)
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.delete(activity)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/transactions", response_model=list[TransactionRead])
def list_transactions(
    user_id: UserId = 1, db: Session = Depends(get_db)
) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.occurred_at.desc())
        )
    )


@app.post(
    "/api/v1/transactions",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    payload: TransactionCreate, user_id: UserId = 1, db: Session = Depends(get_db)
) -> Transaction:
    if payload.linked_activity_id is not None:
        activity = db.scalar(
            select(Activity).where(
                Activity.id == payload.linked_activity_id,
                Activity.user_id == user_id,
            )
        )
        if activity is None:
            raise HTTPException(status_code=404, detail="Activity not found")
    transaction = Transaction(user_id=user_id, **payload.model_dump())
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@app.delete("/api/v1/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: int, user_id: UserId = 1, db: Session = Depends(get_db)
) -> Response:
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id, Transaction.user_id == user_id
        )
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(transaction)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/reflections", response_model=list[ReflectionRead])
def list_reflections(
    user_id: UserId = 1, db: Session = Depends(get_db)
) -> list[Reflection]:
    return list(
        db.scalars(
            select(Reflection)
            .where(Reflection.user_id == user_id)
            .order_by(Reflection.created_at.desc())
        )
    )


@app.post(
    "/api/v1/reflections",
    response_model=ReflectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_reflection(
    payload: ReflectionCreate, user_id: UserId = 1, db: Session = Depends(get_db)
) -> Reflection:
    reflection = Reflection(user_id=user_id, **payload.model_dump())
    db.add(reflection)
    db.commit()
    db.refresh(reflection)
    return reflection


@app.delete("/api/v1/reflections/{reflection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reflection(
    reflection_id: int, user_id: UserId = 1, db: Session = Depends(get_db)
) -> Response:
    reflection = db.scalar(
        select(Reflection).where(
            Reflection.id == reflection_id, Reflection.user_id == user_id
        )
    )
    if reflection is None:
        raise HTTPException(status_code=404, detail="Reflection not found")
    db.delete(reflection)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/v1/activities/{activity_id}/checklist",
    response_model=ActivityChecklistItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_checklist_item(
    activity_id: int,
    payload: ActivityChecklistItemCreate,
    user_id: UserId = 1,
    db: Session = Depends(get_db),
) -> ActivityChecklistItem:
    activity = db.scalar(
        select(Activity).where(Activity.id == activity_id, Activity.user_id == user_id)
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    item = ActivityChecklistItem(
        activity_id=activity.id,
        title=payload.title,
        position=len(activity.checklist_items),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.patch(
    "/api/v1/activities/{activity_id}/checklist/{item_id}",
    response_model=ActivityChecklistItemRead,
)
def update_checklist_item(
    activity_id: int,
    item_id: int,
    payload: ActivityChecklistItemPatch,
    user_id: UserId = 1,
    db: Session = Depends(get_db),
) -> ActivityChecklistItem:
    item = db.scalar(
        select(ActivityChecklistItem)
        .join(Activity)
        .where(
            ActivityChecklistItem.id == item_id,
            ActivityChecklistItem.activity_id == activity_id,
            Activity.user_id == user_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@app.delete(
    "/api/v1/activities/{activity_id}/checklist/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_checklist_item(
    activity_id: int,
    item_id: int,
    user_id: UserId = 1,
    db: Session = Depends(get_db),
) -> Response:
    item = db.scalar(
        select(ActivityChecklistItem)
        .join(Activity)
        .where(
            ActivityChecklistItem.id == item_id,
            ActivityChecklistItem.activity_id == activity_id,
            Activity.user_id == user_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/focus/active", response_model=FocusSessionRead | None)
def get_active_focus(
    user_id: UserId = 1, db: Session = Depends(get_db)
) -> FocusSession | None:
    return db.scalar(
        select(FocusSession).where(
            FocusSession.user_id == user_id, FocusSession.ended_at.is_(None)
        )
    )


@app.post(
    "/api/v1/activities/{activity_id}/focus/start",
    response_model=FocusSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def start_focus(
    activity_id: int, user_id: UserId = 1, db: Session = Depends(get_db)
) -> FocusSession:
    activity = db.scalar(
        select(Activity).where(Activity.id == activity_id, Activity.user_id == user_id)
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    if activity.status == ActivityStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Cannot focus on a completed activity")
    active = db.scalar(
        select(FocusSession).where(
            FocusSession.user_id == user_id, FocusSession.ended_at.is_(None)
        )
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="A focus session is already running")
    session = FocusSession(
        user_id=user_id,
        activity_id=activity_id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@app.post("/api/v1/focus/{session_id}/stop", response_model=FocusSessionRead)
def stop_focus(
    session_id: int, user_id: UserId = 1, db: Session = Depends(get_db)
) -> FocusSession:
    session = db.scalar(
        select(FocusSession).where(
            FocusSession.id == session_id,
            FocusSession.user_id == user_id,
            FocusSession.ended_at.is_(None),
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Active focus session not found")
    ended_at = datetime.now(timezone.utc)
    started_at = session.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    session.ended_at = ended_at
    session.duration_seconds = max(1, int((ended_at - started_at).total_seconds()))
    if session.activity_id is not None:
        activity = db.scalar(
            select(Activity).where(
                Activity.id == session.activity_id, Activity.user_id == user_id
            )
        )
        if activity is not None:
            activity.focus_seconds += session.duration_seconds
    db.commit()
    db.refresh(session)
    return session


@app.get("/api/v1/planning/today", response_model=DailyPlanRead)
def get_today_plan(
    user_id: UserId = 1, db: Session = Depends(get_db)
) -> DailyPlanRead:
    return _daily_plan(db, user_id)


@app.put("/api/v1/planning/today", response_model=DailyPlanRead)
def update_today_plan(
    payload: DailyPlanUpdate,
    user_id: UserId = 1,
    db: Session = Depends(get_db),
) -> DailyPlanRead:
    today = datetime.now(timezone.utc).date()
    plan = db.scalar(
        select(DailyPlan).where(
            DailyPlan.user_id == user_id, DailyPlan.plan_date == today
        )
    )
    if plan is None:
        plan = DailyPlan(
            user_id=user_id,
            plan_date=today,
            available_minutes=payload.available_minutes,
        )
        db.add(plan)
    else:
        plan.available_minutes = payload.available_minutes
    db.commit()
    return _daily_plan(db, user_id)


@app.post(
    "/api/v1/ai/activities/{activity_id}/motivation",
    response_model=AIResponseRead,
)
async def motivate_activity(
    activity_id: int,
    payload: MotivationRequest,
    user_id: UserId = 1,
    db: Session = Depends(get_db),
    adapter: OpenRouterAdapter = Depends(get_ai_adapter),
) -> AIResponseRead:
    activity = db.scalar(
        select(Activity).where(Activity.id == activity_id, Activity.user_id == user_id)
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    prompt = build_motivation_prompt(
        {
            "title": activity.title,
            "category": activity.category,
            "status": activity.status.value,
            "progress": activity.progress,
            "priority": activity.priority.value,
            "estimated_minutes": activity.estimated_minutes,
        },
        payload.current_goal,
        payload.available_minutes,
    )
    result = await adapter.complete("motivation", prompt.system, prompt.user)
    return AIResponseRead(text=result.text, fallback=result.fallback, scenario=result.scenario)


@app.post("/api/v1/ai/time-management", response_model=AIResponseRead)
async def advise_time_management(
    payload: TimeManagementRequest,
    user_id: UserId = 1,
    db: Session = Depends(get_db),
    adapter: OpenRouterAdapter = Depends(get_ai_adapter),
) -> AIResponseRead:
    activities = db.scalars(
        select(Activity)
        .where(Activity.user_id == user_id, Activity.status != ActivityStatus.COMPLETED)
        .order_by(Activity.due_date)
    )
    tasks = [
        {
            "title": activity.title,
            "status": activity.status.value,
            "priority": activity.priority.value,
            "estimated_minutes": activity.estimated_minutes,
            "due_date": activity.due_date.isoformat(),
        }
        for activity in activities
    ]
    prompt = build_time_management_prompt(tasks, payload.available_minutes)
    result = await adapter.complete("time_management", prompt.system, prompt.user)
    return AIResponseRead(text=result.text, fallback=result.fallback, scenario=result.scenario)


@app.post("/api/v1/ai/decompose", response_model=AIResponseRead)
async def decompose_activity(
    payload: DecompositionRequest,
    adapter: OpenRouterAdapter = Depends(get_ai_adapter),
) -> AIResponseRead:
    prompt = build_decomposition_prompt(payload.title, payload.description)
    result = await adapter.complete("decomposition", prompt.system, prompt.user)
    return AIResponseRead(text=result.text, fallback=result.fallback, scenario=result.scenario)