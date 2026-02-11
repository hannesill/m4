---
name: vitrine-api
description: The agent's research journal and live display. Documents decisions, findings, and rationale as persistent cards; collects structured researcher input; creates an exportable provenance trail across research studies.
tier: community
category: system
---

# Vitrine API Reference

Full API reference for the vitrine display system. For usage philosophy and quick reference, see the Vitrine section in CLAUDE.md.

## When to Use This Skill

- You need the full API signature for a vitrine function
- You're using advanced features (events, selections, hybrid controls, progressive updates)
- You need the `DisplayResponse` field reference

## Quick Start

```python
from m4.vitrine import show, section, confirm, ask, set_status

show(df, title="Patient Demographics")           # table
show(fig, title="Age Distribution")               # Plotly or matplotlib chart
show("## Finding\nMortality is **23%**.")         # markdown
show({"patients": 4238, "mortality": "23%"})      # key-value
section("Phase 2: Analysis")                       # divider
set_status("Running regression...")                # status bar
if confirm("Proceed?"): ...                        # yes/no → bool
score = ask("Which score?", ["SOFA", "APACHE"])   # choice → str
```

## `show()`

```python
show(obj, title=None, description=None, *, study=None, source=None,
     replace=None, position=None, wait=False, prompt=None, timeout=300,
     actions=None, controls=None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `obj` | `Any` | required | DataFrame, Plotly/matplotlib figure, str (markdown), dict, Form |
| `title` | `str \| None` | `None` | Card title |
| `description` | `str \| None` | `None` | Subtitle (e.g., "N=4238 after exclusions") |
| `study` | `str \| None` | `None` | Group into named study |
| `source` | `str \| None` | `None` | Provenance — table name, query, dataset. Shown as card footer. |
| `replace` | `str \| None` | `None` | Card ID to update in-place |
| `position` | `str \| None` | `None` | `"top"` to prepend |
| `wait` | `bool` | `False` | Block until user responds |
| `prompt` | `str \| None` | `None` | Question shown to user (requires `wait=True`) |
| `timeout` | `float` | `300` | Seconds to wait |
| `actions` | `list[str] \| None` | `None` | Quick-action buttons (e.g., `["SOFA", "APACHE III"]`) |
| `controls` | `list[FormField] \| None` | `None` | Form controls attached to data cards |

**Returns:** `DisplayHandle` (string-like card id + `.url`) when `wait=False`, `DisplayResponse` when `wait=True`.

## Other Functions

### `section(title, study=None)`
Visual section divider.

### `confirm(message, *, study=None, timeout=600) → bool`
Yes/no gate. Returns `True` if confirmed, `False` if skipped or timed out.

### `ask(question, options, *, study=None, timeout=600) → str`
Multiple-choice. Returns the chosen label or `"timeout"`.

### `set_status(message)`
Agent status bar in browser header. Ephemeral — not persisted.

### `start(port=7741, open_browser=True, mode="thread")`
Start server explicitly. Called automatically on first `show()`. `mode="process"` for daemon.

### `stop()` / `stop_server()`
Stop in-process server / stop daemon server. Study data persists on disk.

### `server_status()`
Info dict about running server, or `None`.

## Study Management

| Function | Description |
|----------|-------------|
| `register_output_dir(path=None, study=None)` | Register output directory for file artifacts. Returns `Path`. |
| `study_context(study)` | Structured summary for re-orientation: `card_count`, `cards`, `decisions_made`, `pending_responses` |
| `list_studies()` | List all studies with metadata |
| `delete_study(study)` | Delete a study by label |
| `clean_studies(older_than="7d")` | Remove old studies (e.g., `"7d"`, `"24h"`, `"0d"` for all). Returns count. |
| `get_card(card_id)` | Look up card by ID, prefix, or slug-suffixed reference (e.g., `a1b2c3-my-title`) |
| `list_annotations(study=None)` | Researcher annotations, newest first. Each: `{id, text, timestamp, card_id, card_title}` |
| `register_session(study=None)` | Associate session ID with study. Auto-called on first `show()`. |
| `wait_for(card_id)` | Re-attach to a timed-out blocking card — checks stored response first, else waits again |

## Export

```python
from m4.vitrine import export

export("output/study.html", format="html", study="sepsis-v1")  # shareable HTML
export("output/study.json", format="json", study="sepsis-v1")  # JSON archive
```

## Supported Types

| Input | Renders As |
|-------|------------|
| `pd.DataFrame` | Interactive table with paging, sorting, row selection |
| `str` | Markdown card (GitHub-flavored) |
| `dict` | Key-value card |
| Plotly `Figure` | Interactive chart |
| Matplotlib `Figure` | Static SVG image |
| `Form` | Structured input card (freezes on confirm) |
| Other | `repr()` fallback |

## Form Controls

```python
from m4.vitrine import Form, Question

Question(
    name="field_name",           # key in response.values
    question="Question text?",
    options=[                    # plain strings or (label, description) tuples
        ("Label", "Description"),
        "Plain option",
    ],
    header="Chip",               # optional short tag
    multiple=False,              # True for multi-select (checkboxes), False for single-select (radio)
    allow_other=True,            # "Other: ___" free-text option
    default="Label",             # pre-selected (str or list[str])
)
```

### Standalone Form

```python
response = show(Form([
    Question("score", "Severity score?",
             options=[("SOFA", "6 organ systems"), ("APACHE III", "Mortality prediction")]),
    Question("excl", "Exclusions?",
             options=["Readmissions", "Age<18"], multiple=True),
]), wait=True, study=RUN)

response.values["score"]   # "SOFA"
response.values["excl"]    # ["Readmissions"]
```

### Hybrid Data + Controls

Attach form controls to a table or chart card:

```python
response = show(cohort_df, title="Cohort Preview",
    controls=[Question("icu", "ICU type?", options=["All", "MICU", "SICU"])],
    wait=True, prompt="Review and confirm.", study=RUN)

response.values["icu"]  # "MICU"
```

## Interaction Patterns

### Blocking with Data Review

```python
response = show(cohort_df, title="Cohort", wait=True,
    prompt="Does this look correct?", timeout=300)

if response.action == "confirm":
    selected = response.data()  # DataFrame of selected rows, or None
elif response.action == "skip":
    ...
elif response.action == "timeout":
    ...
```

### Quick Actions

```python
response = show("Which severity score?", title="Choice", wait=True,
    actions=["SOFA", "APACHE III", "Both"])
# response.action matches the button label exactly
```

### Progressive Updates

```python
card_id = show(preliminary_df, title="Cohort (preliminary)")
# ... more processing ...
show(refined_df, title="Cohort (final)", replace=card_id)
```

### Passive Selections

```python
from m4.vitrine import get_selection

card_id = show(results_df, title="Results")
subset_df = get_selection(card_id)  # current browser selection
```

### Events

```python
from m4.vitrine import on_event

def handle(event):
    if event.event_type == "row_click":
        print(f"Clicked {event.payload['row']['subject_id']}")

on_event(handle)
```

## DisplayResponse Reference

Returned by `show(..., wait=True)`:

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | `"confirm"`, `"skip"`, `"timeout"`, or named action |
| `card_id` | `str` | Card ID |
| `message` | `str \| None` | Optional text from user |
| `summary` | `str` | Brief summary of selected data |
| `values` | `dict` | Form field values (empty if no form) |
| `artifact_id` | `str \| None` | Artifact ID for selected data |
| `.data()` | `DataFrame \| None` | Load selected rows |

## Browser Features

- **Card dismiss/hide:** Eye icon soft-hides cards (provenance preserved, still in exports)
- **Annotations:** Researchers add notes to any card — persist with card, appear in `study_context()`
- **Copy-prompt:** Clipboard button copies contextual card reference for AI client follow-ups
- **Study launcher:** "New session" / "Resume" buttons copy `claude -p` / `claude --resume` commands
