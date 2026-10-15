"""MedGuard AI QR reference + audit trail demo.

Synthetic records only. This module is NOT production authentication or authorization.
The audit trail records QR reference lifecycle events without storing raw QR tokens.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).resolve().parent / "medguard_demo.db"
router = APIRouter(prefix="/api/qr", tags=["QR demo references and audit"])


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now():
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _audit(conn, event_type: str, outcome: str, patient_id: str | None = None, detail: str | None = None):
    """Store metadata only; never store the bearer token itself."""
    conn.execute(
        """INSERT INTO qr_audit_log (event_type, outcome, patient_id, occurred_at, detail)
           VALUES (?, ?, ?, ?, ?)""",
        (event_type, outcome, patient_id, _now().isoformat(), detail),
    )


def initialize_qr_table():
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS qr_references (
            reference_id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            patient_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS qr_audit_log (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            outcome TEXT NOT NULL,
            patient_id TEXT,
            occurred_at TEXT NOT NULL,
            detail TEXT
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qr_audit_time ON qr_audit_log(occurred_at DESC)")


class CreateReference(BaseModel):
    patient_id: str = Field(min_length=1, max_length=80)
    expires_in_hours: int = Field(default=8, ge=1, le=24)


class TokenRequest(BaseModel):
    token: str = Field(min_length=16, max_length=200)


@router.post("/references")
def create_reference(body: CreateReference):
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(hours=body.expires_in_hours)
    with _connect() as conn:
        exists = conn.execute("SELECT patient_id FROM patients WHERE patient_id = ?", (body.patient_id,)).fetchone()
        if exists is None:
            _audit(conn, "create_reference", "denied", body.patient_id, "patient_not_found")
            raise HTTPException(status_code=404, detail="Synthetic patient record not found.")
        conn.execute(
            """INSERT INTO qr_references (token_hash, patient_id, created_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            (_token_hash(token), body.patient_id, now.isoformat(), expires.isoformat()),
        )
        _audit(conn, "create_reference", "success", body.patient_id, f"expires_in_hours={body.expires_in_hours}")
    return {
        "token": token,
        "patient_id": body.patient_id,
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "synthetic_demo_only": True,
        "note": "Token is returned once. This demo does not authenticate users.",
    }


@router.post("/resolve")
def resolve_reference(body: TokenRequest):
    now = _now()
    with _connect() as conn:
        row = conn.execute(
            "SELECT patient_id, expires_at, revoked_at FROM qr_references WHERE token_hash = ?",
            (_token_hash(body.token),),
        ).fetchone()
        if row is None:
            _audit(conn, "resolve_reference", "denied", None, "unknown_reference")
            raise HTTPException(status_code=404, detail="Reference is invalid or revoked.")
        patient_id = row["patient_id"]
        if row["revoked_at"] is not None:
            _audit(conn, "resolve_reference", "denied", patient_id, "revoked_reference")
            raise HTTPException(status_code=404, detail="Reference is invalid or revoked.")
        try:
            expires = datetime.fromisoformat(row["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
        except ValueError:
            _audit(conn, "resolve_reference", "error", patient_id, "invalid_expiry")
            raise HTTPException(status_code=410, detail="Reference expiry is invalid.")
        if expires <= now:
            _audit(conn, "resolve_reference", "denied", patient_id, "expired_reference")
            raise HTTPException(status_code=410, detail="Reference has expired.")
        _audit(conn, "resolve_reference", "success", patient_id, "reference_validated")
        return {
            "patient_id": patient_id,
            "expires_at": row["expires_at"],
            "synthetic_demo_only": True,
            "note": "This validates the QR bearer token only; it does not authenticate the person holding it.",
        }


@router.post("/revoke")
def revoke_reference(body: TokenRequest):
    now = _now().isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT patient_id FROM qr_references WHERE token_hash = ?",
            (_token_hash(body.token),),
        ).fetchone()
        if row is None:
            _audit(conn, "revoke_reference", "denied", None, "reference_not_found")
            raise HTTPException(status_code=404, detail="Reference not found or already revoked.")
        cursor = conn.execute(
            "UPDATE qr_references SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (now, _token_hash(body.token)),
        )
        if cursor.rowcount == 0:
            _audit(conn, "revoke_reference", "denied", row["patient_id"], "already_revoked")
            raise HTTPException(status_code=404, detail="Reference not found or already revoked.")
        _audit(conn, "revoke_reference", "success", row["patient_id"], "reference_revoked")
    return {"revoked": True, "synthetic_demo_only": True}


@router.get("/audit")
def list_qr_audit(limit: int = Query(default=50, ge=1, le=200)):
    """Demo-only audit view. Production deployments must protect this endpoint with staff auth."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT audit_id, event_type, outcome, patient_id, occurred_at, detail
               FROM qr_audit_log ORDER BY audit_id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return {
        "items": [dict(row) for row in rows],
        "count": len(rows),
        "synthetic_demo_only": True,
        "warning": "Unprotected demo endpoint. Add staff authentication and authorization before any real deployment.",
    }
