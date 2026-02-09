---
name: m4-vitrine
description: Present analysis results to the researcher via the vitrine server. Use when showing DataFrames, charts, markdown findings, or interactive decision points during code execution.
tier: community
category: system
---

# vitrine API

The vitrine server pushes interactive visualizations to a live browser tab during code execution sessions. Agents call `show()` to render DataFrames, charts, markdown, and key-value summaries.

## When to Use This Skill

- You need to present results to the researcher during analysis
- You want interactive tables, charts, or decision points in the browser
- You're structuring a multi-step research session with visual output
- You need to block execution until the researcher reviews/approves something

## Core Principle

**Files are the primary output (reproducibility). Display is for real-time communication (understanding).**

Always save first, then show what matters:

```python
# Save (reproducibility)
cohort_df.to_csv("output/cohort.csv", index=False)
fig.write_image("output/fig1.png")

# Show (communication)
show(cohort_df, title="Cohort — Review", run_id="sepsis-v2")
show(fig, title="Figure 1", run_id="sepsis-v2")
```

## Quick Start

```python
from m4.vitrine import show, section

# DataFrame → interactive table with paging/sorting
show(df, title="Patient Demographics")

# Plotly figure → interactive chart
show(fig, title="Age Distribution")

# Matplotlib figure → rendered as image
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.hist(df["age"])
show(fig, title="Age Histogram")

# Markdown → rich text card
show("## Key Finding\nMortality is **23%** in the target cohort.", title="Result")

# Dict → formatted key-value card
show({"patients": 4238, "mortality": "23%", "median_age": 67}, title="Summary")

# Section divider
section("Phase 2: Subgroup Analysis")
```

## Full API Reference

### `show(obj, title, description, *, run_id, source, replace, position, wait, prompt, timeout, on_send)`

Push any displayable object to the browser. Auto-starts the server on first call.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `obj` | `Any` | required | Object to display (DataFrame, figure, str, dict) |
| `title` | `str \| None` | `None` | Card title shown in header |
| `description` | `str \| None` | `None` | Subtitle or context line |
| `run_id` | `str \| None` | `None` | Group cards into a named run (for filtering) |
| `source` | `str \| None` | `None` | Provenance string (e.g., table name, query) |
| `replace` | `str \| None` | `None` | Card ID to update in-place instead of appending |
| `position` | `str \| None` | `None` | `"top"` to prepend instead of append |
| `wait` | `bool` | `False` | Block until user responds in browser |
| `prompt` | `str \| None` | `None` | Question shown to user (requires `wait=True`) |
| `timeout` | `float` | `300` | Seconds to wait for response |
| `on_send` | `str \| None` | `None` | Instruction for agent when user clicks "Send to Agent" |

**Returns:** `str` (card_id) when `wait=False`, `DisplayResponse` when `wait=True`.

### `section(title, run_id=None)`

Insert a visual section divider in the display feed.

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

| Function | Description |
|----------|-------------|
| `export(path, format="html", run_id=None)` | Export run(s) as self-contained HTML or JSON. Returns output path. |

### Interaction

| Function | Description |
|----------|-------------|
| `on_event(callback)` | Register callback for UI events (`DisplayEvent` with `event_type`, `card_id`, `payload`) |
| `pending_requests()` | Poll for user-initiated "Send to Agent" requests. Returns list of `DisplayRequest`. |
| `get_selection(artifact_id)` | Load a selection DataFrame by artifact ID. Returns `DataFrame` or `None`. |

## Supported Types

| Input Type | Renders As |
|-----------|------------|
| `pd.DataFrame` | Interactive table with paging, sorting, row selection |
| `str` | Markdown card (supports full GitHub-flavored markdown) |
| `dict` | Formatted key-value card |
| Plotly `Figure` | Interactive Plotly chart |
| Matplotlib `Figure` | Static image (PNG) |
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

# response is a DisplayResponse
if response.action == "confirm":
    print("Researcher approved")
    selected = response.data()  # DataFrame of selected rows, or None
elif response.action == "skip":
    print("Researcher skipped")
elif response.action == "timeout":
    print("No response within timeout")
```

### Async: Poll for User Requests

```python
from m4.vitrine import show, pending_requests

show(results_df, title="Results", on_send="Re-run analysis with selected subset")

# Later — poll for user actions
for req in pending_requests():
    print(f"User says: {req.prompt}")
    subset = req.data()  # DataFrame of selected rows
    req.acknowledge()    # Mark as handled
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

## Research Session Pattern

Use `run_id` and `section()` to structure a multi-step analysis:

```python
from m4.vitrine import show, section

RUN = "sepsis-mortality-v1"

# Phase 1
section("Cohort Construction", run_id=RUN)
show(cohort_df, title="Sepsis Cohort (N=4238)", run_id=RUN)

# Phase 2
section("Baseline Characteristics", run_id=RUN)
show(table1_df, title="Table 1", run_id=RUN)
show(age_fig, title="Age Distribution", run_id=RUN)

# Phase 3
section("Primary Analysis", run_id=RUN)
show(regression_df, title="Logistic Regression Results", run_id=RUN)
show("## Conclusion\nDay-1 SOFA is independently associated with 30-day mortality (OR 1.12, 95% CI 1.08–1.16).", run_id=RUN)
```

## DisplayResponse Reference

Returned by `show(..., wait=True)`:

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | `"confirm"`, `"skip"`, or `"timeout"` |
| `card_id` | `str` | ID of the card |
| `message` | `str \| None` | Optional text message from the user |
| `summary` | `str` | Brief summary of selected data |
| `artifact_id` | `str \| None` | Artifact ID for selected data |
| `.data()` | `DataFrame \| None` | Load the selected rows |

## DisplayRequest Reference

Returned by `pending_requests()`:

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | `str` | Unique request ID |
| `card_id` | `str` | Originating card ID |
| `prompt` | `str` | User's message |
| `summary` | `str` | Summary of selected data |
| `artifact_id` | `str \| None` | Artifact ID for selected data |
| `instruction` | `str \| None` | The card's `on_send` instruction |
| `.data()` | `DataFrame \| None` | Load the selected rows |
| `.acknowledge()` | `None` | Mark as handled |
