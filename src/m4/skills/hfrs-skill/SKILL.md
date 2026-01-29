---
name: hfrs-skill
description: Calculate Hospital Frailty Risk Score (HFRS) for ICU patients. Use when asked to assess frailty, calculate HFRS, or evaluate frailty risk from ICD diagnosis codes. Supports both ICD-9-CM and ICD-10-CM codes for MIMIC-IV compatibility. Based on Gilbert et al. (2018) Lancet methodology with 109 ICD-10 codes.
license: Apache-2.0
metadata:
  author: m4-clinical-extraction
  version: "1.0"
  database: mimic-iv
  category: severity-scores
  source: https://doi.org/10.1016/S0140-6736(18)30668-8
  validated: False
---

# Hospital Frailty Risk Score (HFRS) Calculator

Calculate HFRS from ICD diagnosis codes. Based on Gilbert et al. (2018) Lancet.

## Risk Categories

| Score | Category | 30-day Mortality OR |
|-------|----------|---------------------|
| < 5 | Low | Reference |
| 5-15 | Intermediate | 1.65 (1.62-1.68) |
| > 15 | High | 1.71 (1.68-1.75) |

## Usage

### Python Function

```python
from scripts.calculate_hfrs import calculate_hfrs

# With list of diagnosis dicts
diagnoses = [
    {'icd_code': 'F05', 'icd_version': 10},  # Delirium
    {'icd_code': '2900', 'icd_version': 9},   # Dementia (ICD-9)
    {'icd_code': 'R29', 'icd_version': 10},  # Falls
]
result = calculate_hfrs(diagnoses)
print(f"HFRS: {result['score']} ({result['risk_category']} risk)")
```

### SQL Query for MIMIC-IV

```sql
-- Calculate HFRS for a specific patient
WITH hfrs_weights AS (
    -- ICD-10 weights (109 codes)
    SELECT 'F00' as icd3, 7.1 as weight UNION ALL
    SELECT 'G81', 4.4 UNION ALL SELECT 'G30', 4.0 UNION ALL
    SELECT 'I69', 3.7 UNION ALL SELECT 'R29', 3.6 UNION ALL
    SELECT 'N39', 3.2 UNION ALL SELECT 'F05', 3.2 UNION ALL
    SELECT 'W19', 3.2 UNION ALL SELECT 'S00', 3.2 UNION ALL
    -- ... (full list in references/hfrs_icd_codes.csv)
),
icd9_map AS (
    -- ICD-9 to ICD-10 mappings
    SELECT '2900' as icd9, 'F00' as icd10 UNION ALL
    SELECT '2901', 'F00' UNION ALL SELECT '2902', 'F00' UNION ALL
    -- ... (full mappings in references/hfrs_icd_codes.csv)
),
patient_diag AS (
    SELECT DISTINCT
        d.subject_id,
        d.hadm_id,
        CASE 
            WHEN d.icd_version = 10 THEN LEFT(d.icd_code, 3)
            WHEN d.icd_version = 9 THEN m.icd10
        END as icd10_code
    FROM mimiciv_hosp.diagnoses_icd d
    LEFT JOIN icd9_map m ON d.icd_code LIKE m.icd9 || '%' AND d.icd_version = 9
    WHERE d.subject_id = {subject_id}
)
SELECT 
    p.subject_id,
    p.hadm_id,
    ROUND(SUM(COALESCE(h.weight, 0)), 1) as hfrs_score,
    CASE 
        WHEN SUM(COALESCE(h.weight, 0)) < 5 THEN 'Low'
        WHEN SUM(COALESCE(h.weight, 0)) < 15 THEN 'Intermediate'
        ELSE 'High'
    END as risk_category
FROM patient_diag p
LEFT JOIN hfrs_weights h ON p.icd10_code = h.icd3
GROUP BY p.subject_id, p.hadm_id;
```

## Top Contributing Codes

| ICD-10 | Points | Description |
|--------|--------|-------------|
| F00 | 7.1 | Dementia in Alzheimer's |
| G81 | 4.4 | Hemiplegia |
| G30 | 4.0 | Alzheimer's disease |
| I69 | 3.7 | Sequelae of CVD |
| R29 | 3.6 | Tendency to fall |
| F05 | 3.2 | Delirium |
| N39 | 3.2 | UTI/incontinence |
| W19 | 3.2 | Unspecified fall |

Full 109-code list: `references/hfrs_icd_codes.csv`

## References

Gilbert T, et al. Development and validation of a Hospital Frailty Risk Score. Lancet 2018;391:1775-82. DOI: 10.1016/S0140-6736(18)30668-8
