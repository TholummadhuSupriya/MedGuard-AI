"""

MedGuard AI — SQLite persistence router for synthetic demo data.



DEMO ONLY:

\- Seeds synthetic patients from data/synthetic_patients_demo.csv.

\- Stores visits and visit medication entries locally in SQLite.

\- No authentication/authorization is implemented here.

\- Do not store real patient information or deploy this demo as-is.

"""

from __future__ import annotations



import csv

import sqlite3

from datetime import datetime, timezone

from pathlib import Path

from typing import Optional



from fastapi import APIRouter, HTTPException, Depends
from auth_demo import get_current_staff, allow_roles

from pydantic import BaseModel, Field



BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

DB_PATH = BASE_DIR / "medguard_demo.db"

PATIENTS_CSV = DATA_DIR / "synthetic_patients_demo.csv"



router = APIRouter(prefix="/api/db", tags=["SQLite demo records"])





def get_connection() -> sqlite3.Connection:

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")

    return conn





def initialize_database() -> None:

    """Create tables and seed synthetic patients once."""

    with get_connection() as conn:

        conn.executescript(

            """

            CREATE TABLE IF NOT EXISTS patients (

                patient_id TEXT PRIMARY KEY,

                display_name TEXT NOT NULL,

                age INTEGER,

                weight_kg REAL,

                egfr REAL,

                pregnancy_status TEXT,

                department TEXT,

                diagnoses TEXT NOT NULL DEFAULT '',

                created_at TEXT NOT NULL

            );



            CREATE TABLE IF NOT EXISTS patient_medications (

                medication_id INTEGER PRIMARY KEY AUTOINCREMENT,

                patient_id TEXT NOT NULL,

                medication_name TEXT NOT NULL,

                source TEXT NOT NULL DEFAULT 'synthetic_seed',

                created_at TEXT NOT NULL,

                FOREIGN KEY(patient_id) REFERENCES patients(patient_id)

                    ON DELETE CASCADE

            );



            CREATE TABLE IF NOT EXISTS visits (

                visit_id INTEGER PRIMARY KEY AUTOINCREMENT,

                patient_id TEXT NOT NULL,

                visit_date TEXT NOT NULL,

                department TEXT,

                notes TEXT NOT NULL DEFAULT '',

                created_at TEXT NOT NULL,

                FOREIGN KEY(patient_id) REFERENCES patients(patient_id)

                    ON DELETE CASCADE

            );



            CREATE TABLE IF NOT EXISTS visit_medications (

                visit_medication_id INTEGER PRIMARY KEY AUTOINCREMENT,

                visit_id INTEGER NOT NULL,

                medication_name TEXT NOT NULL,

                FOREIGN KEY(visit_id) REFERENCES visits(visit_id)

                    ON DELETE CASCADE

            );

            """

        )



        existing = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]

        if existing > 0 or not PATIENTS_CSV.exists():

            return



        now = datetime.now(timezone.utc).isoformat()

        with PATIENTS_CSV.open("r", newline="", encoding="utf-8-sig") as csv_file:

            for row in csv.DictReader(csv_file):

                patient_id = row.get("patient_id", "").strip()

                if not patient_id:

                    continue



                # All seeded records are synthetic; names are generated labels.

                display_name = f"Demo Patient {patient_id[-3:]}"

                conn.execute(

                    """

                    INSERT OR IGNORE INTO patients

                    (patient_id, display_name, age, weight_kg, egfr,

                     pregnancy_status, department, diagnoses, created_at)

                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

                    """,

                    (

                        patient_id,

                        display_name,

                        int(row["age"]) if row.get("age") else None,

                        float(row["weight_kg"]) if row.get("weight_kg") else None,

                        float(row["egfr"]) if row.get("egfr") else None,

                        row.get("pregnancy_status", ""),

                        row.get("department", ""),

                        row.get("diagnoses", ""),

                        now,

                    ),

                )



                for med in row.get("current_medications", "").split(";"):

                    med = med.strip()

                    if med:

                        conn.execute(

                            """

                            INSERT INTO patient_medications

                            (patient_id, medication_name, source, created_at)

                            VALUES (?, ?, 'synthetic_seed', ?)

                            """,

                            (patient_id, med, now),

                        )



                conn.execute(

                    """

                    INSERT INTO visits

                    (patient_id, visit_date, department, notes, created_at)

                    VALUES (?, ?, ?, ?, ?)

                    """,

                    (

                        patient_id,

                        now[:10],

                        row.get("department", ""),

                        "Synthetic demo baseline record imported from CSV.",

                        now,

                    ),

                )





class VisitCreate(BaseModel):

    visit_date: Optional[str] = None

    department: Optional[str] = Field(default=None, max_length=100)

    notes: str = Field(default="", max_length=4000)

    medications: list[str] = Field(default_factory=list, max_length=50)





def _patient_dict(row: sqlite3.Row, medications: list[str]) -> dict:

    diagnoses = [d.strip() for d in (row["diagnoses"] or "").split(";") if d.strip()]

    return {

        "id": row["patient_id"],

        "patient_id": row["patient_id"],

        "name": row["display_name"],

        "age": row["age"],

        "weight_kg": row["weight_kg"],

        "egfr": row["egfr"],

        "pregnancy_status": row["pregnancy_status"],

        "department": row["department"],

        "diagnoses": diagnoses,

        "medications": medications,

        "is_synthetic": True,

    }





@router.get("/health")

def database_health():

    with get_connection() as conn:

        conn.execute("SELECT 1").fetchone()

    return {

        "database": "sqlite",

        "status": "ok",

        "synthetic_demo_only": True,

    }





@router.get("/patients")

def list_db_patients(staff: dict = Depends(allow_roles("doctor", "nurse", "pharmacist", "admin"))):

    with get_connection() as conn:

        patients = conn.execute(

            "SELECT * FROM patients ORDER BY patient_id"

        ).fetchall()

        output = []

        for patient in patients:

            meds = conn.execute(

                """

                SELECT medication_name FROM patient_medications

                WHERE patient_id = ? ORDER BY medication_id

                """,

                (patient["patient_id"],),

            ).fetchall()

            output.append(

                _patient_dict(patient, [m["medication_name"] for m in meds])

            )

    return {"synthetic_demo_only": True, "patients": output, "count": len(output)}





@router.get("/patients/{patient_id}/history")

def get_db_patient_history(patient_id: str, staff: dict = Depends(allow_roles("doctor", "nurse", "pharmacist", "admin"))):

    with get_connection() as conn:

        patient = conn.execute(

            "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)

        ).fetchone()

        if patient is None:

            raise HTTPException(status_code=404, detail="Patient record not found.")



        medications = conn.execute(

            """

            SELECT medication_name, source, created_at

            FROM patient_medications WHERE patient_id = ?

            ORDER BY medication_id

            """,

            (patient_id,),

        ).fetchall()



        visits = conn.execute(

            """

            SELECT visit_id, visit_date, department, notes, created_at

            FROM visits WHERE patient_id = ? ORDER BY visit_id DESC

            """,

            (patient_id,),

        ).fetchall()



        visit_results = []

        for visit in visits:

            visit_meds = conn.execute(

                """

                SELECT medication_name FROM visit_medications

                WHERE visit_id = ? ORDER BY visit_medication_id

                """,

                (visit["visit_id"],),

            ).fetchall()

            visit_results.append({

                "visit_id": visit["visit_id"],

                "visit_date": visit["visit_date"],

                "department": visit["department"],

                "notes": visit["notes"],

                "medications": [m["medication_name"] for m in visit_meds],

            })



        patient_obj = _patient_dict(

            patient, [m["medication_name"] for m in medications]

        )



    return {

        "synthetic_demo_only": True,

        "patient": patient_obj,

        "medication_history": [

            {

                "medication_name": m["medication_name"],

                "source": m["source"],

                "created_at": m["created_at"],

            }

            for m in medications

        ],

        "visits": visit_results,

    }





@router.post("/patients/{patient_id}/visits", status_code=201)

def create_db_visit(patient_id: str, visit: VisitCreate, staff: dict = Depends(allow_roles("doctor", "nurse", "admin"))):

    now = datetime.now(timezone.utc).isoformat()

    visit_date = visit.visit_date or now[:10]

    department = (visit.department or "").strip()

    notes = visit.notes.strip()

    medication_names = [

        str(m).strip() for m in visit.medications if str(m).strip()

    ]



    with get_connection() as conn:

        exists = conn.execute(

            "SELECT 1 FROM patients WHERE patient_id = ?", (patient_id,)

        ).fetchone()

        if not exists:

            raise HTTPException(status_code=404, detail="Patient record not found.")



        cursor = conn.execute(

            """

            INSERT INTO visits

            (patient_id, visit_date, department, notes, created_at)

            VALUES (?, ?, ?, ?, ?)

            """,

            (patient_id, visit_date, department, notes, now),

        )

        visit_id = cursor.lastrowid



        for medication in medication_names:

            conn.execute(

                """

                INSERT INTO visit_medications (visit_id, medication_name)

                VALUES (?, ?)

                """,

                (visit_id, medication),

            )



    return {

        "synthetic_demo_only": True,

        "message": "Synthetic demo visit saved.",

        "visit_id": visit_id,

        "patient_id": patient_id,

        "visit_date": visit_date,

        "department": department,

        "medications": medication_names,

    }
