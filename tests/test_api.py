from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from adapters.openrouter import OpenRouterAdapter
from backend.database import Base, get_db, initialize_database
from backend.main import app, get_ai_adapter
from core.config import Settings


@pytest.fixture()
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(bind=test_engine, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def create_activity(client: TestClient, user_id: int = 1) -> dict:
    response = client.post(
        "/api/v1/activities",
        headers={"X-User-Id": str(user_id)},
        json={
            "title": "Repair",
            "category": "Home",
            "due_date": datetime(2026, 10, 20, tzinfo=timezone.utc).isoformat(),
        },
    )
    assert response.status_code == 201
    return response.json()


def test_activity_defaults_and_owner_isolation(client: TestClient):
    activity = create_activity(client)

    assert activity["status"] == "PENDING"
    assert activity["progress"] == 0
    assert activity["recurrence"] == "ONCE"
    assert client.get(
        f"/api/v1/activities/{activity['id']}", headers={"X-User-Id": "2"}
    ).status_code == 404


def test_progress_out_of_range_is_rejected(client: TestClient):
    activity = create_activity(client)

    response = client.patch(
        f"/api/v1/activities/{activity['id']}", json={"progress": 101}
    )

    assert response.status_code == 422


def test_linked_transaction_requires_owned_activity(client: TestClient):
    activity = create_activity(client)

    response = client.post(
        "/api/v1/transactions",
        headers={"X-User-Id": "2"},
        json={"amount": "24.50", "category": "Materials", "linked_activity_id": activity["id"]},
    )

    assert response.status_code == 404


def test_deleting_activity_preserves_transaction_without_link(client: TestClient):
    activity = create_activity(client)
    transaction_response = client.post(
        "/api/v1/transactions",
        json={"amount": "24.50", "category": "Materials", "linked_activity_id": activity["id"]},
    )
    assert transaction_response.status_code == 201

    delete_response = client.delete(f"/api/v1/activities/{activity['id']}")
    transactions_response = client.get("/api/v1/transactions")

    assert delete_response.status_code == 204
    assert len(transactions_response.json()) == 1
    assert transactions_response.json()[0]["linked_activity_id"] is None


def test_activity_priority_effort_defaults_and_validation(client: TestClient):
    activity = create_activity(client)

    assert activity["priority"] == "NORMAL"
    assert activity["energy_level"] == "MEDIUM"
    assert activity["estimated_minutes"] is None
    invalid = client.post(
        "/api/v1/activities",
        json={
            "title": "Invalid estimate",
            "category": "Work",
            "due_date": datetime(2026, 10, 20, tzinfo=timezone.utc).isoformat(),
            "estimated_minutes": 0,
        },
    )
    assert invalid.status_code == 422


def test_checklist_items_are_nested_and_owner_scoped(client: TestClient):
    activity = create_activity(client)
    item_response = client.post(
        f"/api/v1/activities/{activity['id']}/checklist", json={"title": "Gather materials"}
    )
    item = item_response.json()

    assert item_response.status_code == 201
    assert client.patch(
        f"/api/v1/activities/{activity['id']}/checklist/{item['id']}",
        headers={"X-User-Id": "2"},
        json={"completed": True},
    ).status_code == 404
    assert client.patch(
        f"/api/v1/activities/{activity['id']}/checklist/{item['id']}",
        json={"completed": True},
    ).json()["completed"] is True
    assert client.get(f"/api/v1/activities/{activity['id']}").json()["checklist_items"][0]["title"] == "Gather materials"


def test_focus_session_is_exclusive_and_updates_activity_total(client: TestClient):
    first = create_activity(client)
    second = create_activity(client)
    session = client.post(f"/api/v1/activities/{first['id']}/focus/start")
    assert session.status_code == 201
    assert client.get("/api/v1/focus/active").json()["id"] == session.json()["id"]
    assert client.post(f"/api/v1/activities/{second['id']}/focus/start").status_code == 409

    stopped = client.post(f"/api/v1/focus/{session.json()['id']}/stop")

    assert stopped.status_code == 200
    assert stopped.json()["duration_seconds"] >= 1
    assert client.get("/api/v1/focus/active").json() is None
    assert client.get(f"/api/v1/activities/{first['id']}").json()["focus_seconds"] >= 1


def test_recurring_activity_creates_only_one_next_occurrence(client: TestClient):
    response = client.post(
        "/api/v1/activities",
        json={
            "title": "Monthly review",
            "category": "Work",
            "due_date": datetime(2026, 1, 31, 9, tzinfo=timezone.utc).isoformat(),
            "recurrence": "MONTHLY",
            "priority": "HIGH",
        },
    )
    activity = response.json()
    completed = client.patch(
        f"/api/v1/activities/{activity['id']}", json={"status": "COMPLETED"}
    ).json()
    next_activity = client.get(
        f"/api/v1/activities/{completed['next_occurrence_id']}"
    ).json()

    assert response.status_code == 201
    assert next_activity["parent_activity_id"] == activity["id"]
    assert next_activity["due_date"].startswith("2026-02-28")
    client.patch(f"/api/v1/activities/{activity['id']}", json={"status": "COMPLETED"})
    assert len(client.get("/api/v1/activities").json()) == 2


def test_daily_plan_respects_capacity_and_priority(client: TestClient):
    today = datetime.now(timezone.utc).replace(hour=23, minute=0, second=0, microsecond=0)
    for title, priority, estimate in [
        ("Long high-priority task", "HIGH", 50),
        ("Short urgent task", "URGENT", 20),
    ]:
        response = client.post(
            "/api/v1/activities",
            json={
                "title": title,
                "category": "Work",
                "due_date": today.isoformat(),
                "priority": priority,
                "estimated_minutes": estimate,
            },
        )
        assert response.status_code == 201

    plan = client.put("/api/v1/planning/today", json={"available_minutes": 60})

    assert plan.status_code == 200
    assert plan.json()["planned_minutes"] == 20
    assert [activity["title"] for activity in plan.json()["selected"]] == ["Short urgent task"]
    assert [activity["title"] for activity in plan.json()["deferred"]] == ["Long high-priority task"]


def test_legacy_database_upgrade_preserves_existing_activity(tmp_path):
    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE activities ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title VARCHAR(200) NOT NULL, "
                "category VARCHAR(100) NOT NULL, due_date DATETIME NOT NULL, "
                "status VARCHAR(20) NOT NULL, progress INTEGER NOT NULL, recurrence VARCHAR(20) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO activities "
                "(id, user_id, title, category, due_date, status, progress, recurrence) "
                "VALUES (1, 7, 'Keep this task', 'Work', '2026-10-20 09:00:00', 'PENDING', 0, 'ONCE')"
            )
        )

    initialize_database(legacy_engine)

    columns = {column["name"] for column in inspect(legacy_engine).get_columns("activities")}
    with legacy_engine.connect() as connection:
        row = connection.execute(text("SELECT title, priority, energy_level FROM activities WHERE id = 1")).one()

    assert {"priority", "estimated_minutes", "energy_level", "focus_seconds"} <= columns
    assert row == ("Keep this task", "NORMAL", "MEDIUM")
    legacy_engine.dispose()


def test_ai_decomposition_uses_fallback_without_api_key(client: TestClient):
    app.dependency_overrides[get_ai_adapter] = lambda: OpenRouterAdapter(
        Settings(_env_file=None, openrouter_api_key=None)
    )

    response = client.post(
        "/api/v1/ai/decompose",
        json={"title": "Prepare a presentation", "description": "A large project"},
    )

    assert response.status_code == 200
    assert response.json()["scenario"] == "decomposition"
    assert response.json()["fallback"] is True
    assert "10 минут" in response.json()["text"]
