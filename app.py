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

import json
import os
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import AzureOpenAI


load_dotenv()

AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_KEY = os.getenv("AZURE_OPENAI_KEY")
PORT = int(os.getenv("PORT", "8000"))


SAMPLE_REFERRALS: list[dict[str, Any]] = [
    {
        "id": "ref-001",
        "patient": "Avery Parker",
        "referring_provider": "Dr. Kim — Northbridge Primary Care (NPI 1234567890)",
        "specialty_requested": "Orthopedics",
        "reason": (
            "Persistent right knee pain for 8 weeks. Conservative treatment "
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
        "patient_dob": "1979-08-14",
        "diagnosis_code": "M25.561",
        "urgency_stated": "Routine",
        "label": "Complete & ready to schedule",
    },
    {
        "id": "ref-002",
        "patient": "Jordan Lee",
        "referring_provider": "Dr. Patel — Lakeside Family Medicine",
        "specialty_requested": "Cardiology",
        "reason": "Chest discomfort.",
        "attachments": [],
        "insurance": "",
        "patient_phone": "555-0199",
        "patient_dob": "1962-02-03",
        "diagnosis_code": "",
        "urgency_stated": "",
        "label": "Missing imaging & insurance",
    },
    {
        "id": "ref-003",
        "patient": "Riley Brooks",
        "referring_provider": "Dr. Davis — Westside Internal Medicine (NPI 9876543210)",
        "specialty_requested": "Neurology",
        "reason": (
            "New-onset severe headaches with intermittent vision changes over the "
            "past 5 days. No prior history. Requesting urgent neurology evaluation."
        ),
        "attachments": [
            "MRI brain report (2026-05-26)",
            "Lab panel (CBC, CMP)",
        ],
        "insurance": "United Healthcare PPO — Member ID 4567890",
        "patient_phone": "555-0167",
        "patient_dob": "1988-11-22",
        "diagnosis_code": "G43.909",
        "urgency_stated": "Urgent",
        "label": "Urgent & complete",
    },
    {
        "id": "ref-004",
        "patient": "Morgan Chen",
        "referring_provider": "Dr. Singh — Riverbend Family Health (NPI 1122334455)",
        "specialty_requested": "Gastroenterology",
        "reason": (
            "Suspected IBS. Referral for evaluation and management. Initial labs "
            "reviewed, recommend GI workup."
        ),
        "attachments": [
            "Lab panel (CBC, CMP, TSH)",
            "Symptom diary (2 weeks)",
        ],
        "insurance": "Aetna HMO — Member ID 5566778899",
        "patient_phone": "",
        "patient_dob": "1991-04-17",
        "diagnosis_code": "K58.9",
        "urgency_stated": "Routine",
        "label": "Missing patient contact",
    },
    {
        "id": "ref-005",
        "patient": "Sam Rivera",
        "referring_provider": "Dr. Lin — Harborview Family Medicine (NPI 9988776655)",
        "specialty_requested": "Endocrinology",
        "reason": (
            "Recent hemoglobin A1c trending upward over the past 6 months. "
            "Requesting endocrinology evaluation for diabetes management."
        ),
        "attachments": [],
        "insurance": "Cigna PPO — Member ID 2233445566",
        "patient_phone": "555-0124",
        "patient_dob": "1975-09-30",
        "diagnosis_code": "E11.65",
        "urgency_stated": "Routine",
        "label": "Routine, missing labs",
    },
]


SYSTEM_PROMPT = (
    "You are a referral intake AI assistant for a US healthcare clinic. "
    "You analyze incoming patient referrals to determine whether they are "
    "schedule-ready. You never make clinical decisions and you never decide "
    "treatment. You only assess the completeness of the referral packet, flag "
    "what is missing, and draft outreach emails when items are missing. Your "
    "output is always reviewed by a human referral coordinator before any "
    "action is taken."
)

USER_PROMPT_TEMPLATE = """Analyze this referral packet and return JSON matching this exact schema:

{
  "readiness": "Ready" | "Missing Info" | "Needs Review",
  "confidence": integer 0-100,
  "present_items": ["specific items present in the packet"],
  "missing_items": ["specific items missing or vague"],
  "urgency": "High" | "Medium" | "Low",
  "next_action": "one short sentence describing the coordinator's next step",
  "draft_email": "full polite outreach email to the referring office requesting missing items, or empty string if nothing is missing",
  "safety_note": "one sentence explaining why human review is still required"
}

Rules:
- Use "Ready" only when everything needed to schedule is present (clear reason, diagnosis, insurance, patient contact, relevant attachments).
- Use "Missing Info" when one or more non-urgent items are missing but the referral is fixable with a quick outreach.
- Use "Needs Review" when urgency is high OR critical items (e.g. diagnosis and reason both vague) are missing.
- "urgency" reflects what the referral states or strongly implies. Do NOT make a clinical determination.
- Never invent information. If a field is empty or missing, treat it as missing.
- The draft email must be addressed to the referring provider's office, polite, and specific about what is being requested.

Referral packet (JSON):
"""


def get_azure_client() -> AzureOpenAI | None:
    if not AZURE_ENDPOINT or not AZURE_KEY:
        return None
    try:
        return AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_KEY,
            api_version=AZURE_API_VERSION,
        )
    except Exception:
        return None


def call_azure(referral: dict[str, Any]) -> dict[str, Any] | None:
    client = get_azure_client()
    if client is None:
        return None
    try:
        completion = client.chat.completions.create(
            model=AZURE_DEPLOYMENT,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE + json.dumps(referral, indent=2),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=900,
        )
        raw = completion.choices[0].message.content or ""
        return json.loads(raw)
    except Exception:
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


def fallback_analysis(referral: dict[str, Any]) -> dict[str, Any]:
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
            missing_items.append(label)
        else:
            present_items.append(label)

    attachments = referral.get("attachments") or []
    if isinstance(attachments, list) and len(attachments) > 0:
        present_items.append("Supporting attachments")
    else:
        missing_items.append("Supporting attachments (imaging, labs, or notes)")

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

    return {
        "readiness": readiness,
        "confidence": 70,
        "present_items": present_items,
        "missing_items": missing_items,
        "urgency": urgency,
        "next_action": next_action,
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

    azure_raw = call_azure(referral)
    if azure_raw is not None:
        analysis = normalize_result(azure_raw, source="azure_openai")
    else:
        analysis = normalize_result(fallback_analysis(referral), source="fallback")

    return jsonify({"referral": referral, "analysis": analysis})


@app.route("/api/approve", methods=["POST"])
def approve() -> Any:
    """Demo-only endpoint. Logs an approval event. Does NOT send anything."""
    payload = request.get_json(silent=True) or {}
    referral_id = payload.get("referral_id", "unknown")
    action = payload.get("action", "approve")
    print(f"[APPROVE] referral_id={referral_id} action={action}")
    return jsonify({"ok": True, "logged": True, "referral_id": referral_id, "action": action})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)
