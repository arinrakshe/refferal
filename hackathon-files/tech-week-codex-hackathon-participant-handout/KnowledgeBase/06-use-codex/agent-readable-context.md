# Agent-Readable Hackathon Context

This file is for Codex or another agent helping a participant team.

```yaml
event:
  name: "Tech Week Codex Hackathon"
  date: "2026-05-28"
  timezone: "America/New_York"
  start_time: "09:30"
  demo_start_time: "15:30"
  end_time: "17:00"
  goal: "Build practical AI prototypes that improve a meaningful healthcare workflow."
demo:
  demo_minutes: 3
  qna_minutes: 2
tracks:
  - "Improve Patient Experience"
  - "Improve Encounter Experience"
  - "Reduce Administrative Burden"
  - "Improve Data Liquidity, Trust, and Transparency"
rules:
  data_allowed:
    - "synthetic data"
    - "de-identified data"
  prohibited:
    - "real PHI"
    - "customer-identifiable data"
    - "secrets"
    - "API keys"
    - "passwords"
    - "autonomous clinical decision-making"
  required:
    - "human review for high-risk recommendations"
    - "AI usage disclosure"
    - "trust/safety/transparency mechanism"
    - "success metric"
    - "known limitations"
judging:
  total_points: 30
  criteria:
    - name: "Business Innovation"
      points: 10
    - name: "Technical Innovation"
      points: 10
    - name: "Trust, Safety, and Transparency"
      points: 10
submission_required_fields:
  - "team name"
  - "participant names"
  - "track"
  - "project title"
  - "problem statement"
  - "solution summary"
  - "repo/artifact/demo link"
  - "setup or inspection instructions"
  - "data inputs"
  - "AI usage"
  - "trust/safety/transparency mechanism"
  - "success metric"
  - "known limitations"
dataset_links:
  - name: "Synthea synthetic patients"
    url: "https://github.com/synthetichealth/synthea"
  - name: "Synthea FHIR output"
    url: "https://github.com/synthetichealth/synthea"
  - name: "Medscheduler"
    url: "https://pypi.org/project/medscheduler/"
  - name: "CMS Blue Button 2.0 Sandbox"
    url: "https://sandbox.bluebutton.cms.gov/"
  - name: "CDC PLACES"
    url: "https://www.cdc.gov/places/"
  - name: "Census ACS"
    url: "https://www.census.gov/programs-surveys/acs/data.html"
  - name: "BeTraC 2026"
    url: "https://huggingface.co/datasets/BeTraC/betrac-2026"
  - name: "LOINC"
    url: "https://loinc.org/get-started/getting-loinc/"
  - name: "RxNorm/RxNav APIs"
    url: "https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html"
  - name: "RxNorm/RxNav"
    url: "https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html"
  - name: "CMS Medicare Claims Synthetic Public Use Files"
    url: "https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-claims-synthetic-public-use-files"
  - name: "CMS BCDA sample files"
    url: "https://bcda.cms.gov/bcda-data.html"
  - name: "HL7 Da Vinci PAS"
    url: "https://hl7.org/fhir/us/davinci-pas/"
  - name: "HL7 Da Vinci CRD"
    url: "https://hl7.org/fhir/us/davinci-crd/"
  - name: "HL7 Da Vinci DTR"
    url: "https://hl7.org/fhir/us/davinci-dtr/"
  - name: "NPPES NPI files"
    url: "https://www.cms.gov/medicare/regulations-guidance/administrative-simplification/data-dissemination"
  - name: "CMS Provider Data Catalog"
    url: "https://data.cms.gov/provider-data/"
  - name: "X12 external code lists"
    url: "https://x12.org/codes"
  - name: "HL7 FHIR R4"
    url: "https://hl7.org/fhir/R4/"
  - name: "PMC Open Access Subset"
    url: "https://pmc.ncbi.nlm.nih.gov/tools/openftlist/"
agent_behavior:
  optimize_for:
    - "demo by 15:30 EDT"
    - "small working prototype"
    - "safe sample data"
    - "clear README"
    - "3-minute demo script"
  ask_human_when:
    - "real credential is needed"
    - "data may contain PHI"
    - "clinical claim is uncertain"
    - "official submission/access detail is missing"
```

## Agent Instruction

Help the team ship a safe, narrow, demoable prototype. Do not invent official event details. Do not ask for secrets or PHI. If a live service is blocked, help the team create a mock or backup demo.
