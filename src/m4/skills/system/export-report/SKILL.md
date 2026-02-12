---
name: export-report
description: Compile a structured research report from a vitrine study — gathers cards, decisions, annotations, and scripts into an organized REPORT.md.
tier: community
category: system
---

# Export Research Report

Compile all artifacts from a vitrine study — cards, decisions, annotations, scripts, protocol, and results — into a single structured `REPORT.md`.

## When to Use This Skill

- User asks to export, compile, or summarize a study
- User wants a readable report from a completed research session
- User wants to share findings with collaborators who don't have vitrine access
- Before archiving or publishing study results

## Setup

```python
from m4.vitrine import study_context, register_output_dir, show, list_annotations
import pandas as pd
from pathlib import Path

STUDY = "<study-label>"  # provided as context when dispatched
output_dir = register_output_dir(study=STUDY)
```

## Procedure

### Step 1: Gather Context

Call `study_context(STUDY)` and capture:
- `cards` — all cards with `card_id`, `title`, `type`, `preview`
- `decisions_made` — all decisions with outcomes
- `pending_responses` — any unresolved blocking cards

Call `list_annotations(study=STUDY)` to get researcher notes. Each annotation has `id`, `text`, `timestamp`, `card_id`, `card_title`.

### Step 2: Read Existing Artifacts

Read these files from `output_dir` if they exist:
- `PROTOCOL.md` — study protocol (research question, design, analysis plan)
- `RESULTS.md` — study results and conclusions

List all `.py` files in `output_dir / "scripts/"`. For each script, read the file to extract its docstring (first triple-quoted string) as the script description. If no docstring, use the filename.

### Step 3: Categorize Cards

Group cards by type and role:

- **Study description**: The first markdown card (usually titled "Study Description") or content from `PROTOCOL.md`
- **Data cards**: Cards with type TABLE — these are results tables
- **Plot cards**: Cards with type PLOTLY or IMAGE — these are figures
- **Decision cards**: Cards with type DECISION — these are researcher choices
- **Finding cards**: Other markdown cards — these describe methods, findings, limitations

### Step 4: Compile REPORT.md

Build the report with these sections:

```markdown
# Research Report: <Study Title>

**Study:** <study-label>
**Generated:** <ISO date>
**Cards:** N | **Scripts:** N | **Decisions:** N

---

## 1. Study Description

[Content from the first markdown card or PROTOCOL.md. Include the research
question, study design, population, variables, and analysis plan.]

## 2. Methods

### Scripts

| # | Script | Description |
|---|--------|-------------|
| 1 | `01_cohort_definition.py` | Define sepsis cohort from MIMIC-IV |
| 2 | `02_baseline_characteristics.py` | Compute baseline demographics |
| ... | ... | ... |

### Protocol

[Full content of PROTOCOL.md if it exists, or a note that no protocol was saved.]

## 3. Results

### Key Findings

[Summarize finding cards — markdown cards that describe results, effect sizes,
confidence intervals, and interpretations.]

### Tables

[For each TABLE card, include the card title, description, row/column count,
and a preview of the first few rows formatted as a markdown table. Include the
source field if present.]

### Figures

[For each PLOTLY or IMAGE card, note the card title and description. Since
markdown cannot embed interactive plots, describe what each figure shows and
reference the plot file in `plots/` if available.]

## 4. Decisions Log

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Severity score? | SOFA | Standard for Sepsis-3 studies |
| 2 | Exclude readmissions? | Yes | One observation per patient |
| ... | ... | ... | ... |

[For each decision card, extract the question asked, the choice made (from
response action or form values), and any message the researcher provided as
rationale. Include timestamps.]

## 5. Scripts

[For each script, include the full source code in a fenced code block with
the filename as heading. This makes the report fully self-contained.]

### 01_cohort_definition.py

​```python
<full script content>
​```

### 02_baseline_characteristics.py

​```python
<full script content>
​```

## 6. Annotations

| Card | Annotation | Timestamp |
|------|------------|-----------|
| Cohort Preview | "Looks good, but check age range" | 2026-02-10T14:30:00 |
| ... | ... | ... |

[Include all researcher annotations. If there are none, note that no
annotations were recorded.]

---

*Report compiled from vitrine study `<study-label>`.*
```

### Step 5: Save REPORT.md

Write the compiled report to `output_dir / "REPORT.md"`.

### Step 6: Post Confirmation Card

Post a single card confirming completion with a brief table of contents:

```python
toc = f"""## Report Exported

`REPORT.md` saved to study output directory.

**Contents:**
1. Study Description
2. Methods ({script_count} scripts)
3. Results ({table_count} tables, {plot_count} figures)
4. Decisions Log ({decision_count} decisions)
5. Scripts (full source)
6. Annotations ({annotation_count} notes)

**Total cards processed:** {card_count}
"""

show(toc, title="Report Exported", study=STUDY)
```

## Critical Implementation Notes

1. **Read every script file.** The report includes full script source so it is self-contained and reproducible without access to the original output directory.

2. **Decision extraction.** Decision cards store responses differently depending on whether they used forms or quick actions. Check both `response_action` and `form_values` in the card data. The `study_context()` return includes `decisions_made` which has already-resolved decisions.

3. **Table previews.** For TABLE cards, the `preview` field in the card dict contains inline data. Format it as a markdown table, limiting to 10 rows max. If the preview is truncated, note the total row count.

4. **Plot descriptions.** Interactive Plotly figures cannot be embedded in markdown. Instead, describe what the figure shows using its `title` and `description` fields. Reference the corresponding PNG file in `plots/` if one exists.

5. **Annotation ordering.** `list_annotations()` returns newest first. Reverse the order in the report so annotations read chronologically.

6. **Missing artifacts are normal.** Not every study will have a `PROTOCOL.md`, `RESULTS.md`, annotations, or decisions. Handle each gracefully with a note like "No protocol was saved for this study."

7. **Use `study=STUDY` on every `show()` call.** This keeps the confirmation card grouped with the study.
