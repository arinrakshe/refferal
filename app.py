"""Referral Ready — Track 3 hackathon prototype.

Flask backend that analyzes incoming referral packets with Azure OpenAI GPT-4o,
or a deterministic keyword fallback if Azure is unreachable. Every result is
shown to a human referral coordinator and must be explicitly approved before
any action is taken.

Run:
    venv/bin/python app.py
Then open http://127.0.0.1:8000.
"""

from __future__ import annotations

import concurrent.futures
import csv
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import AzureOpenAI


load_dotenv()

# Synthea synthetic patient data — pre-generated CSV sample from
# https://github.com/synthetichealth/synthea (April 2020 release).
SYNTHEA_DIR = Path(__file__).parent / "synthea"
SYNTHEA_PATIENTS = SYNTHEA_DIR / "patients.csv"
SYNTHEA_CONDITIONS = SYNTHEA_DIR / "conditions.csv"
SYNTHEA_MEDICATIONS = SYNTHEA_DIR / "medications.csv"
SYNTHEA_ENCOUNTERS = SYNTHEA_DIR / "encounters.csv"

# Today's clinical "now" for age + recency calculations.
TODAY = date(2026, 5, 28)

# Fallback CSV (hand-authored) — used only if Synthea files are missing.
PATIENTS_CSV = Path(__file__).parent / "patients.csv"

AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4-mini")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_KEY = os.getenv("AZURE_OPENAI_KEY")
PORT = int(os.getenv("PORT", "8000"))


SAMPLE_REFERRALS: list[dict[str, Any]] = [
    {
        "id": "ref-001",
        "patient_id": "7a8e4ef0-adf4-4e6d-8d28-5d36886547f4",  # Ernie Stamm
        "patient": "Ernie Stamm",
        "referring_provider": "Dr. Kim — Northbridge Primary Care (NPI 1234567890)",
        "specialty_requested": "Orthopedics",
        "reason": (
            "Persistent knee pain for 8 weeks. Conservative treatment "
            "(6 weeks PT, NSAIDs) has failed. Requesting orthopedic consultation "
            "and MRI evaluation."
        ),
        "attachments": [
            "Knee X-ray report (2026-04-12)",
            "PT progress notes (6 sessions)",
            "Medication list",
        ],
        "insurance": "BlueCross PPO — Member ID 1234567890",
        "patient_phone": "555-0142",
        "diagnosis_code": "M25.561",
        "urgency_stated": "Routine",
        "received_at": "2026-05-27",  # 1 day old — fresh
        "label": "Orthopedics · complete",
    },
    {
        "id": "ref-002",
        "patient_id": "50e7ede4-7ca1-4b2c-ae64-6b88b58eeaac",  # Marvel Wyman
        "patient": "Marvel Wyman",
        "referring_provider": "Dr. Patel — Lakeside Family Medicine",
        "specialty_requested": "Cardiology",
        "reason": "Chest discomfort.",
        "attachments": [],
        "insurance": "",
        "patient_phone": "555-0199",
        "diagnosis_code": "",
        "urgency_stated": "",
        "received_at": "2026-05-16",  # 12 days old — leakage risk
        "label": "Cardiology · sparse referral",
    },
    {
        "id": "ref-003",
        "patient_id": "0f5646bc-a156-4ec0-9252-5b592e3d3184",  # Mickey Crist
        "patient": "Mickey Crist",
        "referring_provider": "Dr. Davis — Westside Internal Medicine (NPI 9876543210)",
        "specialty_requested": "Neurology",
        "reason": (
            "Severe migraine flare over the past 5 days with intermittent visual "
            "aura. Requesting urgent neurology evaluation."
        ),
        "attachments": [
            "MRI brain report (2026-05-26)",
            "Lab panel (CBC, CMP)",
        ],
        "insurance": "UnitedHealthcare PPO — Member ID 4567890",
        "patient_phone": "555-0167",
        "diagnosis_code": "G43.909",
        "urgency_stated": "Urgent",
        "received_at": "2026-05-26",  # 2 days old — fresh
        "label": "Neurology · urgent & complete",
    },
    {
        "id": "ref-004",
        "patient_id": "c0346f60-1c3c-46b1-b448-368b5fee8761",  # Vashti Wolff
        "patient": "Vashti Wolff",
        "referring_provider": "Dr. Singh — Riverbend Family Health (NPI 1122334455)",
        "specialty_requested": "Gastroenterology",
        "reason": (
            "Follow-up colonoscopy requested for known colon polyp surveillance. "
            "Patient reports new intermittent abdominal cramping x 3 weeks."
        ),
        "attachments": [
            "Prior colonoscopy report (2024-09-10)",
            "Lab panel (CBC, CMP)",
        ],
        "insurance": "Aetna HMO — Member ID 5566778899",
        "patient_phone": "",
        "diagnosis_code": "K63.5",
        "urgency_stated": "Routine",
        "received_at": "2026-05-23",  # 5 days old — watch
        "label": "GI · missing patient contact",
    },
    {
        "id": "ref-005",
        "patient_id": "8908602e-5f0c-4f1e-847f-75a0043eeba7",  # Carlton Breitenberg
        "patient": "Carlton Breitenberg",
        "referring_provider": "Dr. Lin — Harborview Family Medicine (NPI 9988776655)",
        "specialty_requested": "Endocrinology",
        "reason": (
            "Recent hemoglobin A1c trending upward over the past 6 months "
            "despite metformin. Requesting endocrinology evaluation for "
            "intensified diabetes management."
        ),
        "attachments": [],
        "insurance": "Cigna PPO — Member ID 2233445566",
        "patient_phone": "555-0124",
        "diagnosis_code": "E11.65",
        "urgency_stated": "Routine",
        "received_at": "2026-05-20",  # 8 days old — leakage risk
        "label": "Endocrinology · missing labs",
    },
]


def _split_multi(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(";") if item.strip()]


_NAME_DIGITS = re.compile(r"\d+$")


def _clean_name(value: str) -> str:
    """Strip Synthea's trailing digits from names ('Ernie189' -> 'Ernie')."""
    return _NAME_DIGITS.sub("", (value or "").strip()).strip()


def _age_at(birthdate: str, reference: date = TODAY) -> int:
    try:
        b = date.fromisoformat(birthdate)
    except (TypeError, ValueError):
        return 0
    return max(0, (reference - b).days // 365)


SYNTHETIC_PAYERS = [
    "BlueCross PPO",
    "Aetna HMO",
    "UnitedHealthcare PPO",
    "Cigna PPO",
    "Humana Choice",
    "Medicare + Aetna Supplement",
]


def _synthetic_insurance(patient_id: str, age: int) -> str:
    # Deterministic round-robin so each patient consistently gets the same payer.
    if age >= 65:
        return "Medicare + Aetna Supplement"
    idx = sum(ord(c) for c in patient_id) % len(SYNTHETIC_PAYERS)
    return f"{SYNTHETIC_PAYERS[idx]} (synthetic)"


def load_synthea_patients(
    max_conditions: int = 10,
    max_medications: int = 8,
    max_visits: int = 5,
    keep_only_with_data: bool = True,
) -> dict[str, dict[str, Any]]:
    """Load Synthea CSV sample and project into the app's patient registry shape."""
    if not SYNTHEA_PATIENTS.exists():
        print(f"[synthea] sample not found at {SYNTHEA_DIR}", flush=True)
        return {}

    demographics: dict[str, dict[str, Any]] = {}
    with SYNTHEA_PATIENTS.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("DEATHDATE", "").strip():
                continue  # only living patients
            pid = row["Id"]
            demographics[pid] = {
                "first": _clean_name(row.get("FIRST", "")),
                "last": _clean_name(row.get("LAST", "")),
                "birthdate": row.get("BIRTHDATE", ""),
                "gender": row.get("GENDER", ""),
            }

    active_conditions: dict[str, list[str]] = defaultdict(list)
    with SYNTHEA_CONDITIONS.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("STOP", "").strip():
                continue  # only ongoing
            active_conditions[row["PATIENT"]].append(row["DESCRIPTION"])

    active_medications: dict[str, list[str]] = defaultdict(list)
    with SYNTHEA_MEDICATIONS.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("STOP", "").strip():
                continue
            active_medications[row["PATIENT"]].append(row["DESCRIPTION"])

    encounters: dict[str, list[tuple[str, str]]] = defaultdict(list)
    with SYNTHEA_ENCOUNTERS.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            start = (row.get("START") or "")[:10]
            desc = (row.get("DESCRIPTION") or "").strip()
            if not start or not desc:
                continue
            encounters[row["PATIENT"]].append((start, desc))

    registry: dict[str, dict[str, Any]] = {}
    for pid, demo in demographics.items():
        conds = list(dict.fromkeys(active_conditions.get(pid, [])))[:max_conditions]
        meds = list(dict.fromkeys(active_medications.get(pid, [])))[:max_medications]
        if keep_only_with_data and not (conds or meds):
            continue
        recent = sorted(encounters.get(pid, []), key=lambda x: x[0], reverse=True)[:max_visits]
        visits = [f"{when} {desc}" for when, desc in recent]
        age = _age_at(demo["birthdate"])
        name = f"{demo['first']} {demo['last']}".strip()
        registry[pid] = {
            "patient_id": pid,
            "name": name,
            "age": age,
            "gender": demo["gender"],
            "conditions": conds,
            "medications": meds,
            "recent_visits": visits,
            "insurance": _synthetic_insurance(pid, age),
            "referring_doctor": "",  # not present in this Synthea sample
            "source": "synthea",
        }
    return registry


def load_patients() -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    if not PATIENTS_CSV.exists():
        print(f"[patients] CSV not found at {PATIENTS_CSV}", flush=True)
        return registry
    with PATIENTS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = (row.get("patient_id") or "").strip()
            if not pid:
                continue
            try:
                age = int((row.get("age") or "0").strip())
            except ValueError:
                age = 0
            registry[pid] = {
                "patient_id": pid,
                "name": (row.get("name") or "").strip(),
                "age": age,
                "conditions": _split_multi(row.get("conditions", "")),
                "medications": _split_multi(row.get("medications", "")),
                "recent_visits": _split_multi(row.get("recent_visits", "")),
                "insurance": (row.get("insurance") or "").strip(),
                "referring_doctor": (row.get("referring_doctor") or "").strip(),
            }
    print(f"[patients] loaded {len(registry)} patient records.", flush=True)
    return registry


def build_patient_registry() -> dict[str, dict[str, Any]]:
    synthea = load_synthea_patients()
    if synthea:
        print(f"[patients] using Synthea sample ({len(synthea)} living patients with data).", flush=True)
        return synthea
    fallback = load_patients()
    if fallback:
        print(f"[patients] Synthea unavailable; using hand-authored CSV ({len(fallback)} patients).", flush=True)
    return fallback


PATIENT_REGISTRY: dict[str, dict[str, Any]] = build_patient_registry()


def lookup_patient(referral: dict[str, Any]) -> dict[str, Any] | None:
    pid = (referral.get("patient_id") or "").strip()
    if pid and pid in PATIENT_REGISTRY:
        return PATIENT_REGISTRY[pid]
    name = (referral.get("patient") or "").strip().lower()
    if not name:
        return None
    for record in PATIENT_REGISTRY.values():
        if record["name"].lower() == name:
            return record
    return None


SYSTEM_PROMPT = (
    "You are an experienced referral coordinator for a US healthcare clinic. "
    "You review referral packets for scheduling readiness with a confident, "
    "precise, action-oriented voice. You do not diagnose, choose treatment, or "
    "replace clinical triage; you assess whether the packet contains enough "
    "specific documentation for the receiving specialty to schedule and review.\n\n"
    "Ground every assessment in the supplied referral packet and EHR history. "
    "Explicitly cite patient-specific details when available: named conditions, "
    "active medications, recent visit dates and reasons, specialty requested, "
    "referral reason, diagnosis code, attachments, insurance, and contact "
    "information. Never invent facts. If a field is empty, say what is missing "
    "and why it matters for this patient's referral.\n\n"
    "Use a referral coordinator voice. Do not hedge or use vague AI phrasing "
    "such as 'it appears,' 'it may be worth considering,' 'possibly,' or "
    "'consider asking.' Write direct operational language: request, confirm, "
    "route, escalate, schedule, or hold pending the named item.\n\n"
    "Clinical-awareness rules:\n"
    "- If chart insurance is available, treat insurance as present even when "
    "the referral insurance field is blank, and cite the chart source.\n"
    "- In present_items, connect supporting packet or chart details to the "
    "referral: conditions, current medications, recent visits, labs, imaging, "
    "or notes that make the referral understandable.\n"
    "- In missing_items, do not list generic labels alone. Explain why each "
    "missing item matters clinically for this patient and specialty.\n"
    "- If high urgency is stated or strongly implied by the referral reason or "
    "recent visits, set readiness to Needs Review and give a coordinator action "
    "for clinical triage before routine scheduling.\n"
    "- The readiness score is the confidence field. Set it from 0-100 and make "
    "next_action a one-sentence rationale tied to the actual packet contents.\n\n"
    "Routing rules:\n"
    "- Always return routing_suggestion as one concise, specialty-specific "
    "recommendation string.\n"
    "- Name the best-fit specialty lane, clinic, or workflow and include any "
    "key scheduling prerequisite from the packet. Examples: 'Orthopedic Spine "
    "-- imaging required before scheduling.' or 'Cardiology -- clinical triage "
    "before routine scheduling for chest pain referral.'\n\n"
    "Draft email rules:\n"
    "- Leave draft_email empty when readiness is Ready.\n"
    "- When items are missing, address the receiving provider by role using the "
    "requested specialty, for example 'Dear Cardiology team,'.\n"
    "- Reference patient-specific history inline, including relevant conditions, "
    "medications, and recent visit dates or reasons when provided.\n"
    "- Ask for the exact missing items and explain why they are needed for this "
    "patient's referral.\n\n"
    "Return only a valid JSON object matching the requested schema. No markdown, "
    "no commentary outside JSON. Human review is required before any action."
)

USER_PROMPT_TEMPLATE = """Analyze this referral packet and return JSON matching this exact schema:

{
  "readiness": "Ready" | "Missing Info" | "Needs Review",
  "confidence": integer 0-100,
  "present_items": ["specific items present in the packet"],
  "missing_items": ["specific items missing or vague"],
  "urgency": "High" | "Medium" | "Low",
  "next_action": "one short sentence describing the coordinator's next step",
  "routing_suggestion": "specific specialty routing recommendation string",
  "draft_email": "full polite outreach email to the referring office requesting missing items, or empty string if nothing is missing",
  "safety_note": "one sentence explaining why human review is still required"
}

Rules:
- Use "Ready" only when everything needed to schedule is present (clear reason, diagnosis, insurance, patient contact, relevant attachments).
- Use "Missing Info" when one or more non-urgent items are missing but the referral is fixable with a quick outreach.
- Use "Needs Review" when urgency is high OR critical items (e.g. diagnosis and reason both vague) are missing.
- "urgency" reflects what the referral states or strongly implies. Do NOT make a clinical determination.
- Never invent information. If a field is empty or missing, treat it as missing.
- Use the named referral fields when writing each response: patient, patient_id, referring_provider, specialty_requested, reason, attachments, insurance, patient_phone, patient_dob, diagnosis_code, and urgency_stated.
- Use the named EHR history fields when provided: conditions, medications, recent_visits, insurance, referring_doctor, age, and name.
- present_items must include specific packet or chart facts, not generic confirmations. Example style: "Diagnosis code E11.65 is present for diabetes management" or "Chart lists Metformin 1000mg BID and Lisinopril 20mg daily."
- missing_items must state the missing item and why it matters for this patient and requested specialty. Example style: "Recent A1c/lab trend is missing; endocrinology needs the current diabetes control data for Sam Rivera's Type 2 diabetes referral."
- next_action must be one sentence that includes the readiness score rationale tied to actual packet contents.
- routing_suggestion must name the specific specialty route or clinic workflow and any scheduling prerequisite supported by the packet. Example style: "Endocrinology -- diabetes management; recent A1c labs required before scheduling."
- The draft email must be addressed to the receiving specialty team by role (for example, "Dear Cardiology team,") and must reference the patient's specific history details inline when available.
- Avoid vague phrasing such as "it appears," "it may be worth considering," "possibly," or "consider asking."

Referral packet (JSON):
"""


def get_azure_client() -> AzureOpenAI | None:
    if not AZURE_ENDPOINT or not AZURE_KEY:
        print("[azure] AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_KEY missing.", flush=True)
        return None
    try:
        return AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_KEY,
            api_version=AZURE_API_VERSION,
        )
    except Exception:
        return None


def call_azure(
    referral: dict[str, Any], patient_history: dict[str, Any] | None
) -> dict[str, Any] | None:
    client = get_azure_client()
    if client is None:
        print("[azure] no client (missing endpoint or key); using fallback.", flush=True)
        return None
    history_block = (
        "\n\nPatient history from clinic EHR (use this for smarter analysis):\n"
        + json.dumps(patient_history, indent=2)
        if patient_history
        else "\n\nPatient history from clinic EHR: NONE FOUND (treat referral as a new patient with no prior chart)."
    )
    try:
        completion = client.chat.completions.create(
            model=AZURE_DEPLOYMENT,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        USER_PROMPT_TEMPLATE
                        + json.dumps(referral, indent=2)
                        + history_block
                    ),
                },
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=900,
        )
        raw = completion.choices[0].message.content or ""
        return json.loads(raw)
    except Exception as exc:
        print(f"[azure] call failed ({type(exc).__name__}): {exc}; using fallback.", flush=True)
        return None


HIGH_URGENCY_KEYWORDS = [
    "urgent",
    "emergency",
    "emergent",
    "severe",
    "stat",
    "acute",
    "immediately",
    "chest pain",
    "shortness of breath",
    "vision changes",
    "stroke",
    "bleeding",
    "fainting",
    "syncope",
]
MEDIUM_URGENCY_KEYWORDS = ["soon", "worsening", "moderate", "progressing"]


def fallback_analysis(
    referral: dict[str, Any], patient_history: dict[str, Any] | None = None
) -> dict[str, Any]:
    required = {
        "reason": "Referral reason",
        "diagnosis_code": "Diagnosis code",
        "insurance": "Insurance information",
        "patient_phone": "Patient contact phone number",
    }
    missing_items: list[str] = []
    present_items: list[str] = []
    for key, label in required.items():
        value = (referral.get(key) or "").strip()
        if not value or value.lower() in {"none", "n/a", "unknown"}:
            # If insurance is missing on the referral but on file in the chart,
            # treat it as present.
            if key == "insurance" and patient_history and patient_history.get("insurance"):
                present_items.append("Insurance information (from patient chart)")
            else:
                missing_items.append(label)
        else:
            present_items.append(label)

    attachments = referral.get("attachments") or []
    if isinstance(attachments, list) and len(attachments) > 0:
        present_items.append("Supporting attachments")
    else:
        missing_items.append("Supporting attachments (imaging, labs, or notes)")

    if patient_history:
        present_items.append(
            f"Patient chart on file ({len(patient_history.get('conditions', []))} conditions, "
            f"{len(patient_history.get('medications', []))} active medications)"
        )

    reason = (referral.get("reason") or "").lower()
    urgency_stated = (referral.get("urgency_stated") or "").lower()
    if any(k in reason or k in urgency_stated for k in HIGH_URGENCY_KEYWORDS):
        urgency = "High"
    elif any(k in reason for k in MEDIUM_URGENCY_KEYWORDS):
        urgency = "Medium"
    else:
        urgency = "Low"

    if urgency == "High":
        readiness = "Needs Review"
        next_action = "Escalate to clinical reviewer for urgent triage before scheduling."
    elif not missing_items:
        readiness = "Ready"
        next_action = "Forward to scheduling for next available appointment."
    else:
        readiness = "Missing Info"
        next_action = "Contact the referring office to request the missing items before scheduling."

    if missing_items and readiness != "Ready":
        provider = referral.get("referring_provider", "the referring office")
        patient = referral.get("patient", "the patient")
        items_text = "\n".join(f"  - {item}" for item in missing_items)
        draft_email = (
            f"Subject: Additional Information Needed — Referral for {patient}\n\n"
            f"Hello {provider},\n\n"
            f"Thank you for the referral for {patient}. Before we can schedule "
            f"this appointment, we need the following items:\n\n"
            f"{items_text}\n\n"
            "Please reply with the missing information at your earliest "
            "convenience so we can move forward with scheduling. If you have "
            "questions, please feel free to call our intake line.\n\n"
            "Thank you,\n"
            "Referral Intake Team"
        )
    else:
        draft_email = ""

    specialty = (referral.get("specialty_requested") or "Specialty clinic").strip()
    reason_text = (referral.get("reason") or "").lower()
    attachments_text = " ".join(referral.get("attachments") or []).lower()
    if "orthopedic" in specialty.lower() or "knee" in reason_text:
        route_detail = "orthopedic consult; confirm relevant imaging is available before scheduling"
    elif "cardiology" in specialty.lower() or "chest pain" in reason_text:
        route_detail = "cardiology triage before routine scheduling for chest symptoms"
    elif "neurology" in specialty.lower() or "headache" in reason_text:
        route_detail = "neurology triage; confirm brain imaging or urgent visit notes are attached"
    elif "gastro" in specialty.lower() or "abdominal" in reason_text:
        route_detail = "GI evaluation; confirm symptom history and baseline labs are attached"
    elif "endocrinology" in specialty.lower() or "a1c" in reason_text or "diabetes" in reason_text:
        route_detail = "diabetes management; recent A1c labs required before scheduling"
    elif attachments_text:
        route_detail = "specialty review with attached supporting documentation"
    else:
        route_detail = "intake review pending specialty-specific supporting documentation"
    routing_suggestion = f"{specialty} -- {route_detail}."

    return {
        "readiness": readiness,
        "confidence": 70,
        "present_items": present_items,
        "missing_items": missing_items,
        "urgency": urgency,
        "next_action": next_action,
        "routing_suggestion": routing_suggestion,
        "draft_email": draft_email,
        "safety_note": (
            "Fallback rule-based analysis used because Azure OpenAI was "
            "unreachable. A human coordinator must review before any action."
        ),
        "source": "fallback",
    }


def normalize_readiness(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "ready":
        return "Ready"
    if text in {"missing info", "missing_info", "missing"}:
        return "Missing Info"
    return "Needs Review"


def normalize_urgency(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "high":
        return "High"
    if text == "medium":
        return "Medium"
    return "Low"


def to_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def normalize_result(result: dict[str, Any], source: str) -> dict[str, Any]:
    try:
        confidence = int(round(float(result.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0, min(100, confidence))

    return {
        "readiness": normalize_readiness(result.get("readiness")),
        "confidence": confidence,
        "present_items": to_list(result.get("present_items")),
        "missing_items": to_list(result.get("missing_items")),
        "urgency": normalize_urgency(result.get("urgency")),
        "next_action": str(result.get("next_action", "")).strip(),
        "routing_suggestion": str(result.get("routing_suggestion", "")).strip(),
        "draft_email": str(result.get("draft_email", "")).strip(),
        "safety_note": str(
            result.get(
                "safety_note",
                "Human review required before any scheduling or outreach action.",
            )
        ).strip(),
        "source": source,
    }


app = Flask(__name__, static_folder="static", template_folder="templates")


@app.route("/")
def index() -> Any:
    return render_template("index.html")


@app.route("/api/referrals", methods=["GET"])
def list_referrals() -> Any:
    return jsonify({"referrals": SAMPLE_REFERRALS})


_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def compute_aging(referral: dict[str, Any], today: date = TODAY) -> dict[str, Any]:
    """Return staleness info for a referral: days idle, color, leakage risk."""
    raw = (referral.get("received_at") or "").strip()
    if not raw:
        return {
            "received_at": "",
            "received_display": "—",
            "days_idle": None,
            "staleness": "unknown",
            "label": "No timestamp",
            "leakage_risk": False,
        }
    try:
        received = date.fromisoformat(raw)
    except ValueError:
        return {
            "received_at": raw,
            "received_display": raw,
            "days_idle": None,
            "staleness": "unknown",
            "label": "No timestamp",
            "leakage_risk": False,
        }

    days = (today - received).days
    if days > 7:
        staleness, label, risk = "red", "Leakage risk", True
    elif days >= 3:
        staleness, label, risk = "yellow", "Watch", False
    else:
        staleness, label, risk = "green", "Recent", False

    display = f"{_MONTH_NAMES[received.month]} {received.day}, {received.year}"
    return {
        "received_at": raw,
        "received_display": display,
        "days_idle": days,
        "staleness": staleness,
        "label": label,
        "leakage_risk": risk,
    }


_BULK_CACHE: list[dict[str, Any]] | None = None


def _analyze_referral(referral: dict[str, Any]) -> dict[str, Any]:
    """Run both chart-aware and generic analyses in parallel for a referral."""
    history = lookup_patient(referral)

    def run(with_history: dict[str, Any] | None) -> dict[str, Any]:
        azure_raw = call_azure(referral, with_history)
        if azure_raw is not None:
            return normalize_result(azure_raw, source="azure_openai")
        return normalize_result(
            fallback_analysis(referral, with_history), source="fallback"
        )

    without_chart: dict[str, Any] | None = None
    if history:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f_with = executor.submit(run, history)
            f_without = executor.submit(run, None)
            analysis = f_with.result()
            without_chart = f_without.result()
    else:
        analysis = run(None)

    return {
        "referral": referral,
        "patient_history": history,
        "analysis": analysis,
        "analysis_without_chart": without_chart,
        "aging": compute_aging(referral),
    }


@app.route("/api/triage-all", methods=["GET"])
def triage_all() -> Any:
    """Pre-analyze every sample referral and return a bulk summary.

    Cached in memory after the first call so the UI is instant on subsequent
    loads. Pass ?refresh=1 to force a re-run.
    """
    global _BULK_CACHE
    if request.args.get("refresh") == "1":
        _BULK_CACHE = None
    if _BULK_CACHE is None:
        # All 5 referrals analyzed in parallel; each one internally fans out to
        # two Azure calls (with and without chart context) when a chart exists.
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(2, len(SAMPLE_REFERRALS))
        ) as executor:
            _BULK_CACHE = list(executor.map(_analyze_referral, SAMPLE_REFERRALS))
        print(
            f"[bulk] pre-analyzed {len(_BULK_CACHE)} referrals and cached results.",
            flush=True,
        )
    return jsonify({"results": _BULK_CACHE})


@app.route("/api/patients/<patient_id>", methods=["GET"])
def get_patient(patient_id: str) -> Any:
    record = PATIENT_REGISTRY.get(patient_id)
    if record is None:
        return jsonify({"error": "Patient not found"}), 404
    return jsonify({"patient": record})


@app.route("/api/triage", methods=["POST"])
def triage() -> Any:
    payload = request.get_json(silent=True) or {}
    referral = payload.get("referral")
    free_text = payload.get("free_text")

    if not referral and free_text:
        referral = {
            "id": "custom",
            "patient": "Unknown (free-text input)",
            "referring_provider": "Unknown",
            "specialty_requested": "Unknown",
            "reason": str(free_text).strip(),
            "attachments": [],
            "insurance": "",
            "patient_phone": "",
            "patient_dob": "",
            "diagnosis_code": "",
            "urgency_stated": "",
            "raw_text": str(free_text).strip(),
        }

    if not referral:
        return jsonify({"error": "Missing 'referral' or 'free_text' in request body."}), 400

    patient_history = lookup_patient(referral)

    def analyze(history: dict[str, Any] | None) -> dict[str, Any]:
        azure_raw = call_azure(referral, history)
        if azure_raw is not None:
            return normalize_result(azure_raw, source="azure_openai")
        return normalize_result(
            fallback_analysis(referral, history), source="fallback"
        )

    analysis_without_chart: dict[str, Any] | None = None

    if patient_history:
        # Run both analyses in parallel so the comparison is fast.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_with = executor.submit(analyze, patient_history)
            future_without = executor.submit(analyze, None)
            analysis = future_with.result()
            analysis_without_chart = future_without.result()
    else:
        analysis = analyze(None)

    return jsonify(
        {
            "referral": referral,
            "patient_history": patient_history,
            "analysis": analysis,
            "analysis_without_chart": analysis_without_chart,
            "aging": compute_aging(referral),
        }
    )


# ─────────────────────── Approval log + time-saved counter ───────────────────────

MINUTES_SAVED_PER_APPROVAL = 18  # Estimated minutes a coordinator saves per AI-assisted approval

APPROVAL_LOG: list[dict[str, Any]] = []
STATS = {"approvals": 0, "rejects": 0, "minutes_saved": 0}


def _approval_stats_payload() -> dict[str, Any]:
    minutes = STATS["minutes_saved"]
    return {
        "approvals": STATS["approvals"],
        "rejects": STATS["rejects"],
        "minutes_saved": minutes,
        "hours": minutes // 60,
        "minutes_remainder": minutes % 60,
        "per_approval": MINUTES_SAVED_PER_APPROVAL,
    }


@app.route("/api/approve", methods=["POST"])
def approve() -> Any:
    """Demo-only endpoint. Logs an approval/reject event. Does NOT send anything.

    Increments the time-saved counter on approvals.
    """
    payload = request.get_json(silent=True) or {}
    referral_id = str(payload.get("referral_id", "unknown")).strip()
    action = str(payload.get("action", "approve")).strip().lower()
    notes = str(payload.get("notes", "")).strip()
    patient = str(payload.get("patient", "")).strip()
    readiness = str(payload.get("readiness", "")).strip()

    if action not in {"approve", "reject"}:
        return jsonify({"error": "action must be 'approve' or 'reject'"}), 400

    minutes_credited = 0
    if action == "approve":
        STATS["approvals"] += 1
        STATS["minutes_saved"] += MINUTES_SAVED_PER_APPROVAL
        minutes_credited = MINUTES_SAVED_PER_APPROVAL
    else:
        STATS["rejects"] += 1

    entry = {
        "referral_id": referral_id,
        "patient": patient or "Unknown patient",
        "action": action,
        "readiness": readiness,
        "notes": notes,
        "minutes_credited": minutes_credited,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    APPROVAL_LOG.insert(0, entry)  # newest first
    print(
        f"[APPROVE] action={action} referral={referral_id} patient={patient!r} "
        f"notes_len={len(notes)} stats={STATS}",
        flush=True,
    )
    return jsonify({"ok": True, "entry": entry, "stats": _approval_stats_payload()})


def _bulk_search_summaries() -> list[dict[str, Any]]:
    """Compact representation of the bulk cache for the search prompt."""
    bulk = _BULK_CACHE or []
    summaries: list[dict[str, Any]] = []
    for item in bulk:
        ref = item["referral"]
        analysis = item.get("analysis") or {}
        history = item.get("patient_history") or {}
        aging = item.get("aging") or {}
        summaries.append(
            {
                "id": ref.get("id"),
                "patient": ref.get("patient"),
                "specialty": ref.get("specialty_requested"),
                "referring_provider": ref.get("referring_provider"),
                "readiness": analysis.get("readiness"),
                "urgency": analysis.get("urgency"),
                "confidence": analysis.get("confidence"),
                "missing_items": analysis.get("missing_items", [])[:3],
                "routing_suggestion": analysis.get("routing_suggestion"),
                "days_idle": aging.get("days_idle"),
                "leakage_risk": aging.get("leakage_risk", False),
                "received_at": aging.get("received_at"),
                "patient_conditions": (history.get("conditions") or [])[:5],
                "patient_age": history.get("age"),
            }
        )
    return summaries


SEARCH_SYSTEM_PROMPT = (
    "You are a referral-queue search assistant. The user is a referral coordinator "
    "looking at a list of pre-analyzed patient referrals. Given a natural-language "
    "query, you filter the provided referrals and explain why each match qualifies.\n\n"
    "Hard rules:\n"
    "- Only return referral IDs that are present in the provided list. Never invent.\n"
    "- If nothing matches, return an empty list and explain that clearly.\n"
    "- Match on semantics, not literal substring. For example, 'urgent' should match "
    "any referral with high urgency or readiness Needs Review with high-severity reasons.\n"
    "- 'Missing labs' matches referrals whose missing_items mention labs, A1c, CBC, CMP, etc.\n"
    "- 'Leakage risk' or 'stale' or 'waiting too long' should match leakage_risk=true OR days_idle>7.\n"
    "- 'Patients with cardiac history' or 'cardiac risk' should match patient_conditions including CHD, "
    "heart disease, atrial fib, etc.\n"
    "- Keep the explanation under 2 short sentences. Name the matched patients explicitly."
)


@app.route("/api/search", methods=["POST"])
def search() -> Any:
    """Natural-language search over the pre-analyzed referral queue."""
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    if not query:
        return jsonify({"error": "Missing 'query' in request body."}), 400

    # Ensure the bulk cache is populated; if not, build it now.
    if _BULK_CACHE is None:
        # Touch the bulk endpoint behavior by computing the cache.
        global_cache_warm = _analyze_all_for_cache()
        if global_cache_warm is None:
            return jsonify({"error": "Bulk cache unavailable."}), 500

    summaries = _bulk_search_summaries()
    if not summaries:
        return jsonify({
            "query": query,
            "matching_ids": [],
            "explanation": "No referrals are loaded yet.",
            "source": "empty",
        })

    user_prompt = (
        f'Query: "{query}"\n\n'
        f"Referrals (pre-analyzed JSON):\n{json.dumps(summaries, indent=2)}\n\n"
        'Return JSON exactly matching this schema:\n'
        '{\n'
        '  "matching_ids": ["ref-001", ...],\n'
        '  "explanation": "one or two short sentences naming the matched patients and why they match"\n'
        '}'
    )

    client = get_azure_client()
    if client is not None:
        try:
            completion = client.chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": SEARCH_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=500,
            )
            raw = completion.choices[0].message.content or "{}"
            parsed = json.loads(raw)
            ids = [str(i) for i in (parsed.get("matching_ids") or []) if i]
            # Filter to only IDs that actually exist in the cache.
            valid_ids = {s["id"] for s in summaries}
            ids = [i for i in ids if i in valid_ids]
            explanation = str(parsed.get("explanation") or "").strip()
            return jsonify({
                "query": query,
                "matching_ids": ids,
                "explanation": explanation or "Match details unavailable.",
                "source": "azure_openai",
            })
        except Exception as exc:
            print(f"[search] Azure call failed: {exc}; using keyword fallback.", flush=True)

    # Keyword-based fallback.
    return jsonify(_keyword_search_fallback(query, summaries))


def _analyze_all_for_cache() -> bool | None:
    """Pre-warm the bulk cache if it has not been computed yet."""
    global _BULK_CACHE
    if _BULK_CACHE is not None:
        return True
    try:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(2, len(SAMPLE_REFERRALS))
        ) as executor:
            _BULK_CACHE = list(executor.map(_analyze_referral, SAMPLE_REFERRALS))
        return True
    except Exception as exc:
        print(f"[search] failed to warm bulk cache: {exc}", flush=True)
        return None


def _keyword_search_fallback(query: str, summaries: list[dict[str, Any]]) -> dict[str, Any]:
    q = query.lower()
    matches: list[dict[str, Any]] = []
    for s in summaries:
        haystack = " ".join(
            str(v).lower()
            for v in (
                s.get("patient"),
                s.get("specialty"),
                s.get("readiness"),
                s.get("urgency"),
                " ".join(s.get("missing_items") or []),
                " ".join(s.get("patient_conditions") or []),
            )
            if v
        )
        if any(token in haystack for token in q.split()):
            matches.append(s)
        elif "leakage" in q and s.get("leakage_risk"):
            matches.append(s)
        elif "urgent" in q and (s.get("urgency") == "High"):
            matches.append(s)
        elif "stale" in q and (s.get("days_idle") or 0) > 7:
            matches.append(s)
    names = ", ".join(m["patient"] for m in matches) or "no patients"
    return {
        "query": query,
        "matching_ids": [m["id"] for m in matches],
        "explanation": f"Keyword fallback match: {names}.",
        "source": "fallback",
    }


@app.route("/api/approvals", methods=["GET"])
def approvals() -> Any:
    """Return the in-memory approval log and current time-saved totals."""
    return jsonify({"log": APPROVAL_LOG, "stats": _approval_stats_payload()})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)
