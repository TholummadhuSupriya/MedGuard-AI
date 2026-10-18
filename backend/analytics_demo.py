
"""MedGuard AI analytics for synthetic demo activity only."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from fastapi import APIRouter, Depends
from auth_demo import allow_roles
from database_demo import DB_PATH

router = APIRouter(prefix="/api/analytics", tags=["Demo analytics"])

ALLOWED_ROLES = ("doctor", "nurse", "pharmacist", "admin")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_analytics_table():
    """Create the activity table without modifying existing patient data."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS safety_check_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_count INTEGER NOT NULL DEFAULT 0,
                high_alert_count INTEGER NOT NULL DEFAULT 0,
                review_alert_count INTEGER NOT NULL DEFAULT 0,
                duplicate_alert_count INTEGER NOT NULL DEFAULT 0,
                unresolved_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )


def record_safety_check(result: dict):
    """Store aggregate counts only; do not store medication names."""
    alerts = result.get("alerts") or []
    unresolved = result.get("manual_review_required") or []

    high_count = sum(
        1 for alert in alerts
        if str(alert.get("severity", "")).lower() in {"high", "critical"}
    )
    duplicate_count = sum(
        1 for alert in alerts
        if "duplicate" in str(alert.get("alert_type", "")).lower()
    )
    review_count = sum(
        1 for alert in alerts
        if str(alert.get("severity", "")).lower()
        not in {"high", "critical"}
    )

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO safety_check_events (
                alert_count, high_alert_count, review_alert_count,
                duplicate_alert_count, unresolved_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                len(alerts),
                high_count,
                review_count,
                duplicate_count,
                len(unresolved),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def build_summary(rows, total_checks, since):
    """Pure summary function, also useful for unit tests."""
    events = [dict(row) for row in rows]
    return {
        "synthetic_demo_only": True,
        "period_days": 7,
        "total_checks": total_checks,
        "high_alerts": sum(row["high_alert_count"] for row in events),
        "review_alerts": sum(row["review_alert_count"] for row in events),
        "duplicate_alerts": sum(row["duplicate_alert_count"] for row in events),
        "unresolved_names": sum(row["unresolved_count"] for row in events),
        "daily_activity": [
            {
                "date": (since + timedelta(days=i)).date().isoformat(),
                "checks": sum(
                    1 for row in events
                    if str(row["created_at"])[:10]
                    == (since + timedelta(days=i)).date().isoformat()
                ),
            }
            for i in range(7)
        ],
        "recent_activity": [
            {
                "created_at": row["created_at"],
                "alert_count": row["alert_count"],
                "high_alert_count": row["high_alert_count"],
                "review_alert_count": row["review_alert_count"],
                "duplicate_alert_count": row["duplicate_alert_count"],
                "unresolved_count": row["unresolved_count"],
            }
            for row in sorted(
                events, key=lambda row: row["created_at"], reverse=True
            )[:10]
        ],
    }


@router.get("/summary")
def analytics_summary(
    staff: dict = Depends(allow_roles(*ALLOWED_ROLES)),
):
    """Return seven-day analytics for authorized demo staff."""
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=6)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    since_text = since.isoformat()

    with _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM safety_check_events"
        ).fetchone()[0]

        rows = conn.execute(
            """
            SELECT alert_count, high_alert_count, review_alert_count,
                   duplicate_alert_count, unresolved_count, created_at
            FROM safety_check_events
            WHERE created_at >= ?
            ORDER BY created_at DESC
            """,
            (since_text,),
        ).fetchall()

    return build_summary(rows, total, since)
