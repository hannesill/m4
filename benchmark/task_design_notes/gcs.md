# GCS -- Glasgow Coma Scale

## What it is

GCS is a neurological assessment (3-15) measuring consciousness via 3 components:
Eye opening (1-4), Verbal response (1-5), Motor response (1-6). Total = sum of
components. Lower scores indicate deeper impairment. Introduced by Teasdale &
Jennett (1974).

## The 3 components

| Component | 1 | 2 | 3 | 4 | 5 | 6 |
|-----------|---|---|---|---|---|---|
| **Eye** | None | To pain | To voice | Spontaneous | — | — |
| **Verbal** | None | Incomprehensible | Inappropriate | Confused | Oriented | — |
| **Motor** | None | Extension | Flexion | Withdrawal | Localizing | Obeys |

Total GCS = Eye + Verbal + Motor (range 3-15).

## Data sources in MIMIC-IV

- **Eye, Verbal, Motor**: `chartevents` itemids 220739, 223900, 223901
- **Intubation**: verbal value "No Response-ETT" → verbal component = 0
- Time-series `gcs` derived table computes total with carry-forward logic
- `first_day_gcs` aggregates to minimum GCS in first 24h

## Why standard vs raw

- **Standard**: `first_day_gcs` dropped; agent has `gcs` time-series table and must
  aggregate to first-day minimum
- **Raw**: both `first_day_gcs` and `gcs` dropped; agent must parse `chartevents`
  directly, implementing component carry-forward and intubation handling

## Subtleties to watch for

- **Intubation**: verbal "No Response-ETT" sets verbal=0, and GCS becomes 15 (assumes
  unimpaired consciousness if only intubation prevents verbal assessment)
- **6-hour carry-forward**: missing components use the most recent value within 6h
- **Default imputation**: if no previous value exists, components default to normal
  (motor=6, verbal=5, eyes=4 → GCS=15)
- The `mimiciv_derived.first_day_gcs` table is always dropped (it's the answer)
