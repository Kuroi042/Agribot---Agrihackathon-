"""Small SQLite store shared by the MQTT collector and Telegram bot."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("AGRIBOT_DB_PATH", Path(__file__).with_name("agribot.db")))


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with connect() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS inverter_state (
                id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL,
                updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS faults (
                code TEXT PRIMARY KEY, message TEXT NOT NULL,
                active INTEGER NOT NULL, updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS user_preferences (
                chat_id INTEGER PRIMARY KEY, language TEXT NOT NULL)"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS telemetry_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL,
                fault_codes TEXT NOT NULL DEFAULT '[]', recorded_at TEXT NOT NULL)"""
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(telemetry_history)")}
        if "fault_codes" not in columns:
            connection.execute("ALTER TABLE telemetry_history ADD COLUMN fault_codes TEXT NOT NULL DEFAULT '[]'")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS telemetry_history_recorded_at ON telemetry_history(recorded_at)"
        )


def save_state(payload: dict[str, Any], updated_at: str, faults: list[dict[str, str]] | None = None) -> None:
    with connect() as connection:
        connection.execute(
            """INSERT INTO inverter_state (id, payload, updated_at) VALUES (1, ?, ?)
               ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
               updated_at=excluded.updated_at""",
            (json.dumps(payload, separators=(",", ":")), updated_at),
        )
        connection.execute(
            "INSERT INTO telemetry_history (payload, fault_codes, recorded_at) VALUES (?, ?, ?)",
            (json.dumps(payload, separators=(",", ":")), json.dumps([fault["code"] for fault in faults or []]), updated_at),
        )


def get_history(limit: int = 1440) -> list[dict[str, Any]]:
    initialize_database()
    with connect() as connection:
        rows = connection.execute(
            """SELECT payload, fault_codes, recorded_at FROM telemetry_history
               ORDER BY id DESC LIMIT ?""", (limit,)
        ).fetchall()
    history = []
    for row in reversed(rows):
        payload = json.loads(row["payload"])
        payload["recorded_at"] = row["recorded_at"]
        payload["fault_codes"] = json.loads(row["fault_codes"])
        history.append(payload)
    return history


def get_state() -> dict[str, Any] | None:
    initialize_database()
    with connect() as connection:
        row = connection.execute(
            "SELECT payload, updated_at FROM inverter_state WHERE id=1"
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload"])
    payload["updated_at"] = row["updated_at"]
    return payload


def replace_faults(faults: list[dict[str, str]], updated_at: str) -> None:
    with connect() as connection:
        connection.execute("UPDATE faults SET active=0, updated_at=?", (updated_at,))
        for fault in faults:
            connection.execute(
                """INSERT INTO faults (code, message, active, updated_at)
                   VALUES (?, ?, 1, ?)
                   ON CONFLICT(code) DO UPDATE SET message=excluded.message,
                   active=1, updated_at=excluded.updated_at""",
                (fault["code"], fault["message"], updated_at),
            )


def get_faults(active_only: bool = True) -> list[dict[str, Any]]:
    initialize_database()
    query = "SELECT code, message, active, updated_at FROM faults"
    if active_only:
        query += " WHERE active=1"
    query += " ORDER BY code"
    with connect() as connection:
        return [dict(row) for row in connection.execute(query).fetchall()]


def set_language(chat_id: int, language: str) -> None:
    with connect() as connection:
        connection.execute(
            """INSERT INTO user_preferences (chat_id, language) VALUES (?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET language=excluded.language""",
            (chat_id, language),
        )


def get_language(chat_id: int) -> str:
    initialize_database()
    with connect() as connection:
        row = connection.execute(
            "SELECT language FROM user_preferences WHERE chat_id=?", (chat_id,)
        ).fetchone()
    return str(row["language"]) if row else "en"
