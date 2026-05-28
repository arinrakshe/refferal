import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import AzureOpenAI


load_dotenv()

APP_TITLE = "CareQueue Inbox Triage"
PORT = int(os.getenv("PORT", "8000"))
AZURE_DEPLOYMENT = (
    os.getenv("AZURE_OPENAI_DEPLOYMENT")
    or os.getenv("AZURE_OPENAI_MODEL")
    or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
    or "gpt-4o"
)

TRIAGE_SCHEMA = {
    "category": "urgent | routine | billing",
    "confidence": 0.0,
    "priority_reason": "Short reason for the route.",
    "signals": ["Specific phrases or facts from the message."],
    "missing_information": ["Facts a reviewer may need before responding."],
    "routing_note": "Short operational handoff for staff.",
    "draft_reply": "Patient-facing draft for human review.",
    "safety_note": "Why this must stay human-reviewed.",
}

SAMPLE_MESSAGES = [
    {
        "id": "urgent",
        "label": "Urgent symptoms",
        "patient": "Avery Parker",
        "message": (
            "I started a new blood pressure medicine yesterday and now I have chest tightness, "
            "shortness of breath, and feel dizzy. Should I wait for my appointment next week?"
        ),
    },
    {
        "id": "routine",
        "label": "Routine refill",
        "patient": "Jordan Lee",
        "message": (
            "Can you send a refill for my allergy nasal spray to the pharmacy on file? "
            "I have about a week left and no new symptoms."
        ),
    },
    {
        "id": "billing",
        "label": "Billing question",
        "patient": "Morgan Chen",
        "message": (
            "I received a bill for my annual visit even though my insurance usually covers it. "
            "Can someone review the claim and explain the balance?"
        ),
    },
]

CATEGORY_META = {
    "urgent": {
        "queue": "Clinical escalation",
        "sla": "Same day / immediate review",
        "color": "#b42318",
        "icon": "!",
    },
    "routine": {
        "queue": "Care team inbox",
        "sla": "1-2 business days",
        "color": "#176b53",
        "icon": "R",
    },
    "billing": {
        "queue": "Billing support",
        "sla": "2-3 business days",
        "color": "#8a5a00",
        "icon": "$",
    },
}


def make_client() -> AzureOpenAI | None:
    key = os.getenv("AZURE_OPENAI_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not key or not endpoint:
        return None
    return AzureOpenAI(
        api_key=key,
        azure_endpoint=endpoint,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )


def clean_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    return json.loads(text)


def normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    category = str(result.get("category", "routine")).lower().strip()
    if category not in CATEGORY_META:
        category = "routine"

    def listify(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if value:
            return [str(value).strip()]
        return []

    try:
        confidence = float(result.get("confidence", 0.65))
    except (TypeError, ValueError):
        confidence = 0.65

    normalized = {
        "category": category,
        "confidence": max(0.0, min(confidence, 1.0)),
        "priority_reason": str(result.get("priority_reason") or "Needs staff review.").strip(),
        "signals": listify(result.get("signals"))[:5],
        "missing_information": listify(result.get("missing_information"))[:5],
        "routing_note": str(result.get("routing_note") or CATEGORY_META[category]["queue"]).strip(),
        "draft_reply": str(result.get("draft_reply") or "").strip(),
        "safety_note": str(
            result.get("safety_note")
            or "Draft only. A human must verify route, clinical risk, and final response."
        ).strip(),
    }
    if not normalized["draft_reply"]:
        normalized["draft_reply"] = fallback_reply(category)
    return normalized


def fallback_reply(category: str) -> str:
    if category == "urgent":
        return (
            "Thank you for reaching out. Your message includes symptoms that need prompt clinical review. "
            "I am routing this to the care team now. If you feel this may be an emergency, call emergency "
            "services or go to the nearest emergency department."
        )
    if category == "billing":
        return (
            "Thank you for your message. I am routing this to billing support so they can review the claim, "
            "insurance response, and balance details. They may follow up if they need more information."
        )
    return (
        "Thank you for your message. I am routing this to the care team for review. They will confirm the "
        "details and follow up with next steps."
    )


def heuristic_triage(patient_message: str) -> dict[str, Any]:
    text = patient_message.lower()
    urgent_terms = [
        "chest pain",
        "chest tightness",
        "shortness of breath",
        "can't breathe",
        "cannot breathe",
        "dizzy",
        "faint",
        "severe",
        "bleeding",
        "suicidal",
        "stroke",
        "allergic reaction",
    ]
    billing_terms = ["bill", "billing", "claim", "insurance", "copay", "balance", "charge", "invoice"]
    routine_terms = ["refill", "appointment", "schedule", "question", "form", "lab result", "follow up"]

    urgent_hits = [term for term in urgent_terms if term in text]
    billing_hits = [term for term in billing_terms if term in text]
    routine_hits = [term for term in routine_terms if term in text]

    if urgent_hits:
        category = "urgent"
        signals = urgent_hits
        reason = "Potentially urgent symptoms or safety language detected."
    elif billing_hits:
        category = "billing"
        signals = billing_hits
        reason = "Message appears focused on insurance, claims, charges, or balances."
    else:
        category = "routine"
        signals = routine_hits or ["No urgent or billing keywords detected."]
        reason = "No urgent symptom or billing pattern detected."

    missing = []
    if category == "routine" and "refill" in text and "pharmacy" not in text:
        missing.append("Preferred pharmacy")
    if category == "billing" and "date" not in text and "visit" not in text:
        missing.append("Date of service or statement details")
    if category == "urgent":
        missing.extend(["Symptom onset and severity", "Callback number", "Current location if escalation is needed"])

    return normalize_result(
        {
            "category": category,
            "confidence": 0.74 if signals else 0.58,
            "priority_reason": reason,
            "signals": signals,
            "missing_information": missing,
            "routing_note": f"Route to {CATEGORY_META[category]['queue']} with {CATEGORY_META[category]['sla']} SLA.",
            "draft_reply": fallback_reply(category),
            "safety_note": "Keyword fallback used. Staff must verify the route and edit the draft before sending.",
        }
    )


def ai_triage(patient_name: str, patient_message: str) -> tuple[dict[str, Any], str]:
    client = make_client()
    if client is None:
        result = heuristic_triage(patient_message)
        result["model_source"] = "heuristic fallback"
        return result, "Azure OpenAI credentials were not fully configured."

    system_prompt = f"""
You are assisting a healthcare administrative inbox team with a hackathon prototype.
Classify a synthetic or de-identified patient portal message into exactly one category:
- urgent: possible emergency symptoms, serious medication reaction, safety risk, or time-sensitive clinical escalation.
- routine: scheduling, refills, forms, non-urgent care-team questions, normal follow-up.
- billing: insurance, claims, copays, charges, balances, invoices, coverage questions.

Draft a reply for human approval. Do not diagnose, determine treatment, or tell the patient the issue is safe.
For urgent messages, include escalation language that directs emergency symptoms to emergency services.
Return only valid JSON with this shape: {json.dumps(TRIAGE_SCHEMA)}.
"""
    user_prompt = f"""
Patient display name: {patient_name or "Synthetic patient"}
Message:
{patient_message}
"""
    try:
        response = client.chat.completions.create(
            model=AZURE_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        result = normalize_result(clean_json(content))
        result["model_source"] = f"Azure OpenAI deployment: {AZURE_DEPLOYMENT}"
        return result, ""
    except Exception as exc:
        result = heuristic_triage(patient_message)
        result["model_source"] = "heuristic fallback"
        return result, f"Azure OpenAI call failed, fallback used: {exc}"


def page_html() -> str:
    samples = json.dumps(SAMPLE_MESSAGES)
    meta = json.dumps(CATEGORY_META)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{APP_TITLE}</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --panel: #ffffff;
      --ink: #18212f;
      --muted: #627084;
      --line: #d9dee8;
      --accent: #0b6bcb;
      --accent-dark: #064f98;
      --urgent: #b42318;
      --routine: #176b53;
      --billing: #8a5a00;
      --shadow: 0 10px 30px rgba(22, 31, 44, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: #fff;
    }}
    .wrap {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
    }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 18px 0;
    }}
    h1 {{
      font-size: clamp(1.4rem, 2vw, 2.1rem);
      margin: 0;
      letter-spacing: 0;
    }}
    .track {{
      color: var(--muted);
      font-weight: 650;
      font-size: 0.95rem;
    }}
    main {{
      padding: 24px 0 40px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 0.9fr) minmax(360px, 1.1fr);
      gap: 18px;
      align-items: start;
    }}
    section, aside {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .panel-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 16px;
      border-bottom: 1px solid var(--line);
    }}
    h2 {{
      font-size: 1.03rem;
      margin: 0;
      letter-spacing: 0;
    }}
    .panel-body {{ padding: 16px; }}
    label {{
      display: block;
      font-weight: 700;
      margin-bottom: 7px;
      font-size: 0.92rem;
    }}
    input, textarea, select {{
      width: 100%;
      border: 1px solid #c9d1dd;
      border-radius: 6px;
      padding: 11px 12px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }}
    textarea {{
      min-height: 185px;
      resize: vertical;
      line-height: 1.45;
    }}
    .field {{ margin-bottom: 14px; }}
    .actions {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font-weight: 800;
      padding: 11px 14px;
      cursor: pointer;
      min-height: 42px;
    }}
    button:hover {{ background: var(--accent-dark); }}
    button.secondary {{
      background: #eef3f8;
      color: #213047;
      border: 1px solid #cfd8e5;
    }}
    button.secondary:hover {{ background: #e2eaf4; }}
    .small {{
      color: var(--muted);
      font-size: 0.86rem;
      line-height: 1.4;
    }}
    .sample-row {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }}
    .sample-row button {{
      min-height: 44px;
      background: #fff;
      color: #223047;
      border: 1px solid #cfd8e5;
      padding: 9px;
    }}
    .result-empty {{
      padding: 38px 20px;
      text-align: center;
      color: var(--muted);
    }}
    .badge-line {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 10px;
      border-radius: 999px;
      color: #fff;
      font-weight: 850;
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: 0.78rem;
    }}
    .badge .dot {{
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: rgba(255,255,255,0.24);
      display: inline-grid;
      place-items: center;
      font-size: 0.75rem;
    }}
    .metric-strip {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin: 16px 0;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px;
      background: #fbfcfe;
      min-height: 80px;
    }}
    .metric strong {{
      display: block;
      font-size: 0.88rem;
      margin-bottom: 6px;
    }}
    .metric span {{ color: var(--muted); font-size: 0.9rem; }}
    .result-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin: 14px 0;
    }}
    .box {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }}
    .box h3 {{
      margin: 0 0 8px;
      font-size: 0.92rem;
      letter-spacing: 0;
    }}
    ul {{
      margin: 0;
      padding-left: 19px;
      color: #2c374a;
    }}
    li {{ margin: 5px 0; }}
    .reply {{
      width: 100%;
      min-height: 170px;
      border: 1px solid #c9d1dd;
      border-radius: 8px;
      padding: 12px;
      line-height: 1.45;
      background: #fff;
      white-space: pre-wrap;
    }}
    .review {{
      display: grid;
      gap: 9px;
      margin-top: 12px;
    }}
    .check {{
      display: flex;
      align-items: flex-start;
      gap: 9px;
      font-size: 0.92rem;
      color: #334155;
    }}
    .check input {{
      width: 17px;
      height: 17px;
      margin-top: 2px;
    }}
    .alert {{
      border-left: 4px solid var(--accent);
      background: #eef6ff;
      padding: 11px 12px;
      border-radius: 6px;
      color: #17324d;
      margin-top: 12px;
      font-size: 0.9rem;
      line-height: 1.42;
    }}
    .warning {{
      border-left-color: #b42318;
      background: #fff4f2;
      color: #54211c;
    }}
    .footer-band {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-top: 18px;
    }}
    .footer-band div {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 13px;
      min-height: 108px;
    }}
    .footer-band strong {{ display: block; margin-bottom: 7px; }}
    .status {{ min-height: 20px; }}
    @media (max-width: 860px) {{
      .grid, .result-grid, .footer-band, .metric-strip {{
        grid-template-columns: 1fr;
      }}
      .sample-row {{
        grid-template-columns: 1fr;
      }}
      .topbar {{
        align-items: flex-start;
        flex-direction: column;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <div>
        <h1>{APP_TITLE}</h1>
        <div class="track">Track 3: Reduce Administrative Burden</div>
      </div>
      <div class="small">Synthetic messages only. AI drafts are never sent without staff review.</div>
    </div>
  </header>
  <main class="wrap">
    <div class="grid">
      <section>
        <div class="panel-head">
          <h2>Patient Message</h2>
          <span class="small">Demo input</span>
        </div>
        <div class="panel-body">
          <div class="sample-row" id="sampleRow"></div>
          <div class="field">
            <label for="patient">Patient display name</label>
            <input id="patient" value="Avery Parker" autocomplete="off">
          </div>
          <div class="field">
            <label for="message">Message</label>
            <textarea id="message"></textarea>
          </div>
          <div class="actions">
            <button id="triageBtn">Triage and draft</button>
            <button class="secondary" id="clearBtn">Clear</button>
            <span class="small status" id="status"></span>
          </div>
          <div class="alert">
            Data provenance: built-in synthetic inbox examples or manually entered de-identified text. Do not paste real PHI.
          </div>
        </div>
      </section>

      <aside>
        <div class="panel-head">
          <h2>Triage Output</h2>
          <span class="small" id="sourceLabel">Awaiting message</span>
        </div>
        <div class="panel-body" id="result">
          <div class="result-empty">Choose a sample or enter a message to generate a route, rationale, and draft reply.</div>
        </div>
      </aside>
    </div>

    <div class="footer-band">
      <div>
        <strong>Human Review</strong>
        <span class="small">Staff verifies category, urgency, missing information, and wording before any response is sent.</span>
      </div>
      <div>
        <strong>Success Metric</strong>
        <span class="small">Measure minutes saved per message and first-pass routing accuracy against staff-reviewed labels.</span>
      </div>
      <div>
        <strong>Known Limitation</strong>
        <span class="small">Prototype classification is assistive. It does not diagnose, determine treatment, or replace escalation protocols.</span>
      </div>
    </div>
  </main>
  <script>
    const samples = {samples};
    const categoryMeta = {meta};
    const messageEl = document.getElementById('message');
    const patientEl = document.getElementById('patient');
    const statusEl = document.getElementById('status');
    const resultEl = document.getElementById('result');
    const sourceLabel = document.getElementById('sourceLabel');

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
      }}[ch]));
    }}

    function listHtml(items) {{
      if (!items || !items.length) return '<span class="small">None flagged.</span>';
      return '<ul>' + items.map(item => `<li>${{escapeHtml(item)}}</li>`).join('') + '</ul>';
    }}

    function renderResult(data, warning) {{
      const meta = categoryMeta[data.category] || categoryMeta.routine;
      sourceLabel.textContent = data.model_source || 'AI assisted';
      const confidence = Math.round((data.confidence || 0) * 100);
      resultEl.innerHTML = `
        <div class="badge-line">
          <span class="badge" style="background:${{meta.color}}">
            <span class="dot">${{escapeHtml(meta.icon)}}</span>${{escapeHtml(data.category)}}
          </span>
          <span class="small">${{escapeHtml(data.priority_reason)}}</span>
        </div>
        <div class="metric-strip">
          <div class="metric"><strong>Queue</strong><span>${{escapeHtml(meta.queue)}}</span></div>
          <div class="metric"><strong>SLA</strong><span>${{escapeHtml(meta.sla)}}</span></div>
          <div class="metric"><strong>Confidence</strong><span>${{confidence}}%</span></div>
        </div>
        <div class="result-grid">
          <div class="box">
            <h3>Signals</h3>
            ${{listHtml(data.signals)}}
          </div>
          <div class="box">
            <h3>Missing Information</h3>
            ${{listHtml(data.missing_information)}}
          </div>
        </div>
        <div class="box">
          <h3>Routing Note</h3>
          <div class="small">${{escapeHtml(data.routing_note)}}</div>
        </div>
        <div style="height:12px"></div>
        <label>Draft reply for staff approval</label>
        <div class="reply" contenteditable="true">${{escapeHtml(data.draft_reply)}}</div>
        <div class="review">
          <label class="check"><input type="checkbox"> Confirmed the route and urgency.</label>
          <label class="check"><input type="checkbox"> Edited draft for policy, tone, and patient context.</label>
          <label class="check"><input type="checkbox"> Checked missing information before sending.</label>
        </div>
        <div class="alert warning">${{escapeHtml(data.safety_note)}}</div>
        ${{warning ? `<div class="alert">${{escapeHtml(warning)}}</div>` : ''}}
      `;
    }}

    function loadSample(sample) {{
      patientEl.value = sample.patient;
      messageEl.value = sample.message;
      resultEl.innerHTML = '<div class="result-empty">Sample loaded. Run triage to classify and draft.</div>';
      sourceLabel.textContent = 'Awaiting triage';
    }}

    document.getElementById('sampleRow').innerHTML = samples.map(sample =>
      `<button class="secondary" data-id="${{sample.id}}">${{escapeHtml(sample.label)}}</button>`
    ).join('');
    document.getElementById('sampleRow').addEventListener('click', event => {{
      const button = event.target.closest('button[data-id]');
      if (!button) return;
      loadSample(samples.find(sample => sample.id === button.dataset.id));
    }});
    loadSample(samples[0]);

    document.getElementById('clearBtn').addEventListener('click', () => {{
      patientEl.value = '';
      messageEl.value = '';
      sourceLabel.textContent = 'Awaiting message';
      resultEl.innerHTML = '<div class="result-empty">Enter a synthetic or de-identified message to begin.</div>';
    }});

    document.getElementById('triageBtn').addEventListener('click', async () => {{
      const patient = patientEl.value.trim();
      const message = messageEl.value.trim();
      if (!message) {{
        statusEl.textContent = 'Enter a message first.';
        return;
      }}
      statusEl.textContent = 'Classifying...';
      try {{
        const response = await fetch('/api/triage', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{patient, message}})
        }});
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Request failed');
        renderResult(payload.result, payload.warning);
        statusEl.textContent = 'Ready for review.';
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }});
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self.send_html(page_html())
        elif path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "azure_endpoint_configured": bool(os.getenv("AZURE_OPENAI_ENDPOINT")),
                    "azure_key_configured": bool(os.getenv("AZURE_OPENAI_KEY")),
                    "deployment": AZURE_DEPLOYMENT,
                    "samples": SAMPLE_MESSAGES,
                }
            )
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/triage":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self.send_json({"error": "Invalid JSON request."}, HTTPStatus.BAD_REQUEST)
            return

        message = str(payload.get("message", "")).strip()
        patient = str(payload.get("patient", "")).strip()
        if not message:
            self.send_json({"error": "Message is required."}, HTTPStatus.BAD_REQUEST)
            return
        if len(message) > 5000:
            self.send_json({"error": "Message is too long for this prototype."}, HTTPStatus.BAD_REQUEST)
            return

        result, warning = ai_triage(patient, message)
        self.send_json({"result": result, "warning": warning})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"{APP_TITLE} running at http://127.0.0.1:{PORT}")
    print("Use synthetic or de-identified messages only.")
    server.serve_forever()


if __name__ == "__main__":
    main()
