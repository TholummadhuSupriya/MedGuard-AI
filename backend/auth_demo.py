"""MedGuard AI staff authentication helpers — local synthetic demo only.

Uses a short-lived HMAC-signed bearer token and demo staff accounts configured
through environment variables. This is a learning scaffold, not production IAM.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
security = HTTPBearer(
    scheme_name="BearerAuth",
    description="Enter your MedGuard staff access token"
)
router = APIRouter(prefix="/api/auth", tags=["Demo staff authentication"])

# Configure these environment variables before enabling authentication.
# Passwords are deliberately not hard-coded into the source file.
DEMO_USERS = {
    "doctor.demo": {
        "password_env": "MEDGUARD_DOCTOR_PASSWORD",
        "role": "doctor",
    },
    "nurse.demo": {
        "password_env": "MEDGUARD_NURSE_PASSWORD",
        "role": "nurse",
    },
    "pharmacist.demo": {
        "password_env": "MEDGUARD_PHARMACIST_PASSWORD",
        "role": "pharmacist",
    },
    "admin.demo": {
        "password_env": "MEDGUARD_ADMIN_PASSWORD",
        "role": "admin",
    },
}
TOKEN_SECRET_ENV = "MEDGUARD_TOKEN_SECRET"
TOKEN_TTL_SECONDS = 60 * 60


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=200)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret() -> bytes:
    value = os.getenv(TOKEN_SECRET_ENV, "")
    if len(value) < 32:
        raise HTTPException(
            status_code=503,
            detail=f"Configure {TOKEN_SECRET_ENV} with a random secret of at least 32 characters.",
        )
    return value.encode("utf-8")


def issue_token(username: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "iss": "medguard-demo",
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64encode(signature)}"


def verify_token(token: str) -> dict[str, Any]:
    try:
        body, signature_text = token.split(".", 1)
        supplied_signature = _b64decode(signature_text)
        expected_signature = hmac.new(
            _secret(), body.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("bad signature")
        payload = json.loads(_b64decode(body))
        if payload.get("iss") != "medguard-demo":
            raise ValueError("bad issuer")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired")
        username = payload.get("sub")
        role = payload.get("role")
        configured = DEMO_USERS.get(username)
        if not configured or configured["role"] != role:
            raise ValueError("unknown user or role")
        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired staff token.")



def get_current_staff(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    return verify_token(credentials.credentials)


def require_role(staff: dict[str, Any], allowed_roles: set[str]) -> None:
    if staff.get("role") not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="Your staff role is not allowed to perform this action.",
        )


def allow_roles(*allowed_roles: str):
    """FastAPI dependency factory enforcing staff roles on a route."""
    allowed = set(allowed_roles)

    def _role_guard(
        staff: dict[str, Any] = Depends(get_current_staff),
    ) -> dict[str, Any]:
        require_role(staff, allowed)
        return staff

    return _role_guard


@router.post("/login")
def login(body: LoginRequest):
    user = DEMO_USERS.get(body.username)
    expected_password = os.getenv(user["password_env"], "") if user else ""
    # Do not accept login until all demo credentials and the signing secret are configured.
    if not expected_password or not hmac.compare_digest(body.password, expected_password):
        raise HTTPException(status_code=401, detail="Invalid demo staff username or password.")
    token = issue_token(body.username, user["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "staff": {"username": body.username, "role": user["role"]},
        "synthetic_demo_only": True,
    }



@router.get("/me")
def who_am_i(
    staff: dict[str, Any] = Depends(get_current_staff),
):
    return {
        "username": staff["sub"],
        "role": staff["role"],
        "expires_at_epoch": staff["exp"],
        "synthetic_demo_only": True,
    }
