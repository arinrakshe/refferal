# Data And Security

## Safe Data Choices

Use:

- Synthetic records.
- De-identified sample data.
- FHIR-like examples.
- Synthea data.
- Synthetic claims-style data.
- Public terminology references such as LOINC or RxNorm/RxNav.
- Mock provider/catalog references.

Do not use:

- Real PHI.
- Customer names or identifiers.
- Production logs with sensitive values.
- Private screenshots.
- Real credentials.

## Safe AI Design

Every project should include at least one visible safety mechanism:

- Human approval before action.
- Source citation or data provenance.
- Missing-information warning.
- Confidence or uncertainty note.
- Audit trail.
- Output review checklist.
- Clear limitation message.

## Secret Handling

- Do not commit `.env` files.
- Do not paste keys into Codex or ChatGPT.
- Do not show credentials during demos.
- Use local environment variables if needed.
- If a secret is exposed, tell a TA immediately.

## Clinical Safety

Do not present your prototype as making medical decisions.

Safer language:

- "Assists review."
- "Drafts for human approval."
- "Flags possible missing information."
- "Summarizes synthetic context."
- "Suggests next questions."

Unsafe language:

- "Diagnoses."
- "Determines treatment."
- "Automatically approves."
- "Replaces clinician judgment."
