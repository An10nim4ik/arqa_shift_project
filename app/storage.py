import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .schemas import TripCreate

# Kazakhstan has used UTC+5 nationwide since March 2024.
SHIFT_TIMEZONE = ZoneInfo("Asia/Almaty")


class DuplicateTripConflict(Exception):
    """A trip ID was reused with different details."""


class TripStorage:
    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS trips (
                    id TEXT PRIMARY KEY,
                    start_utc TEXT NOT NULL,
                    end_utc TEXT NOT NULL,
                    local_day TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK (amount > 0),
                    payment TEXT NOT NULL CHECK (payment IN ('cash', 'card')),
                    commission INTEGER NOT NULL CHECK (commission >= 0 AND commission <= amount)
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_trips_day_start
                ON trips(local_day, start_utc)
            """)

    @staticmethod
    def _record(trip: TripCreate) -> tuple:
        start_utc = trip.start.astimezone(timezone.utc)
        end_utc = trip.end.astimezone(timezone.utc)
        local_day = trip.start.astimezone(SHIFT_TIMEZONE).date().isoformat()
        return (
            trip.id,
            start_utc.isoformat(),
            end_utc.isoformat(),
            local_day,
            trip.amount,
            trip.payment,
            trip.commission,
        )

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "start": row["start_utc"],
            "end": row["end_utc"],
            "amount": row["amount"],
            "payment": row["payment"],
            "commission": row["commission"],
        }

    def is_empty(self) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 0

    def add_trip(self, trip: TripCreate) -> tuple[bool, dict]:
        record = self._record(trip)
        with self.connect() as connection:
            cursor = connection.execute("""
                INSERT INTO trips
                    (id, start_utc, end_utc, local_day, amount, payment, commission)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
            """, record)
            created = cursor.rowcount == 1
            existing = connection.execute("SELECT * FROM trips WHERE id = ?", (trip.id,)).fetchone()
            if not created and tuple(existing[key] for key in (
                "id", "start_utc", "end_utc", "local_day", "amount", "payment", "commission"
            )) != record:
                raise DuplicateTripConflict("This trip ID already exists with different data")
            return created, self._to_dict(existing)

    def get_day(self, day: str) -> dict:
        with self.connect() as connection:
            rows = connection.execute("""
                SELECT * FROM trips WHERE local_day = ?
                ORDER BY start_utc ASC, id ASC
            """, (day,)).fetchall()
        trips = [self._to_dict(row) for row in rows]
        revenue = sum(trip["amount"] for trip in trips)
        commission = sum(trip["commission"] for trip in trips)
        return {
            "date": day,
            "summary": {
                "trip_count": len(trips),
                "revenue": revenue,
                "commission": commission,
                "net": revenue - commission,
                "cash": sum(t["amount"] for t in trips if t["payment"] == "cash"),
                "card": sum(t["amount"] for t in trips if t["payment"] == "card"),
            },
            "trips": trips,
        }
