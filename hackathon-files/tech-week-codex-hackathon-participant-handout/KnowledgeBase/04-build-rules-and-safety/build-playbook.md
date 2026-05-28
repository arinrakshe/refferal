# Build Playbook

## Build The Demo First

Write this before you build:

```text
Our user is:
Their problem is:
Our prototype helps by:
The data is:
AI does:
The human reviews:
The success metric is:
```

## Recommended Build Flow

| Time | Focus |
|---|---|
| 10:30-11:00 | MVP, data, architecture, demo story |
| 11:00-12:00 | Core path |
| 12:00-12:30 | First rough demo |
| 13:00-14:15 | Finish implementation |
| 14:15-15:00 | README, submission, safety explanation |
| 15:00-15:30 | Rehearse and prepare backup |

## Simple Architecture

```text
Safe sample data -> deterministic processing -> AI step -> human review -> output/demo
```

## Good AI Tasks

- Summarize.
- Extract.
- Classify.
- Draft.
- Compare.
- Explain.
- Flag missing information.
- Generate checklist.

## Keep It Narrow

When time gets tight:

- Drop extra screens.
- Drop extra personas.
- Drop live deployment.
- Use mock API responses.
- Show one strong example.
- Write down future work instead of building it.

## Final Build Checklist

- [ ] Demo path works.
- [ ] Backup screenshot or saved output exists.
- [ ] README explains setup or inspection.
- [ ] Data is synthetic or de-identified.
- [ ] AI usage is clear.
- [ ] Human review or guardrail is visible.
- [ ] Success metric is named.
- [ ] Limitations are listed.
- [ ] No secrets are exposed.
