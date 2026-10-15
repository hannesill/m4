---
name: clinical-research-session
description: Run a clinical research study with the researcher from question to results - interview, protocol, approved analysis scripts, and results on the Vitrine board. Use when the user wants to study whether an exposure or treatment affects an outcome, compare patient groups, characterise or model a cohort, write a research protocol, or continue an earlier study. Not for a single count or lookup.
tier: validated
category: system
kind: workflow
---

# Clinical Research Session

One study per research question. The researcher answers forms, approves and reads results on
the Vitrine board; you explain and discuss in the conversation. API details are in the
`vitrine-api` and `m4-api` skills.

## Steps

1. **Orient.** Run `m4 list-datasets --json`. A dataset is usable when `"prepared": true`, or
   when `data.backend` is `"bigquery"` and `"bigquery_available": true`. If none is usable,
   ask the researcher to set one up; never run `m4 download`, `m4 init` or `m4 init-derived`
   yourself. Run `vitrine studies`; to continue a study, reuse its label, read
   `study_context(label)` and its `PROTOCOL.md` and `RESULTS.md`, mark the new session with
   `section(..., study=STUDY)`, and resume at the first unfinished step.
2. **Set up.**

   ```python
   from vitrine import register_output_dir, show

   STUDY = "vasopressor-timing-sepsis-v1"         # a different approach becomes -v2
   output_dir = register_output_dir(study=STUDY)  # creates only output/
   for sub in ("scripts", "data", "plots"):
       (output_dir / sub).mkdir(exist_ok=True)
   show("# Early vasopressors in sepsis\n\nQuestion, design, key definitions.",
        title="Study description", study=STUDY)
   ```

3. **Interview.** Post one `Form` with only the questions the user's message leaves open,
   taken from [references/interview-questions.md](references/interview-questions.md), plus any
   the study needs (time windows, subgroups). Offer only usable datasets; with one, skip the
   question. For "does early vasopressor use affect mortality in sepsis?", ask for the
   mortality window, what "early" means, exclusions and the dataset. Then make each answer
   precise in the conversation: outcome definition and follow-up, time zero, exposure window
   and comparator, exclusions that could bias this design, confounders versus mediators.
   Done when every section of the protocol template has a concrete value.
4. **Protocol.** Read `clinical-research-pitfalls`; choose methods with
   `clinical-research-analysis-framework`. Write `output_dir / "PROTOCOL.md"` from
   [references/protocol-template.md](references/protocol-template.md), naming the clinical
   skill behind each concept (`sepsis-3-cohort`, `sofa-score`, `kdigo-aki-staging`, ...).

   ```python
   r = show((output_dir / "PROTOCOL.md").read_text(), title="Protocol", wait=True,
            prompt="Approve this protocol?", study=STUDY)
   ```

   Revise on `"skip"` or typed feedback (`r.message`) until `r.action == "confirm"`.
5. **Analyse** step by step with scripts (below), one `section("Cohort", study=STUDY)` per
   phase. Show the cohort flow with counts at each exclusion (`equiflow` draws it). Where the
   protocol leaves a choice open, ask with `confirm()` or `ask()`. Done when every analysis in
   the plan has a result card.
6. **Finish.** Write `RESULTS.md` (cohort flow, effect estimates with 95% CIs, limitations),
   show a summary card and a limitations card, run
   `export(str(output_dir / "report.html"), study=STUDY)`, and suggest validating on a second
   usable dataset.

## Analysis scripts

Every result the researcher sees comes from a script, so the study can be rerun and audited.
`output_dir` holds `PROTOCOL.md`, `RESULTS.md`, `scripts/NN_name.py`, `data/` and `plots/`.
Each script:

- runs alone as `python scripts/NN_name.py` from `output_dir`;
- names its dataset and reads earlier steps' outputs from `data/` instead of querying again;
- writes tables to `data/` as Parquet and figures to `plots/` (matplotlib `.png`, Plotly
  `.html`), and does not call Vitrine.

```python
"""01 - Cohort: first ICU stay of each adult patient."""
from pathlib import Path

from m4 import execute_query

DATASET = "mimic-iv-demo"
out = Path(__file__).resolve().parent.parent

cohort = execute_query("""
WITH stays AS (
  SELECT i.subject_id, i.hadm_id, i.stay_id, i.intime, a.hospital_expire_flag,
         p.anchor_age + EXTRACT(YEAR FROM i.intime) - p.anchor_year AS age,
         ROW_NUMBER() OVER (PARTITION BY i.subject_id ORDER BY i.intime) AS stay_seq
  FROM mimiciv_icu.icustays i
  JOIN mimiciv_hosp.admissions a ON a.hadm_id = i.hadm_id
  JOIN mimiciv_hosp.patients p ON p.subject_id = i.subject_id
)
SELECT subject_id, hadm_id, stay_id, intime, age, hospital_expire_flag
FROM stays
WHERE stay_seq = 1 AND age >= 18
""", dataset=DATASET)
cohort.to_parquet(out / "data" / "cohort.parquet")
print(f"{len(cohort)} patients")
```

Run a script and show its results in one process, so its figures need no reloading:

```python
import runpy

from vitrine import register_output_dir, show

output_dir = register_output_dir(study=STUDY)
g = runpy.run_path(str(output_dir / "scripts" / "01_cohort.py"))
show(g["cohort"], title="Cohort", source="scripts/01_cohort.py", study=STUDY)
```

To correct a result, edit the script and run it again.

## Rules

- Pass `study=STUDY` to every `show`, `section`, `confirm`, `ask` and `progress` call; cards
  without it land in a separate auto-named study.
- When you post a form or question, tell the researcher in the conversation what to answer.
- Forms, `confirm`, `ask` and `show(..., wait=True)` block for up to `timeout` (600 s). If your
  shell stops commands sooner, pass a shorter `timeout` or raise the shell's limit. A timed-out
  or cut-off wait loses nothing: read the stored answer with `wait_for(card_id)` or from
  `study_context(STUDY)["decisions_made"]`. `confirm()` also returns `False` on timeout, so
  where a wait may time out, use `show(..., wait=True)` and check `r.action`.
- Draw figures with matplotlib (installed with `m4-infra[research]`) or Plotly, whichever is
  installed; `show()` takes both. Give every figure a `description=`. Show distributions as
  figures (bars for categories, histograms for continuous values); keep dict cards for a few
  summary numbers. If neither library is installed (M4 without the `research` extra), show
  the distributions as tables and tell the researcher that figures need it.
- `mimiciv_derived` tables exist only for full MIMIC-IV after `m4 init-derived` (see
  `derived.materialized` in `m4 list-datasets --json`) or on BigQuery. Elsewhere, including the
  demo, compute concepts from `mimiciv_hosp` and `mimiciv_icu` following the matching clinical
  skill and its `scripts/`. In `icustay_detail`, one stay per patient needs
  `first_hosp_stay AND first_icu_stay`.
