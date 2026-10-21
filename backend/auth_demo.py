
"""MedGuard AI: staff registration, email verification and login."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import sqlite3
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DB_PATH = BASE_DIR / "medguard_demo.db"

router = APIRouter(prefix="/api/auth", tags=["Staff authentication"])
security = HTTPBearer()
TOKEN_TTL_SECONDS = 3600
SELF_REGISTER_ROLES = {"doctor", "nurse", "pharmacist"}


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_auth_tables():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS staff_users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                full_name TEXT NOT NULL,
                department TEXT NOT NULL,
                role TEXT NOT NULL CHECK(
                    role IN ('doctor','nurse','pharmacist','admin')
                ),
                password_hash TEXT NOT NULL,
                email_verified INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS email_verification_codes (
                email TEXT PRIMARY KEY COLLATE NOCASE,
                code_hash TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)


def b64e(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(
        value + "=" * (-len(value) % 4)
    )


def token_secret() -> bytes:
    secret = os.getenv("MEDGUARD_TOKEN_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(
            status_code=503,
            detail="Server token secret is not configured correctly."
        )
    return secret.encode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    hashed = hashlib.scrypt(
        password.encode(), salt=salt,
        n=2**14, r=8, p=1, dklen=32
    )
    return f"scrypt${b64e(salt)}${b64e(hashed)}"


def check_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, expected = stored.split("$", 2)
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=b64d(salt),
            n=2**14, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(b64e(actual), expected)
    except (ValueError, TypeError):
        return False


def send_verification_email(email: str, code: str):
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")

    if not host or not sender:
        raise HTTPException(
            status_code=503,
            detail="Email is not configured. Set the SMTP variables in backend/.env."
        )

    message = EmailMessage()
    message["Subject"] = "Verify your MedGuard AI work email"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"Your verification code is {code}. "
        "It expires in 10 minutes."
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not send verification email. Check SMTP settings."
        ) from exc


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    department: str = Field(min_length=2, max_length=100)
    role: str
    password: str = Field(min_length=12, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^[0-9]{6}$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def issue_token(user: sqlite3.Row) -> str:
    now = int(time.time())
    payload = {
        "sub": user["email"],
        "role": user["role"],
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "iss": "medguard-demo",
    }
    body = b64e(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    signature = hmac.new(
        token_secret(), body.encode(), hashlib.sha256
    ).digest()
    return f"{body}.{b64e(signature)}"


def verify_token(token: str) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(
            token_secret(), body.encode(), hashlib.sha256
        ).digest()

        if not hmac.compare_digest(b64d(signature), expected):
            raise ValueError("Invalid signature")

        payload = json.loads(b64d(body))
        if payload.get("iss") != "medguard-demo":
            raise ValueError("Invalid issuer")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("Expired token")

        with connect() as conn:
            user = conn.execute(
                """SELECT email, role, email_verified, active
                   FROM staff_users WHERE email = ? COLLATE NOCASE""",
                (payload.get("sub"),)
            ).fetchone()

        if (
            not user
            or not user["active"]
            or not user["email_verified"]
            or user["role"] != payload.get("role")
        ):
            raise ValueError("Account is not active or verified")

        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired staff token."
        ) from exc


def get_current_staff(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    return verify_token(credentials.credentials)


def allow_roles(*roles: str):
    allowed = set(roles)

    def guard(staff: dict = Depends(get_current_staff)):
        if staff.get("role") not in allowed:
            raise HTTPException(
                status_code=403,
                detail="Your staff role cannot access this resource."
            )
        return staff

    return guard


initialize_auth_tables()


@router.post("/register", status_code=202)
def register(body: RegisterRequest):
    email = str(body.email).strip().lower()
    role = body.role.strip().lower()

    # Admin can NEVER be assigned through public registration.
    if role not in SELF_REGISTER_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Choose doctor, nurse, or pharmacist. "
                   "Admin accounts must be provisioned separately."
        )

    if (
        not any(c.isalpha() for c in body.password)
        or not any(c.isdigit() for c in body.password)
    ):
        raise HTTPException(
            status_code=400,
            detail="Password must contain letters and numbers."
        )

    now = datetime.now(timezone.utc).isoformat()
    code = f"{secrets.randbelow(1_000_000):06d}"

    with connect() as conn:
        existing = conn.execute(
            "SELECT email_verified FROM staff_users "
            "WHERE email = ? COLLATE NOCASE",
            (email,)
        ).fetchone()

        if existing and existing["email_verified"]:
            raise HTTPException(
                status_code=409,
                detail="An account already exists for this email."
            )

        conn.execute(
            """INSERT INTO staff_users
               (email, full_name, department, role, password_hash,
                email_verified, active, created_at)
               VALUES (?, ?, ?, ?, ?, 0, 1, ?)
               ON CONFLICT(email) DO UPDATE SET
                 full_name=excluded.full_name,
                 department=excluded.department,
                 role=excluded.role,
                 password_hash=excluded.password_hash,
                 email_verified=0, active=1""",
            (
                email, body.full_name.strip(),
                body.department.strip(), role,
                hash_password(body.password), now
            )
        )
        conn.execute(
            """INSERT INTO email_verification_codes
               (email, code_hash, expires_at, attempts, created_at)
               VALUES (?, ?, ?, 0, ?)
               ON CONFLICT(email) DO UPDATE SET
                 code_hash=excluded.code_hash,
                 expires_at=excluded.expires_at,
                 attempts=0, created_at=excluded.created_at""",
            (
                email, hashlib.sha256(code.encode()).hexdigest(),
                int(time.time()) + 600, now
            )
        )

    try:
        send_verification_email(email, code)
    except HTTPException:
        # Do not leave an unusable pending registration behind.
        with connect() as conn:
            conn.execute(
                "DELETE FROM email_verification_codes WHERE email=?",
                (email,)
            )
            conn.execute(
                "DELETE FROM staff_users WHERE email=? AND email_verified=0",
                (email,)
            )
        raise

    return {
        "message": "Verification code sent. It expires in 10 minutes.",
        "email": email
    }


@router.post("/verify-email")
def verify_email(body: VerifyEmailRequest):
    email = str(body.email).strip().lower()

    with connect() as conn:
        row = conn.execute(
            """SELECT code_hash, expires_at, attempts
               FROM email_verification_codes
               WHERE email=? COLLATE NOCASE""",
            (email,)
        ).fetchone()

        if (
            not row
            or row["expires_at"] < int(time.time())
            or row["attempts"] >= 5
        ):
            raise HTTPException(
                status_code=400,
                detail="Code invalid or expired. Register again."
            )

        supplied = hashlib.sha256(body.code.encode()).hexdigest()
        if not hmac.compare_digest(supplied, row["code_hash"]):
            conn.execute(
                "UPDATE email_verification_codes "
                "SET attempts=attempts+1 WHERE email=?",
                (email,)
            )
            raise HTTPException(
                status_code=400,
                detail="Incorrect verification code."
            )

        conn.execute(
            "UPDATE staff_users SET email_verified=1 WHERE email=?",
            (email,)
        )
        conn.execute(
            "DELETE FROM email_verification_codes WHERE email=?",
            (email,)
        )

    return {"message": "Email verified. You can now sign in."}


@router.post("/login")
def login(body: LoginRequest):
    email = str(body.email).strip().lower()

    with connect() as conn:
        user = conn.execute(
            "SELECT * FROM staff_users WHERE email=? COLLATE NOCASE",
            (email,)
        ).fetchone()

    if not user or not check_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password.")

    if not user["email_verified"]:
        raise HTTPException(403, "Verify your work email before signing in.")

    if not user["active"]:
        raise HTTPException(403, "Account disabled. Contact the administrator.")

    return {
        "access_token": issue_token(user),
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "staff": {
            "email": user["email"],
            "full_name": user["full_name"],
            "department": user["department"],
            "role": user["role"]
        }
    }


@router.get("/me")
def who_am_i(staff: dict = Depends(get_current_staff)):
    return {
        "email": staff["sub"],
        "role": staff["role"],
        "expires_at_epoch": staff["exp"]
    }
