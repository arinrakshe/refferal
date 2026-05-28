# Using Codex During The Hackathon

Codex can help you scope, build, debug, document, and rehearse. It should not be given secrets or PHI.

## First Prompt

```text
We are participating in the Tech Week Codex Hackathon. Read this participant handout. Help us build a one-day prototype for the [track] track. Follow the rules: synthetic or de-identified data only, no real PHI, no secrets, no autonomous clinical decision-maker, include human review, disclose AI usage, include a trust/safety/transparency mechanism, and prepare a 3-minute demo plus 2-minute Q&A.
```

## Good Codex Tasks

- Turn an idea into a one-day MVP.
- Generate synthetic sample data.
- Scaffold a small app, script, notebook, or CLI.
- Write setup instructions.
- Debug errors.
- Write tests where useful.
- Draft the README.
- Draft the final submission.
- Review the project against the rubric.
- Write the 3-minute demo script.

## Do Not Give Codex

- Real PHI.
- Customer data.
- API keys.
- Passwords.
- Personal access tokens.
- Private logs.
- Screenshots with secrets.

## Useful Prompts

Scope:

```text
Help us reduce this idea to a one-day MVP. Return the user, problem, demo path, non-goals, data needed, AI step, guardrail, and success metric.
```

Rubric review:

```text
Review our project against the 30-point rubric. Give likely strengths, missing required fields, safety concerns, and the highest-value fixes we can make in 30 minutes.
```

Demo:

```text
Write a 3-minute demo script and 2-minute Q&A prep list. Include user, pain point, before/after workflow, data inputs, AI usage, guardrail, limitations, and success metric.
```

Safety check:

```text
Check our repo and README for hackathon safety issues: PHI, secrets, unsupported clinical claims, missing human review, unclear data source, missing limitations, or third-party attribution gaps.
```
