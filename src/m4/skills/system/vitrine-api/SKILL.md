---
name: vitrine-api
description: Use the vitrine display API for M4 research visualization, review cards, forms, study tracking, approvals, exports, and recovery of displayed results.
tier: community
category: system
---

# Vitrine API

Vitrine is the live display and research journal used by M4 analyses. Use it to show DataFrames, plots, markdown findings, forms, and approval gates in a browser while keeping a persistent study trail.

## When to Use This Skill

- Display query or analysis results from M4 in the browser
- Collect structured researcher input with forms
- Ask for review or approval before continuing an analysis
- Organize outputs by study and export a provenance trail
- Recover a card, study context, selected rows, or a timed-out response

## Quick Start

```python
from vitrine import show, section, confirm, ask

show(df, title="Patient Demographics")
show(fig, title="Age Distribution", description="Distribution after exclusions.")
show("## Finding\nMortality was higher in the exposed group.")
show({"patients": 4238, "mortality": "23%"})
section("Outcome Analysis")

if confirm("Proceed with adjusted model?"):
    score = ask("Which severity score?", ["SOFA", "SAPS-II", "OASIS"])
```

`show()` starts the display server automatically. The CLI is available through the M4 project environment:

```bash
uv run vitrine status
uv run vitrine start
uv run vitrine restart
```

## `show()`

```python
show(obj, title=None, description=None, *, study=None, source=None,
     replace=None, position=None, wait=False, prompt=None, timeout=600,
     actions=None, controls=None)
```

Common parameters:

| Parameter | Use |
|-----------|-----|
| `obj` | DataFrame, Plotly/matplotlib figure, markdown string, dict, or `Form` |
| `title` | Card title |
| `description` | Short explanation or interpretation |
| `study` | Group cards into a named study |
| `source` | Provenance such as dataset, table, script, or SQL summary |
| `replace` | Existing card id to update in place |
| `wait=True` | Block until the researcher responds |
| `prompt` | Review question shown with `wait=True` |
| `actions` | Quick action buttons |
| `controls` | Form fields attached to the card |

Return values:
- `wait=False`: a string-like card handle with `.url`
- `wait=True`: a `DisplayResponse` with `action`, `card_id`, `message`, `summary`, and `values`

## Forms

```python
from vitrine import Form, Question, show

response = show(Form([
    Question("score", "Severity score?",
             options=[("SOFA", "Organ dysfunction"), ("SAPS-II", "Mortality prediction")]),
    Question("exclusions", "Exclusions?",
             options=["Readmissions", "Age < 18", "ICU LOS < 24h"],
             multiple=True),
]), wait=True, prompt="Confirm study parameters.", study="sepsis-v1")

score = response.values["score"]
exclusions = response.values["exclusions"]
```

Use `multiple=True` whenever several answers can be selected. Use `allow_other=True` when free-text additions are expected.

## Study Management

```python
from vitrine import (
    register_output_dir, list_studies, study_context,
    export, section, get_card, list_annotations,
)

STUDY = "early-vasopressors-sepsis-v1"
out = register_output_dir(study=STUDY)
section("Cohort Definition", study=STUDY)
context = study_context(STUDY)
export("output/study.html", format="html", study=STUDY)
```

Useful functions:

| Function | Use |
|----------|-----|
| `register_output_dir(path=None, study=None)` | Create/register artifact directory |
| `list_studies()` | List known studies |
| `study_context(study)` | Re-orient to prior cards and decisions |
| `section(title, study=None)` | Add a visual section divider |
| `export(path, format="html", study=None)` | Export HTML or JSON |
| `get_card(card_id)` | Fetch card metadata by id/prefix |
| `list_annotations(study=None)` | Read researcher annotations |

## Interaction Patterns

### Blocking Review

```python
response = show(cohort_df, title="Cohort Preview", wait=True,
                prompt="Does this cohort look correct?", timeout=300,
                study=STUDY)

if response.action == "confirm":
    selected_rows = response.data()
elif response.action in {"skip", "timeout"}:
    raise RuntimeError("Researcher did not approve the cohort.")
```

Narrate the handoff in the terminal before using `wait=True`, so the researcher knows to respond in vitrine.

### Progressive Updates

```python
card_id = show(preliminary_df, title="Cohort (preliminary)", study=STUDY)
show(final_df, title="Cohort (final)", replace=card_id, study=STUDY)
```

### Passive Selection and Recovery

```python
from vitrine import get_selection, wait_for

subset = get_selection(card_id)
response = wait_for(card_id, timeout=600)
```

## Plot Guidance

- Use plots for distributions with many categories or continuous variables.
- Always pass `description=` for plots, describing what the plot shows and why it matters.
- Save Plotly figures as JSON from scripts, then reload with `plotly.io.from_json()` before calling `show()`.

## References

- Vitrine Python package API, installed as the M4 dependency `vitrine>=0.1.0`.
