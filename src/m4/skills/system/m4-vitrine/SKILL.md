---
name: m4-vitrine
description: The agent's research journal and live display. Documents decisions, findings, and rationale as persistent cards; collects structured researcher input; creates an exportable provenance trail across research runs.
tier: community
category: system
---

# vitrine API

Vitrine is the agent's research journal and live display. Every `show()` call adds a card to a persistent, browsable record of the research process. The researcher can open the browser at any time to see where the analysis stands, review past decisions, and understand the agent's reasoning. Runs persist on disk, survive restarts, and export as self-contained HTML.

## When to Use This Skill

- You're documenting a decision, finding, or rationale the researcher should see
- You need to present results for review (tables, charts, summaries)
- You need structured input from the researcher (forms, quick actions, approval)
- You're structuring a multi-step research session with a clear provenance trail
- You want to export a research run as a shareable document

## Core Principles

**The research journal records what happened and why. Files record what was produced.**

```python
# File (reproducibility — the artifact)
cohort_df.to_csv("output/cohort.csv", index=False)

# Journal (understanding — the story)
show(cohort_df, title="Sepsis Cohort",
     description="N=4238 after excluding readmissions and age < 18",
     source="mimiciv_derived.icustay_detail", run_id="sepsis-v2")
```

**Document as you go.** Don't just show data — show decisions, rationale, and transitions. The journal should read like a research narrative:

```python
section("Cohort Construction", run_id=RUN)
show("## Inclusion Criteria\n- Adult patients (≥18)\n- First ICU stay only\n- Suspected infection within ±48h of ICU admission", run_id=RUN)
show(cohort_df, title="Cohort (N=4238)", run_id=RUN)

show("## Exclusion Decision\nRemoving 312 patients with ICU stay < 24h — insufficient observation window for SOFA trending.", run_id=RUN)
```

**Show what matters, not everything.** Routine intermediate DataFrames, debugging output, and exhaustive tables belong in files only.

## Quick Start

```python
from m4.vitrine import show, section, set_status

# DataFrame → interactive table with paging/sorting
show(df, title="Patient Demographics")

# Plotly figure → interactive chart
show(fig, title="Age Distribution")

# Matplotlib figure → rendered as image
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.hist(df["age"])
show(fig, title="Age Histogram")

# Markdown → rich text card (document reasoning)
show("## Key Finding\nMortality is **23%** in the target cohort.", title="Result")

# Dict → formatted key-value card
show({"patients": 4238, "mortality": "23%", "median_age": 67}, title="Summary")

# Section divider
section("Phase 2: Subgroup Analysis")

# Agent status bar
set_status("Running logistic regression...")
```

## Agent Usage Patterns

- **Document decisions as you make them.** Every exclusion criterion, parameter choice, or methodology decision should be a card. The journal should explain *why*, not just *what*.
- **Use `show()` instead of `print()`** for DataFrames and charts — the browser handles rendering, keeping terminal output minimal.
- **Batch related outputs, then block.** Show several cards, then use a single `wait=True` card for the decision point.
- **Use `set_status()` during long operations** so the researcher knows the agent is working ("Querying 4.2M rows...", "Running bootstrap...").
- **Attach provenance with `source=`** when showing query results — it records where data came from.
- **Use `run_id` consistently** within a research session. Name runs after the research question ("sepsis-mortality-v1").
- **Call `run_context(run_id)` at the start of each phase** to re-orient after long waits or turn boundaries.
- **Export at the end** of a research run — `export("output/session.html", run_id=RUN)` creates a shareable record.

## Full API Reference

### `show(obj, title, description, *, run_id, source, replace, position, wait, prompt, timeout, actions, controls)`

Push any displayable object to the browser. Auto-starts the server on first call.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `obj` | `Any` | required | Object to display (DataFrame, figure, str, dict, Form) |
| `title` | `str \| None` | `None` | Card title shown in header |
| `description` | `str \| None` | `None` | Subtitle or context line (e.g., "N=4238 after exclusions") |
| `run_id` | `str \| None` | `None` | Group cards into a named run |
| `source` | `str \| None` | `None` | Provenance string (e.g., table name, query, dataset) |
| `replace` | `str \| None` | `None` | Card ID to update in-place instead of appending |
| `position` | `str \| None` | `None` | `"top"` to prepend instead of append |
| `wait` | `bool` | `False` | Block until user responds in browser |
| `prompt` | `str \| None` | `None` | Question shown to user (requires `wait=True`) |
| `timeout` | `float` | `300` | Seconds to wait for response |
| `actions` | `list[str] \| None` | `None` | Named quick-action buttons (e.g., `["SOFA", "APACHE III", "Both"]`) |
| `controls` | `list[FormField] \| None` | `None` | Form controls attached to data cards (hybrid data+controls) |

**Returns:** `DisplayHandle` (string-like card id + `.url`) when `wait=False`, `DisplayResponse` when `wait=True`.

### `section(title, run_id=None)`

Insert a visual section divider in the display feed.

### `set_status(message)`

Set the agent status bar in the browser header. Ephemeral — not persisted. Use to communicate long-running operations:

```python
set_status("Querying 4.2M rows...")
df = execute_query(sql)
set_status("Building regression model...")
# Status auto-clears when a decision card is pushed
```

### `start(port=7741, open_browser=True, mode="thread")`

Start the display server explicitly. Called automatically on first `show()`. Use to customize port or disable browser opening.

- `mode="thread"` — in-process server (default)
- `mode="process"` — separate daemon process

### `stop()`

Stop the in-process display server and event polling.

### `stop_server()`

Stop a running persistent (process-mode) display server via HTTP. Run data persists on disk. Returns `True` if a server was stopped.

### `server_status()`

Return info dict about a running persistent server, or `None`.

### Run Management

| Function | Description |
|----------|-------------|
| `list_runs()` | List all runs with metadata and card counts |
| `delete_run(run_id)` | Delete a run by label. Returns `True` if found. |
| `clean_runs(older_than="7d")` | Remove runs older than age string (e.g., `"7d"`, `"24h"`, `"0d"` for all). Returns count removed. |

### Export

```python
from m4.vitrine import export

# Self-contained HTML — shareable, opens in any browser
export("output/sepsis-study.html", format="html", run_id="sepsis-v1")

# JSON archive — cards + raw artifacts (Parquet, chart specs)
export("output/sepsis-study.json", format="json", run_id="sepsis-v1")
```

### Interaction

| Function | Description |
|----------|-------------|
| `on_event(callback)` | Register callback for UI events (`DisplayEvent` with `event_type`, `card_id`, `payload`) |
| `get_selection(card_id)` | Read current table/chart selection state for a card. Returns selected rows as `DataFrame`. |
| `run_context(run_id)` | Structured run summary for agent re-orientation (cards, decisions, selections, pending responses). |

## Supported Types

| Input Type | Renders As |
|-----------|------------|
| `pd.DataFrame` | Interactive table with paging, sorting, row selection |
| `str` | Markdown card (supports full GitHub-flavored markdown) |
| `dict` | Formatted key-value card |
| Plotly `Figure` | Interactive Plotly chart |
| Matplotlib `Figure` | Static image (SVG) |
| `Form` | Structured input card (freezes on confirm) |
| Other | `repr()` fallback as markdown code block |

## Interaction Patterns

### Blocking: Wait for Researcher Review

```python
from m4.vitrine import show

response = show(
    cohort_df,
    title="Cohort for Review",
    wait=True,
    prompt="Does this cohort look correct? Select rows to exclude if needed.",
    timeout=300,
)

if response.action == "confirm":
    selected = response.data()  # DataFrame of selected rows, or None
elif response.action == "skip":
    print("Researcher skipped")
elif response.action == "timeout":
    print("No response within timeout")
```

### Quick Actions: Structured Choices

```python
response = show(
    "SOFA is standard for Sepsis-3. APACHE III offers mortality prediction.\nWhich severity score should we use?",
    title="Severity Score Selection",
    wait=True,
    actions=["SOFA", "APACHE III", "Both"],
    run_id=RUN,
)

# response.action matches the button label exactly
if response.action == "SOFA":
    compute_sofa(cohort_df)
elif response.action == "APACHE III":
    compute_apache(cohort_df)
elif response.action == "Both":
    compute_sofa(cohort_df)
    compute_apache(cohort_df)
```

### Form Controls: Structured Input

```python
from m4.vitrine import show, Form, Dropdown, Slider, RangeSlider, Checkbox, RadioGroup, NumberInput

# Standalone form — collect parameters before analysis
response = show(
    Form([
        Dropdown("score", ["SOFA", "APACHE III", "SAPS-II"], label="Severity Score"),
        RangeSlider("age_range", (18, 100), label="Age Range", default=(18, 90)),
        RadioGroup("outcome", ["30-day mortality", "In-hospital mortality", "ICU mortality"],
                   label="Primary Outcome"),
        Checkbox("exclude_readmissions", label="Exclude readmissions", default=True),
        NumberInput("min_los", label="Minimum ICU stay (hours)", default=24, min=0, max=720),
    ]),
    title="Analysis Parameters",
    wait=True,
    run_id=RUN,
)

score = response.values["score"]                # "SOFA"
age_lo, age_hi = response.values["age_range"]   # (18, 90)
outcome = response.values["outcome"]            # "30-day mortality"
```

All 10 form field types:

| Field | Constructor | Value Type |
|-------|-------------|------------|
| `Dropdown` | `(name, options, label, default)` | `str` |
| `MultiSelect` | `(name, options, label, default)` | `list[str]` |
| `Slider` | `(name, range, label, default, step)` | `number` |
| `RangeSlider` | `(name, range, label, default, step)` | `(number, number)` |
| `Checkbox` | `(name, label, default)` | `bool` |
| `Toggle` | `(name, label, default)` | `bool` |
| `RadioGroup` | `(name, options, label, default)` | `str` |
| `TextInput` | `(name, label, default, placeholder)` | `str` |
| `DateRange` | `(name, label, default)` | `(str, str)` |
| `NumberInput` | `(name, label, default, min, max, step)` | `number` |

### Hybrid Data + Controls

Attach form controls to a table or chart card:

```python
# Table with filter controls — researcher sees data AND adjusts parameters
response = show(
    cohort_df,
    title="Cohort Preview",
    controls=[
        Slider("sofa_threshold", (0, 24), label="Min SOFA", default=2),
        Dropdown("icu_type", ["All", "MICU", "SICU", "CCU"], label="ICU Type"),
    ],
    wait=True,
    prompt="Adjust filters and confirm to proceed.",
    run_id=RUN,
)

threshold = response.values["sofa_threshold"]
icu_type = response.values["icu_type"]
```

### Progressive Updates: Replace Cards In-Place

```python
# Show initial results, then update as analysis refines
card_id = show(preliminary_df, title="Cohort (preliminary)")

# ... more processing ...

show(refined_df, title="Cohort (final, N=4238)", replace=card_id)
```

### Pull: Read Passive Selections

```python
from m4.vitrine import show, get_selection

card_id = show(results_df, title="Results")

# Later — read current browser selection at any point
subset_df = get_selection(card_id)
if not subset_df.empty:
    print(f"Selected rows: {len(subset_df)}")
```

### Events: React to UI Interactions

```python
from m4.vitrine import show, on_event

def handle(event):
    if event.event_type == "row_click":
        row = event.payload["row"]
        print(f"Clicked patient {row['subject_id']}")

on_event(handle)
show(df, title="Click a patient")
```

### Re-orient Each Phase with `run_context()`

```python
from m4.vitrine import run_context

ctx = run_context("sepsis-mortality-v1")
print("Cards:", ctx["card_count"])
print("Pending:", len(ctx["pending_responses"]))
print("Decisions made:", len(ctx["decisions_made"]))
```

## Provenance

Attach provenance to every data card so the journal records where results came from:

```python
show(df, title="ICU Stays",
     source="mimiciv_derived.icustay_detail", run_id=RUN)

show(df, title="Query Results",
     source="SELECT * FROM mimiciv_hosp.patients WHERE ...", run_id=RUN)
```

Provenance appears as a card footer and is included in exports. Use `description=` for context that helps the researcher understand what they're looking at:

```python
show(df, title="Final Cohort",
     description="After applying all exclusion criteria (readmissions, age < 18, ICU stay < 24h)",
     source="mimiciv_derived.icustay_detail",
     run_id=RUN)
```

## Research Session Pattern

Use `run_id`, `section()`, and narrative cards to create a self-documenting research journal:

```python
from m4.vitrine import show, section, set_status, export

RUN = "sepsis-mortality-v1"

# Phase 1: Document the research question
section("Research Question", run_id=RUN)
show("## Objective\nInvestigate the association between day-1 SOFA score "
     "and 30-day mortality in adult sepsis patients.", run_id=RUN)

# Phase 2: Cohort construction with documented decisions
section("Cohort Construction", run_id=RUN)
set_status("Querying MIMIC-IV...")
show(inclusion_df, title="Inclusion Criteria Applied",
     description="Adult first ICU stays with suspected infection",
     source="mimiciv_derived.icustay_detail", run_id=RUN)

show("## Exclusion Decision\nRemoving 312 patients with ICU stay < 24h "
     "— insufficient window for SOFA trending.", run_id=RUN)

response = show(final_cohort_df,
     title=f"Final Cohort (N={len(final_cohort_df)})",
     wait=True, prompt="Approve cohort before proceeding?", run_id=RUN)

# Phase 3: Analysis
section("Primary Analysis", run_id=RUN)
show(regression_df, title="Logistic Regression",
     source="statsmodels GLM", run_id=RUN)
show(or_fig, title="Forest Plot — Adjusted ORs", run_id=RUN)

# Phase 4: Conclusion
section("Conclusion", run_id=RUN)
show("## Finding\nDay-1 SOFA is independently associated with 30-day mortality "
     "(OR 1.12, 95% CI 1.08–1.16, p<0.001).\n\n"
     "**Clinical implication:** SOFA ≥ 6 on day 1 identifies patients "
     "at substantially elevated risk.", run_id=RUN)

# Export the complete journal
export("output/sepsis-mortality-v1.html", run_id=RUN)
```

## DisplayResponse Reference

Returned by `show(..., wait=True)`:

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | `"confirm"`, `"skip"`, `"timeout"`, or a named quick action (e.g. `"SOFA"`) |
| `card_id` | `str` | ID of the card |
| `message` | `str \| None` | Optional text message from the user |
| `summary` | `str` | Brief summary of selected data |
| `values` | `dict` | Form field values (empty dict if no form controls) |
| `artifact_id` | `str \| None` | Artifact ID for selected data |
| `.data()` | `DataFrame \| None` | Load the selected rows |
