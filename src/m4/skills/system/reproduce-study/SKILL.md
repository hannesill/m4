---
name: reproduce-study
description: Run a reproducibility audit on a vitrine study — re-executes scripts, checks determinism, and verifies claims against outputs.
tier: community
category: system
---

# Reproducibility Audit

Re-execute every script in a vitrine study, check determinism, and verify that card claims match script outputs. Produces a `REPRODUCIBILITY.md` report and a live summary card.

## When to Use This Skill

- User asks to verify or reproduce a study
- User wants to check if scripts are deterministic
- User wants to audit whether vitrine cards reflect actual outputs
- Before publishing or sharing a study

## Setup

```python
from m4.vitrine import study_context, register_output_dir, show
import pandas as pd
from pathlib import Path

STUDY = "<study-label>"  # provided as context when dispatched
output_dir = register_output_dir(study=STUDY)
```

## Procedure

### Step 1: Orient

Call `study_context(STUDY)` and read the result. Note:
- `card_count` — total cards in the study
- `cards` — list of card dicts, each with `card_id`, `title`, `type`, `preview`
- `decisions_made` — decisions and their outcomes

Read `PROTOCOL.md` and `RESULTS.md` from `output_dir` if they exist — these contain claims to verify.

### Step 2: Inventory Scripts

List all `.py` files in `output_dir / "scripts/"`. Sort by filename (they should be numbered: `01_cohort_definition.py`, `02_baseline.py`, etc.).

If there are no scripts, post a single card explaining that the study has no scripts to audit and stop.

### Step 3: Create Progress Card

Post an initial progress card and capture the card ID for progressive updates:

```python
progress = "| Script | Status | Deterministic | Output Matches |\n"
progress += "|--------|--------|---------------|----------------|\n"
for script in scripts:
    progress += f"| `{script.name}` | pending | -- | -- |\n"

card_id = show(progress, title="Reproducibility Audit", study=STUDY)
```

### Step 4: Execute Each Script

For each script in order:

1. **Run 1** — Execute the script via the Bash tool: `python scripts/NN_name.py` from the output directory. Capture stdout/stderr and exit code. Record output files produced in `data/` and `plots/` (snapshot filenames and file hashes).

2. **Run 2** — Execute the same script a second time. Capture the same information.

3. **Check determinism** — Compare output file hashes between Run 1 and Run 2. If all hashes match, the script is deterministic. If any differ, flag it.

4. **Check claims** — Look through the study's cards for any card whose title or content references this script's outputs (e.g., a card titled "Cohort" that shows a DataFrame likely came from `01_cohort_definition.py`). Compare:
   - Row counts: does the card's row count match the output parquet's row count?
   - Key values: do summary statistics or counts mentioned in markdown cards match the actual outputs?
   - If the card is a table, load the parquet and compare shape and column names.
   - If you cannot link any card to a script's output, mark as "unverifiable".

5. **Update progress card** — After each script completes, update the card in-place:

```python
# Build updated table with results so far
progress = "| Script | Status | Deterministic | Output Matches |\n"
progress += "|--------|--------|---------------|----------------|\n"
for entry in results:
    progress += f"| `{entry['script']}` | {entry['status']} | {entry['deterministic']} | {entry['matches']} |\n"
# Remaining scripts still pending
for script in remaining:
    progress += f"| `{script.name}` | pending | -- | -- |\n"

show(progress, title="Reproducibility Audit", replace=card_id, study=STUDY)
```

### Step 5: Write REPRODUCIBILITY.md

Save a full report to `output_dir / "REPRODUCIBILITY.md"` with:

```markdown
# Reproducibility Report

**Study:** <study-label>
**Date:** <ISO date>
**Scripts audited:** N

## Summary

| Script | Status | Deterministic | Output Matches |
|--------|--------|---------------|----------------|
| `01_cohort_definition.py` | pass | yes | yes |
| `02_baseline.py` | pass | yes | unverifiable |
| ... | ... | ... | ... |

## Verdict

X/Y scripts pass, Z/Y deterministic, W/Y claims verified, V unverifiable.

## Details

### 01_cohort_definition.py
- **Status:** pass
- **Deterministic:** yes — output hashes identical across runs
- **Output matches:** yes — cohort.parquet has 4238 rows, card "Cohort" shows 4238 rows
- **Outputs:** data/cohort.parquet (sha256: abc123...)

### 02_baseline.py
...

## Non-Deterministic Scripts

[List any scripts that produced different outputs across runs, with details on what differed.]

## Unverifiable Claims

[List any cards whose claims could not be traced back to a script output.]

## Failures

[List any scripts that failed to execute, with error messages.]
```

### Step 6: Final Card Update

Update the progress card one last time with the verdict line appended:

```python
verdict = f"\n**Verdict:** {pass_count}/{total} scripts pass, {det_count}/{total} deterministic, {match_count}/{total} claims verified, {unverifiable_count} unverifiable."

show(progress + verdict, title="Reproducibility Audit", replace=card_id, study=STUDY)
```

## Critical Implementation Notes

1. **Always run from the output directory.** Scripts use `Path(__file__).resolve().parent.parent` to find `data/` and `plots/`, so the working directory must be `output_dir`.

2. **Hash comparison for determinism.** Use SHA-256 hashes of output files, not content comparison. For parquet files, hash the file bytes. Some non-determinism is acceptable in floating-point edge cases — note it but don't fail the script.

3. **Claim matching is best-effort.** Not every card will map cleanly to a script. Use title keywords, output filenames, and row counts as heuristics. Mark anything ambiguous as "unverifiable" rather than guessing.

4. **Do not modify scripts.** This is an audit — run scripts as-is. If a script fails, record the failure and move on. (You are working in a sandbox copy; the original study files are safe.)

5. **Use `study=STUDY` on every `show()` call.** This keeps audit cards grouped with the study being audited.

6. **Progressive updates use `replace=card_id`.** The first `show()` returns a `DisplayHandle` (string-like card ID). Pass it as `replace=` to update the same card.
