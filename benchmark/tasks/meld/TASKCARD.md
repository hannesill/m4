# MELD -- Model for End-Stage Liver Disease

## What it is

MELD is a continuous severity score (6-40) for liver disease using logarithmic
transformations of creatinine, bilirubin, and INR with a conditional sodium
adjustment (MELD-Na). Originally developed for TIPS procedure prognostication,
now the primary organ allocation criterion for liver transplantation in the US.

## Formula

1. **Component scores** (values floored at 1.0):
   - Creatinine: `0.957 × ln(max(Cr, 1))` — capped at Cr=4 if RRT or Cr > 4
   - Bilirubin: `0.378 × ln(max(Bili, 1))`
   - INR: `1.120 × ln(max(INR, 1)) + 0.643`

2. **MELD Initial**: `round(sum, 1) × 10` — capped at 40

3. **Sodium adjustment** (only if MELD Initial > 11):
   - Na score: `137 - max(min(Na, 137), 125)`
   - `MELD = MELD_Initial + 1.32 × Na_score - 0.033 × MELD_Initial × Na_score`

## Data sources in MIMIC-IV

- **Creatinine, Bilirubin, INR, Sodium**: `first_day_lab`
- **RRT/Dialysis**: `first_day_rrt` (dialysis_present flag)
- Missing values → components default to ln(1) = 0

## Why standard vs raw

- **Standard**: `meld` dropped; agent has `first_day_lab` and `first_day_rrt`
- **Raw**: MELD and task-relevant lab/RRT intermediates are dropped; agent must
  aggregate labs from `labevents` and detect RRT from procedures

## Subtleties to watch for

- **Creatinine cap at 4**: patients on RRT or with Cr > 4 are scored as Cr = 4
- **Sodium is conditional**: only adjusts if MELD Initial > 11
- **INR constant term**: +0.643 added even at INR = 1
- **Score range**: minimum ~6 (all normal), maximum 40 (hard cap)
- The `mimiciv_derived.meld` table is always dropped (it's the answer)
