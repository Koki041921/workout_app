# db.py
import sqlite3
from datetime import datetime
from typing import Any, List, Optional, Dict

DB_PATH = "workout.db"

# 共通の取得カラム（DRY原則のため定数化）
SELECT_COLS = "id, date, exercise, weight, reps, sets, volume, note, created_at"


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workout_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                exercise TEXT NOT NULL,
                weight REAL NOT NULL,
                reps INTEGER NOT NULL,
                sets INTEGER NOT NULL,
                volume REAL NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()


def insert_entry(d: str, exercise: str, weight: float, reps: int, sets: int, note: str) -> None:
    volume = float(weight) * int(reps) * int(sets)
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO workout_entries(date, exercise, weight, reps, sets, volume, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (d, exercise, weight, reps, sets, volume, note, now),
        )
        conn.commit()


def delete_entry(entry_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM workout_entries WHERE id = ?", (entry_id,))
        conn.commit()


def fetch_by_date(d: str) -> List[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute(
            f"""
            SELECT {SELECT_COLS}
            FROM workout_entries
            WHERE date = ?
            ORDER BY created_at DESC
            """,
            (d,),
        )
        return cur.fetchall()


def fetch_range(start_date: str, end_date: str) -> List[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute(
            f"""
            SELECT {SELECT_COLS}
            FROM workout_entries
            WHERE date BETWEEN ? AND ?
            ORDER BY date DESC, created_at DESC
            """,
            (start_date, end_date),
        )
        return cur.fetchall()


def fetch_last_for_exercise(exercise: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT date, weight, reps, sets, note
            FROM workout_entries
            WHERE exercise = ?
            ORDER BY date DESC, created_at DESC
            LIMIT 1
            """,
            (exercise,),
        )
        return cur.fetchone()


def fetch_last_day_entries_for_exercise(exercise: str):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT date FROM workout_entries WHERE exercise = ? ORDER BY date DESC LIMIT 1",
            (exercise,),
        )
        row = cur.fetchone()
        if not row:
            return []

        last_date = row["date"]

        cur2 = conn.execute(
            """
            SELECT date, weight, reps, sets, note
            FROM workout_entries
            WHERE exercise = ? AND date = ?
            ORDER BY created_at ASC
            """,
            (exercise, last_date),
        )
        return cur2.fetchall()


def fetch_recent_entries_for_exercise(exercise: str, limit: int = 300):
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT date, weight, reps, sets, note
            FROM workout_entries
            WHERE exercise = ?
            ORDER BY date DESC, created_at DESC
            LIMIT ?
            """,
            (exercise, int(limit)),
        )
        return cur.fetchall()


def update_entry(entry_id: int, weight: float, reps: int, sets: int, note: str) -> None:
    volume = float(weight) * int(reps) * int(sets)
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE workout_entries
            SET weight = ?, reps = ?, sets = ?, volume = ?, note = ?
            WHERE id = ?
            """,
            (weight, reps, sets, volume, note, entry_id),
        )
        conn.commit()
