# APSIII -- Acute Physiology Score III (APACHE III)

## What it is

APS III is the physiological component of the APACHE III scoring system (0-299).
It uses 16 components from the first 24 hours of ICU stay with a unique "worst
from normal" scoring philosophy — each variable is scored by its maximum distance
from a physiological reference value, not simply its min or max.

## The 16 components

| Component | Reference | Points | Key Feature |
|-----------|-----------|--------|-------------|
| Heart Rate | 75 bpm | 0-17 | Worst = furthest from 75 |
| Mean BP | 90 mmHg | 0-23 | Worst = furthest from 90 |
| Temperature | 38°C | 0-20 | Worst = furthest from 38 |
| Respiratory Rate | 19/min | 0-18 | Worst = furthest from 19; vent interaction |
| PaO2 or A-aDO2 | — | 0-15 | PaO2 if non-vent + FiO2<50%; A-aDO2 if vent + FiO2>=50% |
| Hematocrit | 45.5% | 0-3 | Worst = furthest from 45.5 |
| WBC | 11.5 x10^9/L | 0-19 | Worst = furthest from 11.5 |
| Creatinine | 1.0 mg/dL | 0-10 | ARF modifier changes scoring range |
| Urine Output | — | 0-15 | 24h total, 6 thresholds |
| BUN | — | 0-12 | Always uses max |
| Sodium | 145.5 mEq/L | 0-4 | Worst = furthest from 145.5 |
| Albumin | 3.5 g/dL | 0-11 | Worst = furthest from 3.5 |
| Bilirubin | — | 0-16 | Always uses max |
| Glucose | 130 mg/dL | 0-9 | Worst = furthest from 130 |
| Acid-Base (pH/PaCO2) | — | 0-12 | 2D lookup matrix (7 pH bands × 4 PaCO2 bands) |
| GCS | — | 0-48 | 3D lookup matrix (eyes × verbal × motor) |

Total = sum of all 16 scores. Missing data → score 0.

## Data sources in MIMIC-IV

- **Vitals**: `first_day_vitalsign` (HR, MBP, Temp, RR, Glucose)
- **Labs**: `first_day_lab` (Hematocrit, WBC, Creatinine, BUN, Sodium, Albumin, Bilirubin, Glucose)
- **Blood Gas**: `bg` (PaO2, A-aDO2, pH, PaCO2; arterial only)
- **Ventilation**: `ventilation` (for respiratory and oxygenation scoring)
- **GCS**: `first_day_gcs` (components: eyes, verbal, motor, unable)
- **Urine Output**: `first_day_urine_output`
- **ARF Detection**: creatinine >= 1.5 AND UO < 410 AND no CKD 4-6 (from `diagnoses_icd`)

## Why standard vs raw

- **Standard**: `apsiii` dropped; agent has all first_day tables + bg + ventilation
- **Raw**: APS III and task-relevant upstream derived tables are dropped; most
  complex raw task in benchmark

## Subtleties to watch for

- **"Worst from normal"**: NOT min/max — uses value furthest from reference. When
  equidistant, the higher score wins.
- **ARF modifier**: if ARF detected, creatinine scoring changes to 0/10 scale (not 0-7)
- **PaO2 vs A-aDO2**: mutually exclusive based on ventilation + FiO2 >= 50% threshold
- **Arterial specimens only** (`specimen = 'ART.'`) for blood gas
- **3D GCS lookup**: eyes × verbal × motor → score (21-cell matrix). If `gcs_unable=1`
  (intubated), gcs_score=0
- **Acid-base 2D matrix**: pH band × PaCO2 band → score (complex interaction)
- **Ventilation + RR interaction**: if ventilated AND RR < 14, resp_rate_score = 0
- The `mimiciv_derived.apsiii` table is always dropped (it's the answer)
