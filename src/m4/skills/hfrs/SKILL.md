---
name: hfrs
description: Calculate Hospital Frailty Risk Score (HFRS) for ICU patients using ICD diagnosis codes. Use for frailty assessment, risk stratification, or outcome prediction in older patients. Supports both ICD-9-CM and ICD-10-CM codes for MIMIC-IV compatibility.
tier: expert
---

# Hospital Frailty Risk Score (HFRS)

Calculate HFRS from ICD diagnosis codes. Based on Gilbert et al. (2018) Lancet methodology with 109 weighted ICD-10 codes.

## When to Use This Skill

- Assessing frailty in ICU or hospitalized patients
- Risk stratification for older adults
- Predicting 30-day mortality, prolonged length of stay, or readmission
- Research requiring a validated frailty metric from administrative data

## Methodology

Per the original publication, HFRS is calculated using diagnoses from:
1. **The current (index) admission**
2. **All emergency admissions in the preceding 2 years**

Each unique ICD code is counted only once, even if it appears in multiple admissions.

## Risk Categories

| Score | Category | 30-day Mortality OR |
|-------|----------|---------------------|
| < 5 | Low | Reference |
| 5-15 | Intermediate | 1.65 (1.62-1.68) |
| > 15 | High | 1.71 (1.68-1.75) |

## Critical Implementation Notes

1. **ICD-9 mappings are NOT part of the original publication.** They have been added for MIMIC-IV compatibility, which contains both ICD-9 and ICD-10 coded admissions. Use ICD-9 mappings with appropriate caution.

2. **Emergency admission types in MIMIC-IV**: The SQL implementation considers `EMERGENCY`, `URGENT`, and `EW EMER.` as emergency admissions.

3. **Code matching uses 3-character prefix** for ICD-10 (e.g., `F05` matches `F05.0`, `F05.1`). ICD-9 uses variable-length matching.

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

## Example Queries

### Calculate HFRS for all admissions

```sql
-- See scripts/calculate_hfrs.sql for the complete query
-- Key tables used:
-- - mimiciv_hosp.admissions (admission dates and types)
-- - mimiciv_hosp.diagnoses_icd (ICD codes)

-- Simplified example: score a single admission
SELECT
    a.subject_id,
    a.hadm_id,
    SUM(w.points) AS hfrs_score
FROM mimiciv_hosp.diagnoses_icd d
JOIN mimiciv_hosp.admissions a ON d.hadm_id = a.hadm_id
JOIN hfrs_weights w ON d.icd_code LIKE w.icd_prefix || '%'
    AND d.icd_version = w.icd_version
GROUP BY a.subject_id, a.hadm_id;
```

### Python: ad-hoc calculation

```python
from scripts.calculate_hfrs import calculate_hfrs

diagnoses = [
    {'icd_code': 'F05', 'icd_version': 10},  # Delirium
    {'icd_code': '2900', 'icd_version': 9},   # Dementia (ICD-9)
    {'icd_code': 'R29', 'icd_version': 10},   # Falls
]
result = calculate_hfrs(diagnoses)
print(f"HFRS: {result['score']} ({result['risk_category']} risk)")
```

## References

- Gilbert T, et al. "Development and validation of a Hospital Frailty Risk Score focusing on older people in acute care settings using electronic hospital records: an observational study." Lancet. 2018;391:1775-82.
