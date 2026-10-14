import os
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./productivity.db")
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


_ACTIVITY_COLUMN_UPGRADES = {
    "priority": "VARCHAR(6) NOT NULL DEFAULT 'NORMAL'",
    "estimated_minutes": "INTEGER",
    "energy_level": "VARCHAR(6) NOT NULL DEFAULT 'MEDIUM'",
    "focus_seconds": "INTEGER NOT NULL DEFAULT 0",
    "parent_activity_id": "INTEGER REFERENCES activities(id) ON DELETE SET NULL",
    "next_occurrence_id": "INTEGER REFERENCES activities(id) ON DELETE SET NULL",
}


def initialize_database(bind: Engine = engine) -> None:
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name != "sqlite":
        return

    existing_columns = {column["name"] for column in inspect(bind).get_columns("activities")}
    with bind.begin() as connection:
        for column_name, column_definition in _ACTIVITY_COLUMN_UPGRADES.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE activities ADD COLUMN {column_name} {column_definition}"
                    )
                )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_activities_next_occurrence_id ON activities(next_occurrence_id)"
            )
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
