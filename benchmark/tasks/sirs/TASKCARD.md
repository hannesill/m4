# SIRS — Systemic Inflammatory Response Syndrome

## What it is

SIRS is a clinical score (0–4) that detects a generalized inflammatory response.
It was the original basis for diagnosing sepsis before Sepsis-3 replaced it with
SOFA in 2016. SIRS >= 2 plus suspected infection = old sepsis definition.

## The 4 criteria (each scores 0 or 1)


| Criterion   | Positive if                                      |
| ----------- | ------------------------------------------------ |
| Temperature | > 38 C or < 36 C                                 |
| Heart rate  | > 90 bpm                                         |
| Respiratory | RR > 20/min OR PaCO2 < 32 mmHg                   |
| WBC         | > 12k or < 4k cells/mm3, or > 10% immature bands |


Total = sum of four binary scores.

## Data sources in MIMIC-IV

- **Temperature, heart rate, RR**: `chartevents` (vitals), or derived `vitalsign`
- **PaCO2**: arterial blood gas — `labevents` or derived `bg_art`
- **WBC, bands**: `labevents` or derived `first_day_lab`
- Missing values are treated as normal (score 0)

## Why 12h vs 24h

Most ICU studies use the **first 24 hours** after admission (MIMIC provides
pre-aggregated `first_day_`* tables for this). The **12-hour** variant is equally
valid clinically but non-standard — it tests whether an agent can adapt to a
legitimate parameter change rather than blindly following convention.

## Why standard vs raw

- **Standard**: derived tables (`mimiciv_derived.vitalsign`, etc.) are available
- **Raw**: derived tables are dropped, forcing the agent to aggregate from
`chartevents` / `labevents` directly using correct itemids and units

## Subtleties to watch for

- The respiratory criterion has **two sub-conditions** (RR or PaCO2) — agents
often miss the PaCO2 component
- Band count is frequently missing in EHR data
- The 6-hour pre-admission buffer captures ED data when available
- The `mimiciv_derived.sirs` table is always dropped (it's the answer)
