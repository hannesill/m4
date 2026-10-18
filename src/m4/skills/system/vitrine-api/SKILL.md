---
name: vitrine-api
description: Publish results to the researcher's Vitrine board as cards (tables, figures, images and galleries, notes, forms, approvals) and read back what is on it (cards, decisions, form answers, annotations). Use when showing results, asking the researcher to choose or approve, or when they mention a card, a table, the board, or a study.
tier: community
category: system
kind: integration
---

# Vitrine

Vitrine shows results as cards on a board the researcher reads beside the conversation. Cards
belong to a study, stored in the `.vitrine` folder of the project.

## Rules for every script

- **One study.** Set `STUDY = "short-label"` once and pass `study=STUDY` to every call that takes
  it. Cards without a label go to an `auto-<time>` study per process. To continue earlier work,
  reuse a label from `vitrine studies`.
- **Run from the project folder.** Cards go to the nearest `.vitrine` above the working directory,
  or to `VITRINE_DATA_DIR`. A script run from a temporary folder publishes where nobody looks.
- **Let the server run.** `show()` starts it, and the researcher's board points at it; stopping or
  restarting it breaks their view. With `VITRINE_OPEN_BROWSER=0` a host app shows the board: point
  the researcher to the board, not to a URL.
- Run `vitrine` and `python` from the environment M4 is installed in.

## Read the board

When the researcher mentions a card, a table, or the board, look before answering.

```python
import vitrine

vitrine.list_studies()             # label, dir_name, card_count; CLI: vitrine studies
ctx = vitrine.study_context(STUDY) # cards (card_id, card_type, title, annotations),
                                   # decisions_made, pending_responses
card = vitrine.get_card("a1b2c3")  # preview, response_action/values/message, annotations
vitrine.get_selection("a1b2c3")    # rows or points the researcher selected
```

A reference copied from the board, `[card:a1b2c3, study:sepsis-v1]`, names the card. A table's
`preview` holds 20 rows; the whole table is
`<data_dir>/studies/<dir_name>/artifacts/<artifact_id>.parquet` (`data_dir` from
`vitrine status --json`).

## Publish

```python
from vitrine import progress, section, show

STUDY = "sepsis-v1"
section("Cohort", study=STUDY)
handle = show(cohort_df, title="Cohort", source="mimiciv_icu.icustays; scripts/01_cohort.py", study=STUDY)
show(fig, title="Age at admission", description="Included stays by decade of age.", study=STUDY)
show("28-day mortality was **23%** (412 of 1,790).", title="Primary outcome", study=STUDY)
show(final_df, title="Cohort", replace=handle, study=STUDY)  # update that card in place

with progress("Fitting the model", study=STUDY) as step:      # completes, or fails with the block
    step("fold 2 of 5")
```

`show()` takes a DataFrame (a paged, searchable table), a Plotly or matplotlib figure, a markdown
string, a dict (a key-value list), a `Form`, or images (next section). Give every card a `title` and a `source`, and every figure a `description` of what it shows.
Tables are redacted by default: columns named like identifiers (name, address, city, zip,
phone, email, ssn, mrn, dob) show `[REDACTED]`, and rows past 10,000 are dropped, which the card
states. `VITRINE_REDACT=0` turns both off; `VITRINE_MAX_ROWS` moves the cap.

## Images

```python
from pathlib import Path
from vitrine import Picture, Question, show

# PNG, JPEG, WebP, GIF, SVG
show(Path("figures/flow.svg"), title="Cohort flow", source="scripts/01_cohort.py", study=STUDY)
# PIL image or NumPy array
show(pil_image_or_array, title="Case 3", source="mimic-cxr-jpg; scripts/03_view.py", study=STUDY)
pictures = [
    Picture(path, caption=f"case {i}", labels={"Effusion (model)": 0.82, "Radiologist": "no effusion"},
            overlay={"Left lung": left_mask, "Right lung": right_mask})   # or a mask, heatmap, RGBA
    for i, (path, left_mask, right_mask) in enumerate(rows, start=1)
]
# A list makes a gallery
show(pictures, title="Largest disagreements", source="mimic-cxr-jpg; scripts/04_review.py", study=STUDY)
show("## Result\n\n![ROC curve](figures/roc.png)", title="Result", source="scripts/05_roc.py", study=STUDY)
```

- A file needs `Path(...)`: a plain string is markdown. Markdown cards copy the local images they
  embed (`![alt](path)` or `<img src="path" width="300">`, read from the working directory) into
  the card.
- The researcher opens a picture in a viewer (zoom, pan, arrow keys, overlays on and off). Labels
  show beside each picture; a 16-bit or float array is scaled to 8 bits for display.
- Captions such as `case 3`, never patient identifiers: captions and labels are what an agent
  reads back. DICOM is not read; convert it to an array first.
- Never open or view images from credentialed datasets yourself: what you read goes to your model
  provider. Put them on the board for the researcher instead.

## Ask the researcher

```python
from vitrine import Form, Question, ask, confirm, show

if confirm("Exclude stays under 24 hours?", study=STUDY):              # False on skip or timeout
    ...
score = ask("Which severity score?", ["SOFA", "SAPS-II"], study=STUDY) # typed text, else the option,
                                                                       # "skip", or "timeout"
r = show(Form([
    Question("outcome", "Primary outcome?", options=["28-day mortality", "ICU length of stay"]),
    Question("exclusions", "Exclusions?", options=["Readmissions", "Age < 18"], multiple=True),
]), title="Study parameters", study=STUDY)
r.values["outcome"], r.values["exclusions"]
```

- Questions take free text too unless `allow_other=False`; options can be `(label, description)`.
- `show(obj, wait=True, prompt="Does this cohort look right?", study=STUDY)` puts a question on any
  card and returns a `DisplayResponse`: `action` (`"confirm"`, `"skip"`, `"timeout"`, or a label
  from `actions=[...]`), `message`, `values`, and `data()` for rows the researcher selected.
- `controls=[Question(...)]` attaches a question to a table, chart, or gallery. A question whose
  options are a gallery's captions is answered by clicking the pictures. A single choice among
  seven or more options shows as a dropdown.
- `wait=False` on a form or `controls=` asks without blocking; read the answer later from
  `get_card(card_id).response_values` or `study_context(STUDY)["decisions_made"]`. Use it for
  reviews the researcher may take a while over.
- Before a question, say in the conversation what to answer on the board.
- Questions and forms block up to `timeout=600` seconds, longer than many agent shells wait. Run
  the script with a longer shell timeout. If the wait was cut short, the answer is still stored:
  `wait_for(card_id)` returns it, or waits again; open questions are in
  `study_context(STUDY)["pending_responses"]`.

## Files and export

- `register_output_dir(study=STUDY)` returns the study's `output/` folder for files it produces.
- `export("report.html", study=STUDY)` writes the study with its provenance; `format="json"`
  for JSON. CLI: `vitrine export report.html --study STUDY`.
