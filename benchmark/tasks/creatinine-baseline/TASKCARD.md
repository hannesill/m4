# Baseline Creatinine Estimation

## What it is

Estimates the patient's baseline (pre-illness) serum creatinine for each hospital admission.
The true baseline is often unknown; this concept uses a hierarchical approach that reflects
standard clinical research practice.

The baseline creatinine is critical for KDIGO AKI staging, which compares current creatinine
to the estimated baseline.

## The hierarchical decision logic

1. **If lowest admission creatinine <= 1.1 mg/dL**: Use the observed minimum (assumed normal)
2. **If CKD diagnosis present (ICD-9 585.x or ICD-10 N18.x)**: Use the observed minimum
3. **Otherwise**: Estimate via MDRD equation assuming eGFR = 75 mL/min/1.73m²

### MDRD estimation formula

- Male: `scr = (75 / 186 / age^(-0.203))^(-1/1.154)`
- Female: `scr = (75 / 186 / age^(-0.203) / 0.742)^(-1/1.154)`

## Data sources in MIMIC-IV

- **Creatinine values**: `mimiciv_derived.chemistry` (standard) or `mimiciv_hosp.labevents` itemid 50912 (raw)
- **Age**: `mimiciv_derived.age` (standard) or computed from `mimiciv_hosp.patients` + `mimiciv_hosp.admissions` (raw)
- **Gender**: `mimiciv_hosp.patients`
- **CKD diagnosis**: `mimiciv_hosp.diagnoses_icd` (ICD-9 585, ICD-10 N18)

## Why this tests different capabilities than severity scores

- **Per-admission, not per-ICU-stay**: Keyed by `hadm_id`, not `stay_id`
- **Hierarchical decision tree**: Tests conditional logic, not just numeric thresholds
- **ICD code lookup**: Requires querying diagnosis tables for CKD
- **Mathematical formula**: MDRD back-calculation involves multi-step arithmetic
- **No time window**: Uses all measurements during admission, not a fixed window

## Why standard vs raw

- **Standard**: `mimiciv_derived.age` and `mimiciv_derived.chemistry` are available
- **Raw**: Baseline creatinine and task-relevant age/chemistry intermediates are
  dropped; agent must compute age from `patients.anchor_age` + year math, and
  extract creatinine from `labevents`

## Subtleties to watch for

- Adults only (age >= 18); pediatric creatinine norms differ
- The MDRD race coefficient is deliberately omitted (consistent with recent guidelines)
- CKD codes are assigned at discharge (technically future information)
- Missing creatinine → NULL baseline (not zero)
- The `scr_min` is the minimum across the entire admission, not just first day
