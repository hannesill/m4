---
name: equiflow
description: Generate equity-focused cohort selection flow diagrams. Automatically tracks demographic, socioeconomic, and outcome variables (gender, race, insurance, language, age, LOS, mortality) at each exclusion step. Calculates SMD to detect selection bias. Based on Ellen et al. (2024) J Biomed Inform.
license: Apache-2.0
metadata:
  author: m4-clinical-extraction
  version: "1.0"
  database: both
  category: data-quality
  source: https://doi.org/10.1016/j.jbi.2024.104631
  validated: false
---

# EquiFlow - Equity-Focused Cohort Flow Diagrams

Visualize and quantify selection bias in clinical ML/research cohorts.

## When to Use

- Building patient cohorts from MIMIC-IV
- Documenting inclusion/exclusion criteria
- Detecting disproportionate exclusion of vulnerable groups
- Generating CONSORT-style flow diagrams with equity focus

## Quick Start

```python
from cohort_flow import CohortFlow

# Initialize - automatically detects equity variables
cf = CohortFlow(df)

# Add exclusion criteria
cf.exclude(df['anchor_age'] >= 18, "Age < 18", "Adults")
cf.exclude(df['los'] >= 24, "LOS < 24h", "LOS ≥ 24h")

# View results
cf.view_flows()           # N at each step
cf.view_drifts()          # SMD values
cf.check_bias()           # Flag SMD > 0.2
cf.plot("cohort_flow")    # Generate diagram
```

## Default Equity Variables

When no variables are specified, CohortFlow automatically tracks:

| Category | Variables | Column Aliases |
|----------|-----------|----------------|
| **Demographics** | gender | gender, sex |
| | race | race, ethnicity |
| | age | anchor_age, age, admission_age |
| **Socioeconomic** | insurance | insurance, insurance_type, payer |
| | language | language, primary_language |
| | marital_status | marital_status, marital |
| **Clinical** | los | los, length_of_stay, icu_los |
| **Outcome** | mortality | hospital_expire_flag, mortality, death |

## Input/Output

### Input

| Parameter | Description | Default |
|-----------|-------------|---------|
| `data` | Patient DataFrame | Required |
| `categorical` | Categorical variables | Auto-detect |
| `normal` | Normal continuous vars | Auto-detect |
| `nonnormal` | Skewed continuous vars | Auto-detect |
| `additional` | Extra variables to track | None |

### Output

1. **Flow Table**: N at each exclusion step
2. **Characteristics Table**: Variable distributions per step
3. **Drifts Table**: SMD between consecutive cohorts
4. **Flow Diagram**: Visual PDF/PNG

## Usage Patterns

### Pattern 1: Full Auto (Recommended)
```python
cf = CohortFlow(df)  # Auto-detects all equity variables
```

### Pattern 2: User-Specified Only
```python
cf = CohortFlow(
    df,
    categorical=['gender', 'race'],
    normal=['age'],
    use_defaults=False
)
```

### Pattern 3: Defaults + Additional
```python
cf = CohortFlow(df, additional=['diagnosis_group', 'charlson_score'])
```

## SMD Interpretation

| |SMD| | Interpretation | Action |
|-------|----------------|--------|
| < 0.1 | Negligible | ✓ OK |
| 0.1-0.2 | Small | Monitor |
| **> 0.2** | **Meaningful** | ⚠️ Investigate |
| > 0.5 | Large | ⛔ Serious concern |

## M4 Integration Example

```python
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
cf = CohortFlow(df)  # Auto-detects: gender, race, insurance, language, age, los, mortality

cf.exclude(df['anchor_age'] >= 18, "Age < 18", "Adults")
cf.exclude(df['los'] >= 24, "ICU < 24h", "ICU ≥ 24h")
cf.exclude(df['anchor_age'] <= 90, "Age > 90", "Age 18-90")

# Step 3: Check for bias
print(cf.check_bias())  # Shows variables with SMD > 0.2

# Step 4: Generate diagram
cf.plot("sepsis_cohort_flow")
```

## Dependencies

```bash
pip install equiflow
```

## References

Ellen JG, et al. Participant flow diagrams for health equity in AI. J Biomed Inform. 2024;152:104631.
