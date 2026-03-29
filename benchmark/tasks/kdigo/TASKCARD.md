# KDIGO AKI -- Acute Kidney Injury Staging

## What it is

KDIGO AKI staging (0-3) classifies acute kidney injury severity based on
creatinine changes, urine output rates, and renal replacement therapy (CRRT).
Defined by the 2012 KDIGO Clinical Practice Guideline. Unlike severity scores,
this is a **staging system** — it classifies the presence and degree of kidney
injury, not overall illness severity.

## The 3 staging criteria (highest applies)

| Stage | Creatinine | Urine Output | CRRT |
|-------|-----------|--------------|------|
| 1 | >= 1.5x baseline (7-day) OR >= baseline (48h) + 0.3 mg/dL | < 0.5 mL/kg/h for 6-12h | — |
| 2 | >= 2.0x baseline (7-day) | < 0.5 mL/kg/h for >= 12h | — |
| 3 | >= 3.0x baseline (7-day) OR >= 4.0 with acute rise OR initiation of RRT | < 0.3 mL/kg/h for >= 24h OR anuria for >= 12h | Any CRRT = Stage 3 |

Final stage = MAX(creatinine stage, UO stage, CRRT stage).

## Data sources in MIMIC-IV

- **Creatinine**: `kdigo_creatinine` (aggregated from `labevents`, itemid 50912)
  - 7-day lookback for baseline minimum
  - 48-hour lookback for absolute increase criterion
- **Urine Output**: `kdigo_uo` (from `urine_output` + `weight_durations`)
  - Weight-normalized rates (mL/kg/h) over 6/12/24h rolling windows
- **CRRT**: detected from charted CRRT mode in `kdigo_stages`
- **Weight**: from `weight_durations` for UO normalization

## Why 48h (not 24h)

KDIGO AKI staging uses a 48-hour assessment window by definition. The creatinine
criteria require observing changes over 48h (the 0.3 mg/dL absolute increase uses
a 48h lookback). A 24h window would miss the majority of AKI events.

## Why standard vs raw

- **Standard**: `kdigo_stages` dropped; agent has `kdigo_creatinine`, `kdigo_uo`, and
  upstream measurement tables to work with
- **Raw**: all intermediate tables dropped; agent must compute creatinine baselines,
  weight-normalized UO rates, and CRRT detection from base tables

## Subtleties to watch for

- **UO requires weight normalization** (mL/kg/h, not mL/h) — weight from `weight_durations`
- **UO not evaluated until 6h post-admission** — insufficient data before that
- **Creatinine baseline** is minimum observed in prior 7 days (not pre-admission baseline)
- **Stage 3 creatinine** has an OR condition: either 3x baseline OR (Cr >= 4.0 AND
  acute rise from 48h baseline)
- **CRRT is always Stage 3** regardless of creatinine or UO values
- The `mimiciv_derived.kdigo_stages` table is always dropped (it's the answer)
