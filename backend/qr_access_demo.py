"""MedGuard AI QR reference demo router. Synthetic data only; not production security."""
from __future__ import annotations
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).resolve().parent / "medguard_demo.db"
router = APIRouter(prefix="/api/qr", tags=["QR demo references"])


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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


class CreateReference(BaseModel):
    patient_id: str = Field(min_length=1, max_length=80)
    expires_in_hours: int = Field(default=8, ge=1, le=24)

class TokenRequest(BaseModel):
    token: str = Field(min_length=16, max_length=200)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/references")
def create_reference(body: CreateReference):
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=body.expires_in_hours)
    with _connect() as conn:
        exists = conn.execute("SELECT patient_id FROM patients WHERE patient_id = ?", (body.patient_id,)).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Synthetic patient record not found.")
        conn.execute("INSERT INTO qr_references (token_hash, patient_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                     (_token_hash(token), body.patient_id, now.isoformat(), expires.isoformat()))
    return {"token": token, "patient_id": body.patient_id, "created_at": now.isoformat(),
            "expires_at": expires.isoformat(), "synthetic_demo_only": True,
            "note": "Token is returned once. This demo does not authenticate users."}


@router.post("/resolve")
def resolve_reference(body: TokenRequest):
    now = datetime.now(timezone.utc)
    with _connect() as conn:
        row = conn.execute("SELECT patient_id, expires_at, revoked_at FROM qr_references WHERE token_hash = ?", (_token_hash(body.token),)).fetchone()
        if row is None or row["revoked_at"] is not None:
            raise HTTPException(status_code=404, detail="Reference is invalid or revoked.")
        try:
            expires = datetime.fromisoformat(row["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=410, detail="Reference expiry is invalid.")
        if expires <= now:
            raise HTTPException(status_code=410, detail="Reference has expired.")
        return {"patient_id": row["patient_id"], "expires_at": row["expires_at"], "synthetic_demo_only": True}


@router.post("/revoke")
def revoke_reference(body: TokenRequest):
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cursor = conn.execute("UPDATE qr_references SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL", (now, _token_hash(body.token)))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Reference not found or already revoked.")
    return {"revoked": True, "synthetic_demo_only": True}
