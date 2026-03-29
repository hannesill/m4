# OASIS -- Oxford Acute Severity of Illness Score

## What it is

OASIS is a severity score (0-71) that predicts hospital mortality using only 10
variables — none of which require laboratory data. Developed by Johnson et al.
(2013) as a simpler alternative to APACHE/SAPS when lab values are unavailable
or unreliable.

## The 10 components

| Variable | Points | Scoring Logic |
|----------|--------|---------------|
| **Pre-ICU LOS** (minutes) | 0-5 | 5 (<10.2), 3 (10.2-296), 0 (297-1439), 2 (1440-18707), 1 (>=18708) |
| **Age** | 0-9 | 0 (<24), 3 (24-53), 6 (54-77), 9 (78-89), 7 (>=90) |
| **GCS** | 0-10 | 10 (<=7), 4 (8-13), 3 (14), 0 (15) |
| **Heart Rate** | 0-6 | 6 (>125), 4 (<33), 3 (107-125), 1 (89-106), 0 (33-88) |
| **Mean BP** | 0-4 | 4 (<20.65), 3 (<51 or >143.44), 2 (51-61.33), 0 (61.33-143.44) |
| **Respiratory Rate** | 0-10 | 10 (<6), 9 (>44), 6 (>30), 1 (>22 or <13), 0 (13-22) |
| **Temperature** | 0-6 | 6 (>39.88°C), 4 (33.22-35.93), 3 (<33.22), 2 (35.93-36.39 or 36.89-39.88), 0 (36.39-36.89) |
| **Urine Output** (mL/day) | 0-10 | 10 (<671), 8 (>6897), 5 (671-1427), 1 (1427-2544), 0 (2544-6897) |
| **Mechanical Ventilation** | 0-9 | 9 (ventilated), 0 (not ventilated) |
| **Elective Surgery** | 0-6 | 0 (elective surgical), 6 (all others) |

Total = sum of all 10 component scores. Missing data → score 0.

## Data sources in MIMIC-IV

- **Pre-ICU LOS**: computed from `admissions.admittime` to `icustays.intime`
- **Age**: `age` derived table
- **GCS**: `first_day_gcs`
- **HR, MBP, RR, Temp**: `first_day_vitalsign`
- **Urine Output**: `first_day_urine_output`
- **Mechanical Ventilation**: `ventilation` (InvasiveVent status overlapping first 24h)
- **Elective Surgery**: `admissions.admission_type` + `services` (surgical flag, includes ORTHO)

## Why no 12h variant

OASIS uses `first_day_*` tables (24h aggregation). The mortality formula is calibrated
on 24h data. Urine output scoring uses 24h totals. A 12h variant would require
custom windowing and recalibration.

## Why standard vs raw

- **Standard**: derived tables (`first_day_vitalsign`, `age`, `ventilation`, etc.) available
- **Raw**: derived tables dropped; agent must aggregate from `chartevents`, compute age,
  detect ventilation from procedures, and sum urine from `outputevents`

## Subtleties to watch for

- **No lab values needed** — makes OASIS raw mode easier than other scores
- **Pre-ICU LOS scoring is non-monotonic**: best prognosis at 5-24h (297-1440 min → 0 pts)
- **Elective surgery is inverted**: elective surgical admission = 0 pts (best), everything else = 6 pts
- **Surgical flag** includes ORTHO service (not just `%surg%` pattern match)
- **Ventilation detection** checks if any InvasiveVent period overlaps the first 24h
- The `mimiciv_derived.oasis` table is always dropped (it's the answer)
