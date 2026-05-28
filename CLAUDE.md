# Referral Ready — Hackathon Project

## Project
AI intake agent for healthcare referrals. Track 3 - Reduce Administrative Burden. Athenahealth Tech Week Hackathon.

## Stack
- Python Flask
- Azure OpenAI GPT-4o
- HTML/CSS frontend

## Azure Credentials
- Endpoint and key are in .env as AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY
- Deployment name: [ASK TA AND PUT IT HERE]

## What We're Building
1. Show 5 fake referral packets
2. AI analyzes each one and returns readiness score, missing items, draft email
3. Human approval checklist before any action
4. Keyword fallback if Azure is unreachable

## Rules
- No real patient data
- Human always approves before anything is sent
- AI never makes clinical decisions