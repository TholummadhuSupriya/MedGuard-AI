
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List

from safety_engine_demo import check_medication_list
from database_demo import (
    router as database_demo_router,
    initialize_database,
)
from auth_demo import router as auth_router
from fastapi import Depends
from auth_demo import router as auth_router, allow_roles
from fastapi.security import HTTPBearer


security = HTTPBearer()
app = FastAPI(
    title="MedGuard AI",
    description="Medical history and medication safety prototype",
    version="0.1.0",
)

app.include_router(auth_router)
initialize_database()
app.include_router(database_demo_router)

from qr_access_audit_demo import router as qr_router, initialize_qr_table

initialize_qr_table()
app.include_router(qr_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Synthetic demo records only. Do not enter real patient information.
PATIENTS = [
    {
        "id": "DEMO-001",
        "name": "Demo Patient One",
        "age": 65,
        "department": "General Medicine",
        "diagnoses": ["Demo diagnosis — not a clinical finding"],
        "medications": [],
        "records_status": "Synthetic demo data",
    },
    {
        "id": "DEMO-002",
        "name": "Demo Patient Two",
        "age": 52,
        "department": "Cardiology",
        "diagnoses": [],
        "medications": [],
        "records_status": "Synthetic demo data",
    },
]


@app.get("/")
def home():
    return {"project": "MedGuard AI", "status": "running"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/patients")
def get_patients(staff: dict = Depends(allow_roles("doctor", "nurse", "pharmacist", "admin"))):
    return PATIENTS


@app.get("/api/patients/{patient_id}/history")
def get_patient_history(patient_id: str, staff: dict = Depends(allow_roles("doctor", "nurse", "pharmacist", "admin"))):
    for patient in PATIENTS:
        if patient["id"] == patient_id:
            return patient

    raise HTTPException(status_code=404, detail="Patient not found")


class SafetyCheckRequest(BaseModel):
    medications: List[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Medication names to review"
    )


@app.post("/api/safety/check")
def run_safety_check(request: SafetyCheckRequest, staff: dict = Depends(allow_roles("doctor", "nurse", "pharmacist", "admin"))):
    """Run the synthetic MedGuard AI safety demo."""

    medications = [
        name.strip()
        for name in request.medications
        if name.strip()
    ]

    if not medications:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail="Provide at least one medication name."
        )

    return check_medication_list(medications)
