"""
MedGuard AI synthetic demo safety engine.

Development/testing only. The included interaction rules are illustrative,
not clinically validated. Never use this script to make real prescribing
decisions.

New in this version:
- Suggests close medication-name matches for manual confirmation.
- Flags repeated exact generic ingredients as possible duplicates.
- Does not auto-resolve misspellings or claim a no-alert result means safe.
"""
from pathlib import Path
import re
from difflib import SequenceMatcher
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
MEDICATIONS_PATH = DATA_DIR / "medication_reference_demo.csv"
INTERACTIONS_PATH = DATA_DIR / "interaction_reference_demo.csv"


def clean_name(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_reference_data():
    if not MEDICATIONS_PATH.exists() or not INTERACTIONS_PATH.exists():
        raise FileNotFoundError(
            "Demo CSVs not found. Keep this script beside the data/ folder."
        )

    medications = pd.read_csv(MEDICATIONS_PATH).fillna("")
    interactions = pd.read_csv(INTERACTIONS_PATH).fillna("")

    name_to_generic = {}
    for _, row in medications.iterrows():
        generic = clean_name(row["generic_name"])
        if generic:
            name_to_generic[generic] = generic

        for brand in str(row["brand_names"]).split(";"):
            brand_key = clean_name(brand)
            if brand_key:
                name_to_generic[brand_key] = generic

    return medications, interactions, name_to_generic


def resolve_medication(name: str, name_to_generic: dict) -> dict:
    """Exact matches resolve; fuzzy matches are suggestions only."""
    key = clean_name(name)

    if key in name_to_generic:
        return {
            "input_name": name,
            "generic_name": name_to_generic[key],
            "status": "resolved",
            "confidence": "high",
            "suggested_matches": [],
            "message": "Exact match in the synthetic demo reference."
        }

    # Compare against both generic names and brand names, but never
    # silently accept a fuzzy match as the medicine's identity.
    scored = []
    for candidate in name_to_generic:
        score = SequenceMatcher(None, key, candidate).ratio()
        if score >= 0.72:
            scored.append((score, candidate))

    scored.sort(reverse=True)
    suggestions = []
    seen_generics = set()
    for score, candidate in scored:
        generic = name_to_generic[candidate]
        if generic in seen_generics:
            continue
        seen_generics.add(generic)
        suggestions.append({
            "candidate_name": candidate,
            "generic_name": generic,
            "similarity": round(score, 3)
        })
        if len(suggestions) == 3:
            break

    if suggestions:
        message = (
            "Possible matches are suggestions only. Confirm the exact medicine "
            "name with an authorized clinician/pharmacist before using a match."
        )
    else:
        message = (
            "No close match found in the demo reference. Confirm the medicine "
            "name with an authorized clinician/pharmacist; do not guess."
        )

    return {
        "input_name": name,
        "generic_name": None,
        "status": "manual_review_required",
        "confidence": "low",
        "suggested_matches": suggestions,
        "message": message
    }


def check_medication_list(medication_names):
    """
    Check submitted names against illustrative demo data.

    Duplicate detection only flags repeated exact generic ingredients after
    exact reference resolution. It does not infer therapeutic equivalence.
    """
    medications, interactions, name_to_generic = load_reference_data()
    resolved = [
        resolve_medication(name, name_to_generic)
        for name in medication_names
    ]

    alerts = []

    # Exact duplicate active-ingredient check.
    seen = {}
    for item in resolved:
        generic = item["generic_name"]
        if not generic:
            continue
        seen.setdefault(generic, []).append(item["input_name"])

    for generic, inputs in seen.items():
        if len(inputs) > 1:
            alerts.append({
                "alert_type": "possible_duplicate_ingredient",
                "severity": "review",
                "medications": inputs,
                "generic_name": generic,
                "suggested_action": (
                    "Verify whether the repeated ingredient is intentional by "
                    "checking the complete prescription and confirming with the "
                    "prescriber/pharmacist. Do not automatically discontinue it."
                ),
                "evidence_status": "Exact duplicate in submitted demo list",
                "confidence": "exact-name match",
                "limitations": (
                    "The demo list does not include dose, formulation, route, "
                    "timing, or clinical intent. This is a review prompt, not a "
                    "determination that the prescription is inappropriate."
                )
            })

    # Pairwise interaction checks against the illustrative table.
    for i in range(len(resolved)):
        left = resolved[i]["generic_name"]
        if not left:
            continue
        for j in range(i + 1, len(resolved)):
            right = resolved[j]["generic_name"]
            if not right:
                continue

            for _, rule in interactions.iterrows():
                pair = {
                    clean_name(rule["drug_a"]),
                    clean_name(rule["drug_b"])
                }
                if {left, right} == pair:
                    alerts.append({
                        "alert_type": rule["demo_alert_type"],
                        "severity": rule["demo_severity"],
                        "medications": [left, right],
                        "suggested_action": rule["demo_action"],
                        "evidence_status": rule["evidence_status"],
                        "confidence": "demo-reference match",
                        "limitations": (
                            "Illustrative synthetic rule only. Verify against an "
                            "authoritative clinical source and patient context."
                        )
                    })

    unresolved = [
        item for item in resolved if item["status"] != "resolved"
    ]

    return {
        "synthetic_demo_only": True,
        "medications_reviewed": list(medication_names),
        "resolved_medications": resolved,
        "alerts": alerts,
        "manual_review_required": unresolved,
        "summary": (
            "Demo reference checks completed. This is not a complete safety "
            "assessment; absence of an alert does not mean the regimen is safe."
        )
    }


if __name__ == "__main__":
    import json

    example = ["Coumadin", "Advil", "ibuprofn", "mysterymed", "metformin", "metformin"]
    print(json.dumps(check_medication_list(example), indent=2))
