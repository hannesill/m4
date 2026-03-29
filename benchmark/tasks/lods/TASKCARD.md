# LODS -- Logistic Organ Dysfunction Score

## What it is

LODS is a severity score (0-22) that quantifies organ dysfunction across 6 systems
using logistic regression-derived weights. Developed by Le Gall et al. (1996) as an
alternative to SOFA, with fewer score levels per organ but different variable
combinations.

## The 6 components

| System | Variables | Scoring | Max |
|--------|-----------|---------|-----|
| **Neurologic** | GCS | 0 (14-15), 1 (9-13), 3 (6-8), 5 (<=5) | 5 |
| **Cardiovascular** | HR, SBP | 0 (normal), 1 (HR>=140 or SBP 90-239), 3 (SBP<70 or >=270), 5 (HR<30 or SBP<40) | 5 |
| **Renal** | BUN, Cr, UO | 0 (normal), 1 (Cr>=1.2 or BUN>=7.5), 3 (Cr>=1.6 or UO<750 or BUN>=28 or UO>=10000), 5 (UO<500 or BUN>=56) | 5 |
| **Pulmonary** | PaO2/FiO2 (ventilated only) | 0 (not ventilated), 1 (PF>=150), 3 (PF<150) | 3 |
| **Hematologic** | WBC, Platelets | 0 (normal), 1 (WBC<2.5 or Plt<50 or WBC>=50), 3 (WBC<1) | 3 |
| **Hepatic** | PT, Bilirubin | 0 (normal), 1 (Bili>=2 or PT>15s or PT<3s) | 1 |

Total = sum of 6 organ scores. Missing data → score 0.

## Data sources in MIMIC-IV

- **GCS**: `first_day_gcs`
- **HR, SBP**: `first_day_vitalsign`
- **BUN, Cr, WBC, Plt, PT, Bilirubin**: `first_day_lab`
- **Urine Output**: `first_day_urine_output`
- **PaO2/FiO2**: `bg` (all specimens) + `ventilation` (InvasiveVent) + `chartevents` (CPAP/BiPAP)
- Missing values → score 0

## Why standard vs raw

- **Standard**: derived tables (`first_day_lab`, `first_day_vitalsign`, etc.) available
- **Raw**: derived tables dropped; agent must aggregate from `chartevents`, `labevents`, `outputevents`

## Subtleties to watch for

- **Pulmonary defaults to 0 when not ventilated** (not NULL) — different from other
  components where NULL means missing data
- **GCS < 3 → NULL** — treated as erroneous data (same as SAPS-II)
- **CPAP detection** via `chartevents` itemid 226732 — extends PaO2/FiO2 scoring to
  patients on CPAP/BiPAP (not just invasive ventilation)
- **Renal requires ALL three variables** (BUN, creatinine, UO) to be non-NULL; if any
  is missing, the entire renal component is NULL (→ 0 after COALESCE)
- **PT threshold**: assumes 12s is normal; abnormal if > 15s or < 3s
- **No arterial specimen filter** — LODS uses the `bg` table without filtering by
  `specimen = 'ART.'`, so venous blood gases may contribute to PaO2/FiO2
- The `mimiciv_derived.lods` table is always dropped (it's the answer)
