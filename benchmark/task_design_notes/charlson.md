# Charlson Comorbidity Index

## What it is

The Charlson Comorbidity Index (CCI) is a weighted score (0-33+) that quantifies
comorbidity burden for each hospital admission using ICD diagnosis codes. Introduced
by Charlson et al. (1987), it is the most widely used comorbidity index in clinical
research. Higher scores predict increased mortality.

## The 17 conditions and weights

| Weight | Conditions |
|--------|------------|
| 1 | Myocardial infarction, CHF, PVD, Cerebrovascular disease, Dementia, COPD, Rheumatic disease, Peptic ulcer, Mild liver disease, Diabetes without CC |
| 2 | Diabetes with CC, Paraplegia, Renal disease, Malignant cancer |
| 3 | Severe liver disease |
| 6 | Metastatic solid tumor, AIDS |

### Age score (additional)

| Age | Points |
|-----|--------|
| <= 50 | 0 |
| 51-60 | 1 |
| 61-70 | 2 |
| 71-80 | 3 |
| > 80  | 4 |

### Hierarchy rules

Three condition pairs have hierarchy overrides:
- **Liver**: severe (weight 3) overrides mild (weight 1) → `GREATEST(mild, 3 * severe)`
- **Diabetes**: with complications (weight 2) overrides without (weight 1) → `GREATEST(2 * with_cc, without_cc)`
- **Cancer**: metastatic (weight 6) overrides non-metastatic (weight 2) → `GREATEST(2 * cancer, 6 * metastatic)`

## Data sources in MIMIC-IV

- **ICD codes**: `mimiciv_hosp.diagnoses_icd` — contains both ICD-9 (pre-Oct 2015) and
  ICD-10 (post-Oct 2015) codes. Uses Quan 2005 mapping algorithms.
- **Admissions**: `mimiciv_hosp.admissions` — one row per admission
- **Age**: `mimiciv_derived.age` (standard) or computed from `mimiciv_hosp.patients` (raw)

## Why this tests different capabilities than severity scores

- **ICD code mapping**: Tests ability to implement extensive pattern matching on
  diagnostic codes (17 conditions x 2 ICD versions = 34 code sets)
- **Per-admission, not per-ICU-stay**: Keyed by `hadm_id`
- **No time window or measurement aggregation**: Pure code lookup + scoring
- **Hierarchy logic**: Agent must handle the 3 override pairs correctly
- **Large specification**: The ICD code mappings make for a lengthy instruction

## Why only raw

The standard variant was removed because the standard/raw gap was negligible:
the core complexity (ICD code mapping) uses raw tables in both modes. The
remaining raw task drops the derived `age` table, so the agent must compute age
from `patients.anchor_age` and the admittime-to-anchor_year offset.

## Subtleties to watch for

- Dual ICD version handling: MIMIC-IV spans the ICD-9 to ICD-10 transition
- SUBSTR-based matching: codes match on prefixes (e.g., ICD-9 '410' matches '4100', '4101')
- Some ICD-9 codes use BETWEEN ranges (e.g., '4254' to '4259')
- Admissions without any diagnoses should still appear with all flags = 0
- Age score uses the `mimiciv_derived.age` table which computes age at admission
