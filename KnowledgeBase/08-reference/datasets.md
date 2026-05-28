# Dataset Guide

These are the dataset and reference links extracted from `AI Hackathon Structure.docx`.

Use only synthetic, de-identified, public, or organizer-approved subsets. If a source requires an account, license click, large download, or usage review, ask a TA before relying on it for the demo.

## Quick Selection By Track

| Track | Best Starting Points |
|---|---|
| Improve Patient Experience | Synthea, Medscheduler, CMS Blue Button 2.0 Sandbox, CDC PLACES, Census ACS |
| Improve Encounter Experience | Synthea, BeTraC 2026, LOINC, RxNorm/RxNav |
| Reduce Administrative Burden | CMS synthetic claims, BCDA samples, Da Vinci PAS/CRD/DTR, NPPES, CMS Provider Data Catalog, X12 codes |
| Improve Data Liquidity, Trust, and Transparency | HL7 FHIR R4, Synthea FHIR output, BCDA samples, LOINC, RxNorm/RxNav, PMC Open Access, CDC PLACES, Census ACS |

## Linked Datasets And References

| Resource | Link | Best For | Participant Notes |
|---|---|---|---|
| Synthea synthetic patients | https://github.com/synthetichealth/synthea | Patient timelines, chart prep, care journeys, encounters, medications, care plans | Good default synthetic patient source. Can produce FHIR/CSV-style records. |
| Synthea FHIR output | https://github.com/synthetichealth/synthea | FHIR-shaped synthetic patient records | Use with HL7 FHIR R4 for FHIR-to-action workflows and care journey demos. |
| Medscheduler | https://pypi.org/project/medscheduler/ | Appointment slots, no-shows, cancellations, wait times, scheduling prototypes | Useful for scheduling, referrals, and navigation demos. |
| CMS Blue Button 2.0 Sandbox | https://sandbox.bluebutton.cms.gov/ | Synthetic Medicare claims/EOB-style data | Good for cost, coverage, and care-history summaries. |
| CDC PLACES | https://www.cdc.gov/places/ | Community-level health context | Use aggregate context; do not confuse population-level context with patient facts. |
| Census ACS | https://www.census.gov/programs-surveys/acs/data.html | Community demographic context | Use for aggregate context and transparency demos. |
| BeTraC 2026 | https://huggingface.co/datasets/BeTraC/betrac-2026 | Synthetic doctor-patient transcripts/audio and SOAP-style outputs | Useful for visit summaries, follow-up extraction, transcript-to-note prototypes. |
| LOINC | https://loinc.org/get-started/getting-loinc/ | Lab and observation terminology | Use a curated subset for demos; helps label observations and explain missing/abnormal results. |
| RxNorm/RxNav APIs | https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html | Medication normalization | Useful for med-list cleanup, follow-up instructions, and safer chart summaries. |
| RxNorm/RxNav | https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html | Medication terminology and API reference | Use to explain matched medications, missing medication context, and confidence limits. |
| CMS Medicare Claims Synthetic Public Use Files | https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-claims-synthetic-public-use-files | Synthetic claims analysis | Good for denial patterns, workqueue prioritization, revenue-cycle summaries, and dashboards. |
| CMS BCDA sample files | https://bcda.cms.gov/bcda-data.html | FHIR-style claims, coverage, patient, and ExplanationOfBenefit examples | Useful for claims ingestion, eligibility context, and transparent workflow insights. |
| HL7 Da Vinci PAS | https://hl7.org/fhir/us/davinci-pas/ | Prior authorization workflow reference | Use as workflow guidance; do not try to implement the full standard in one day. |
| HL7 Da Vinci CRD | https://hl7.org/fhir/us/davinci-crd/ | Coverage requirements discovery reference | Useful for prior-auth and coverage workflow framing. |
| HL7 Da Vinci DTR | https://hl7.org/fhir/us/davinci-dtr/ | Documentation templates and rules reference | Useful for documentation-gap prototypes. |
| NPPES NPI files | https://www.cms.gov/medicare/regulations-guidance/administrative-simplification/data-dissemination | Provider identifiers and metadata | Trim real provider contact fields if not needed for the demo. |
| CMS Provider Data Catalog | https://data.cms.gov/provider-data/ | Provider specialties, locations, and public profile data | Useful for routing, referrals, and documentation-gap prototypes. |
| X12 external code lists | https://x12.org/codes | Denial/remittance concepts | Safer path: use a small mock CARC/RARC-style denial set rather than redistributing full lists. |
| HL7 FHIR R4 | https://hl7.org/fhir/R4/ | Common healthcare resource shapes | Good reference for FHIR-to-action workflows and data-liquid prototypes. |
| PMC Open Access Subset | https://pmc.ncbi.nlm.nih.gov/tools/openftlist/ | Optional evidence/retrieval demos | Use only article-level licenses that permit the intended use, and show citations. |

## Suggested Safe Starter Data Shapes

The structure document also recommends using curated, small, allowed subsets so teams do not burn hackathon time on accounts, API keys, licenses, or large data cleanup.

Suggested starter shapes:

- Patient demographics and visit history.
- Encounter notes or visit transcripts.
- Appointment and scheduling data.
- Inbox or patient message samples.
- Referral workflows.
- Prior authorization request examples.
- Claims or denial reason samples.
- Medication, lab, and follow-up task examples.
- Structured FHIR-like resources.

## Attribution Checklist

For any dataset or reference you use, record:

- Resource name.
- URL.
- Version or access date, if known.
- License or usage note.
- Whether the data is synthetic, de-identified, public, or aggregate.
- Any caveat judges should know.
