import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from app.services.pet_auto.models import PetContentPlan, PetProfile
from app.utils import utils

_DB_FILENAME = "pet_auto.sqlite3"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def db_path() -> str:
    return os.path.join(utils.storage_dir("pet_auto", create=True), _DB_FILENAME)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_profiles (
                pet_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pet_content_plans (
                plan_id TEXT PRIMARY KEY,
                pet_id TEXT NOT NULL,
                plan_date TEXT NOT NULL,
                topic TEXT NOT NULL,
                script TEXT NOT NULL,
                status TEXT NOT NULL,
                task_id TEXT,
                videos TEXT NOT NULL,
                error_message TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(pet_id, plan_date)
            )
            """
        )


def save_profile(profile: PetProfile) -> PetProfile:
    init_db()
    payload = profile.model_dump()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO pet_profiles (pet_id, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(pet_id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (
                profile.pet_id,
                json.dumps(payload, ensure_ascii=False),
                profile.created_at,
                profile.updated_at,
            ),
        )
    return profile


def list_profiles(active_only: bool = False) -> list[PetProfile]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT payload FROM pet_profiles ORDER BY created_at DESC").fetchall()
    profiles = [PetProfile(**json.loads(row["payload"])) for row in rows]
    if active_only:
        return [profile for profile in profiles if profile.active]
    return profiles


def get_profile(pet_id: str) -> Optional[PetProfile]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT payload FROM pet_profiles WHERE pet_id = ?",
            (pet_id,),
        ).fetchone()
    if not row:
        return None
    return PetProfile(**json.loads(row["payload"]))


def delete_profile(pet_id: str) -> bool:
    init_db()
    with connect() as conn:
        cursor = conn.execute("DELETE FROM pet_profiles WHERE pet_id = ?", (pet_id,))
    return cursor.rowcount > 0


def save_plan(plan: PetContentPlan) -> PetContentPlan:
    init_db()
    payload = plan.model_dump()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO pet_content_plans (
                plan_id, pet_id, plan_date, topic, script, status, task_id,
                videos, error_message, payload, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(plan_id) DO UPDATE SET
                topic = excluded.topic,
                script = excluded.script,
                status = excluded.status,
                task_id = excluded.task_id,
                videos = excluded.videos,
                error_message = excluded.error_message,
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (
                plan.plan_id,
                plan.pet_id,
                plan.plan_date,
                plan.topic,
                plan.script,
                plan.status,
                plan.task_id,
                json.dumps(plan.videos, ensure_ascii=False),
                plan.error_message,
                json.dumps(payload, ensure_ascii=False),
                plan.created_at,
                plan.updated_at,
            ),
        )
    return plan


def get_plan(plan_id: str) -> Optional[PetContentPlan]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT payload FROM pet_content_plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
    if not row:
        return None
    return PetContentPlan(**json.loads(row["payload"]))


def get_plan_by_pet_date(pet_id: str, plan_date: str) -> Optional[PetContentPlan]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT payload FROM pet_content_plans WHERE pet_id = ? AND plan_date = ?",
            (pet_id, plan_date),
        ).fetchone()
    if not row:
        return None
    return PetContentPlan(**json.loads(row["payload"]))


def list_plans(pet_id: Optional[str] = None, limit: int = 50) -> list[PetContentPlan]:
    init_db()
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500
    with connect() as conn:
        if pet_id:
            rows = conn.execute(
                "SELECT payload FROM pet_content_plans WHERE pet_id = ? ORDER BY plan_date DESC, created_at DESC LIMIT ?",
                (pet_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT payload FROM pet_content_plans ORDER BY plan_date DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [PetContentPlan(**json.loads(row["payload"])) for row in rows]
