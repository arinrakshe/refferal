# Referral Ready

**AI intake agent that turns incoming specialist referrals into schedule-ready packets — with a human approving every step.**

> 🏆 Built during the **Athenahealth AI for Healthcare Hackathon during #BostonTechWeek** — Track 3: *Reduce Administrative Burden*.
> Won First Place - 🏆 Trusted Innovation Award — sponsored by Snowflake

---

## The problem

Referral coordinators manually review **every** incoming specialist referral to answer three questions:

1. Is it complete enough to schedule?
2. If not, what's missing?
3. How urgent is it?

It's slow, repetitive work — and referrals that stall in this queue become patients who never get scheduled.

## What Referral Ready does

For each incoming referral, the agent:

- 🟢 **Flags readiness** — `Ready`, `Missing Info`, or `Needs Review`
- 🔍 **Identifies what's missing** — and explains *why each gap matters* for this patient and specialty (e.g. *"Recent A1c is missing; endocrinology needs current diabetes control data"*)
- ✉️ **Drafts a follow-up email** to the referring office requesting the missing items (only when something's actually missing)
- ⏱️ **Assesses urgency** — `High` / `Medium` / `Low`, based only on what the referral states or strongly implies
- 🧭 **Suggests routing** and a concrete next action for the coordinator

…and **nothing is sent until a human reviews and approves it.** The AI never makes a clinical decision and never acts on its own.

## Responsible-AI guardrails

These rules are baked into the prompt and the workflow:

- **Human-in-the-loop** — every result must be explicitly approved before any action is taken.
- **No clinical decisions** — the agent assesses *administrative completeness and stated urgency*, not medical judgment.
- **No invented facts** — empty fields are reported as missing, never filled in.
- **No real patient data** — the demo runs entirely on synthetic [Synthea](https://github.com/synthetichealth/synthea) records.
- **Graceful fallback** — if Azure OpenAI is unreachable, a deterministic keyword analyzer takes over so the demo never goes dark.

---

## How it works

```
Incoming referral ──► Patient chart lookup (Synthea) ──► GPT-4o analysis ──► Coordinator review & approval
                                                              │
                                                   (keyword fallback if Azure is down)
```

1. A referral packet (reason, specialty, attachments, insurance, contact, etc.) arrives.
2. The app pulls the matching synthetic patient history (conditions, meds, encounters).
3. **Azure OpenAI GPT-4o** analyzes the referral *with and without* the chart and returns structured JSON: readiness, confidence, missing items, present items, urgency, draft email, routing, and a safety note.
4. The coordinator sees every result and approves before anything goes out.

### Tech stack

| Layer | Tech |
|-------|------|
| Backend | Python + Flask, served by gunicorn |
| AI | Azure OpenAI (GPT-4o) with a deterministic keyword fallback |
| Frontend | Vanilla HTML / CSS / JavaScript |
| Data | Synthea synthetic patient records (CSV) |
| Deploy | Docker + `Procfile` (gunicorn) |

---

## Getting started

### Prerequisites
- Python 3.13+
- (Optional) Azure OpenAI endpoint + key. Without them the app automatically uses the keyword fallback.

### Run locally

```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) configure Azure OpenAI
cp .env.example .env   # then fill in your values

# 4. Run
python app.py          # dev server
# or, production-style:
gunicorn app:app --bind 0.0.0.0:8000

# 5. Open http://127.0.0.1:8000
```

### Configuration

All credentials are read from environment variables (see `.env.example`) — **none are committed to the repo.**

| Variable | Purpose | Default |
|----------|---------|---------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | — (falls back to keyword mode if unset) |
| `AZURE_OPENAI_KEY` | Azure OpenAI API key | — |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name | `gpt-5.4-mini` |
| `AZURE_OPENAI_API_VERSION` | API version | `2024-10-21` |
| `PORT` | Port to serve on | `8000` |

---

## API

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/api/referrals` | List the sample referral packets |
| `GET` | `/api/triage-all` | Analyze all sample referrals |
| `GET` | `/api/patients/<id>` | Synthetic patient history |
| `POST` | `/api/triage` | Analyze a single referral |
| `POST` | `/api/search` | Search synthetic patients |
| `POST` | `/api/approve` | Record a human approval |
| `GET` | `/api/approvals` | List recorded approvals |

## Demo data — 5 sample referrals

Each is hand-picked to exercise a different edge case:

| Specialty | Scenario |
|-----------|----------|
| Orthopedics | Complete packet → **Ready** |
| Cardiology | Sparse referral → **Needs Review** |
| Neurology | Urgent & complete → high-priority |
| Gastroenterology | Missing patient contact → **Missing Info** |
| Endocrinology | Missing labs → **Missing Info** |

---

## Project structure

```
app.py              # Flask backend: referrals, triage, fallback, approvals
templates/          # index.html (UI)
static/             # app.js, styles.css
synthea/            # synthetic patient data (CSV)
patients.csv        # hand-authored fallback dataset
requirements.txt    # Python dependencies
Dockerfile          # container build
Procfile            # gunicorn process for PaaS hosts
```

## Limitations & future work

- Demo uses a fixed set of synthetic referrals; a real deployment would ingest from an intake queue / fax / fax-to-text.
- Time-saved figures are illustrative estimates, not measured.
- Approvals are stored in-memory for the demo.

---

*No real patient data is used anywhere in this project. The AI assists with administrative triage only — a human reviews and approves every action.*
