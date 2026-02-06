---
name: equiflow
description: Generate equity-focused cohort selection flow diagrams. Tracks demographic, socioeconomic, and outcome variables at each exclusion step and calculates SMD to detect selection bias. Use for cohort construction, CONSORT-style diagrams, or bias detection in clinical ML/research.
tier: expert
category: clinical
---

# EquiFlow - Equity-Focused Cohort Flow Diagrams

Visualize and quantify selection bias in clinical ML/research cohorts. Based on Ellen et al. (2024) J Biomed Inform.

## When to Use This Skill

- Building patient cohorts from MIMIC-IV or eICU
- Documenting inclusion/exclusion criteria with CONSORT-style diagrams
- Detecting disproportionate exclusion of vulnerable groups
- Quantifying selection bias via Standardized Mean Difference (SMD)

## Default Equity Variables

When no variables are specified, CohortFlow automatically tracks:

| Category | Variables | Column Aliases |
|----------|-----------|----------------|
| Demographics | gender | gender, sex |
| | race | race, ethnicity |
| | age | anchor_age, age, admission_age |
| Socioeconomic | insurance | insurance, insurance_type, payer |
| | language | language, primary_language |
| | marital_status | marital_status, marital |
| Clinical | los | los, length_of_stay, icu_los |
| Outcome | mortality | hospital_expire_flag, mortality, death |

## SMD Interpretation

| |SMD| | Interpretation | Action |
|-------|----------------|--------|
| < 0.1 | Negligible | OK |
| 0.1-0.2 | Small | Monitor |
| > 0.2 | Meaningful | Investigate |
| > 0.5 | Large | Serious concern |

See `references/smd_interpretation.md` for detailed guidance.

## Critical Implementation Notes

1. **Auto-detection**: CohortFlow scans DataFrame columns for known aliases. Override with `use_defaults=False` if you want full control.

2. **SMD > 0.2 is the default threshold** for flagging potential bias. This follows established covariate balance literature.

3. **Missing data**: Exclusion steps that remove patients with missing values can introduce systematic bias. Always check SMD after such steps.

## Example Queries

### Full workflow with MIMIC-IV

```python
from cohort_flow import CohortFlow

# Step 1: Query MIMIC-IV
query = """
SELECT
    p.subject_id, p.gender, p.anchor_age,
    a.race, a.insurance, a.language, a.marital_status,
    a.hospital_expire_flag,
    i.los
FROM mimiciv_hosp.patients p
JOIN mimiciv_hosp.admissions a USING (subject_id)
JOIN mimiciv_icu.icustays i ON a.hadm_id = i.hadm_id
"""
df = execute_query(query)

# Step 2: Build cohort with equity tracking
cf = CohortFlow(df)  # Auto-detects equity variables

cf.exclude(df['anchor_age'] >= 18, "Age < 18", "Adults")
cf.exclude(df['los'] >= 24, "ICU < 24h", "ICU >= 24h")
cf.exclude(df['anchor_age'] <= 90, "Age > 90", "Age 18-90")

# Step 3: Check for bias
print(cf.check_bias())  # Flags variables with SMD > 0.2

# Step 4: Generate diagram
cf.plot("sepsis_cohort_flow")
```

### Minimal example

```python
cf = CohortFlow(df)
cf.exclude(df['anchor_age'] >= 18, "Age < 18", "Adults")
cf.view_drifts()  # SMD values after exclusion
```

## Dependencies

```bash
pip install equiflow
```

## References

- Ellen JG, et al. "Participant flow diagrams for health equity in AI." J Biomed Inform. 2024;152:104631.
