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
  validated: true
---

# Hospital Frailty Risk Score (HFRS) Calculator

Calculate HFRS from ICD diagnosis codes. Based on Gilbert et al. (2018) Lancet.

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

## Implementation Notes

### ICD-9 Mapping

The original HFRS was developed using UK NHS data with ICD-10 codes only. **ICD-9 mappings are NOT part of the original publication** but have been added for MIMIC-IV compatibility, which contains both ICD-9 and ICD-10 coded admissions. Use ICD-9 mappings with appropriate caution.

### Emergency Admission Types in MIMIC-IV

The SQL implementation considers the following MIMIC-IV `admission_type` values as emergency admissions:
- `EMERGENCY`
- `URGENT`
- `EW EMER.` (Emergency Ward)

## Usage

### SQL Query for MIMIC-IV

The full SQL implementation is in `scripts/calculate_hfrs.sql`. It calculates HFRS for each admission using:
- Current admission diagnoses
- Prior 2 years of emergency admission diagnoses

```sql
-- Example: Calculate HFRS for a specific patient
-- See scripts/calculate_hfrs.sql for the complete query

-- Key tables used:
-- - mimiciv_hosp.admissions (for admission dates and types)
-- - mimiciv_hosp.diagnoses_icd (for ICD codes)
```

### Python Function

The Python script calculates HFRS from a list of diagnoses (useful for ad-hoc calculations):

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

Note: The Python function calculates HFRS from a provided list of diagnoses. For the full 2-year lookback methodology, use the SQL query or pre-aggregate diagnoses before calling this function.

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

Gilbert T, et al. Development and validation of a Hospital Frailty Risk Score focusing on older people in acute care settings using electronic hospital records: an observational study. Lancet 2018;391:1775-82. DOI: 10.1016/S0140-6736(18)30668-8
