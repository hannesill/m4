---
name: oasis-score
description: Calculate OASIS (Oxford Acute Severity of Illness Score) for ICU patients in MIMIC-IV. OASIS is a parsimonious severity score for mortality prediction using 10 variables without requiring laboratory values. Use this skill when: (1) predicting in-hospital mortality for ICU patients, (2) lab data is incomplete or unavailable, (3) quick severity assessment is needed without lab turnaround time, (4) comparing severity scores (OASIS vs APACHE/SAPS), (5) analyzing ICU patient outcomes, or (6) working with first 24-hour ICU data. Supports both BigQuery (pre-computed tables available) and DuckDB (requires setup). For DuckDB setup or troubleshooting, see references/ folder.
---

# OASIS Score Calculation

The Oxford Acute Severity of Illness Score (OASIS) predicts in-hospital mortality using only vital signs, urine output, and administrative data from the first 24 hours of ICU admission—no laboratory values required.

**Key advantages over APACHE/SAPS:**
- Simpler: 10 variables vs 15-17
- Faster: No lab turnaround time
- Similar predictive accuracy

## Score Components

OASIS uses these 10 variables from the first 24 hours:

| Variable | Range | Points |
|----------|-------|--------|
| Age | <24 to ≥90 | 0-9 |
| Pre-ICU LOS | <10 min to ≥18708 min | 0-5 |
| Glasgow Coma Scale | ≤7 to ≥15 | 0-10 |
| Heart Rate | <33 to >125 bpm | 0-6 |
| Mean Blood Pressure | <20.65 to >143.44 mmHg | 0-4 |
| Respiratory Rate | <6 to >44 breaths/min | 0-10 |
| Temperature | <33.22 to >39.88°C | 0-6 |
| Urine Output | <671 to >6897 mL/day | 0-10 |
| Mechanical Ventilation | Yes/No | 0 or 9 |
| Elective Surgery | Yes/No | 0 or 6 |

**Total score range:** 0-67 (higher = higher mortality risk)

**Mortality probability:** `oasis_prob = 1 / (1 + exp(-(-6.1746 + 0.1275 * oasis)))`

## Quick Start

### Check if OASIS Table Exists

**BigQuery:**
```sql
SELECT COUNT(*) FROM `physionet-data.mimiciv_derived.oasis` LIMIT 1;
```

**DuckDB:**
```sql
SELECT COUNT(*) FROM mimiciv_derived.oasis;
```

**If table doesn't exist:** See [references/setup-duckdb.md](references/setup-duckdb.md) for DuckDB setup, or [references/troubleshooting.md](references/troubleshooting.md) for help.

### Basic Usage

**BigQuery example:**
```sql
-- Get high-risk patients
SELECT
    stay_id,
    subject_id,
    oasis,
    oasis_prob,
    CASE
        WHEN oasis < 20 THEN 'Low Risk'
        WHEN oasis < 30 THEN 'Moderate Risk'
        WHEN oasis < 40 THEN 'High Risk'
        ELSE 'Very High Risk'
    END AS risk_category
FROM `physionet-data.mimiciv_derived.oasis`
WHERE oasis >= 30
ORDER BY oasis_prob DESC
LIMIT 100;
```

**DuckDB example:**
```sql
-- Same query, different table reference
SELECT
    stay_id,
    subject_id,
    oasis,
    oasis_prob,
    CASE
        WHEN oasis < 20 THEN 'Low Risk'
        WHEN oasis < 30 THEN 'Moderate Risk'
        WHEN oasis < 40 THEN 'High Risk'
        ELSE 'Very High Risk'
    END AS risk_category
FROM mimiciv_derived.oasis
WHERE oasis >= 30
ORDER BY oasis_prob DESC
LIMIT 100;
```

## Available Columns

Pre-computed OASIS table includes:

```sql
SELECT
    subject_id,           -- Patient ID
    hadm_id,             -- Hospital admission ID
    stay_id,             -- ICU stay ID
    oasis,               -- Total OASIS score (0-67)
    oasis_prob,          -- Predicted mortality probability (0-1)
    -- Component scores and values:
    age, age_score,
    preiculos, preiculos_score,           -- Pre-ICU length of stay
    gcs, gcs_score,                       -- Glasgow Coma Scale
    heartrate, heart_rate_score,
    meanbp, mbp_score,                    -- Mean blood pressure
    resprate, resp_rate_score,
    temp, temp_score,
    urineoutput, urineoutput_score,
    mechvent, mechvent_score,             -- Mechanical ventilation
    electivesurgery, electivesurgery_score
FROM mimiciv_derived.oasis;
```

## Common Use Cases

### 1. Identify High-Risk Patients

```sql
SELECT stay_id, oasis, oasis_prob
FROM mimiciv_derived.oasis
WHERE oasis_prob >= 0.5
ORDER BY oasis_prob DESC;
```

### 2. Compare OASIS vs SAPS-II

```sql
SELECT
    o.stay_id,
    o.oasis,
    o.oasis_prob AS oasis_mortality,
    s.sapsii,
    s.sapsii_prob AS sapsii_mortality,
    ABS(o.oasis_prob - s.sapsii_prob) AS diff
FROM mimiciv_derived.oasis o
INNER JOIN mimiciv_derived.sapsii s ON o.stay_id = s.stay_id
ORDER BY diff DESC;
```

### 3. Analyze by Risk Category

```sql
SELECT
    CASE
        WHEN oasis < 20 THEN 'Low'
        WHEN oasis < 30 THEN 'Moderate'
        WHEN oasis < 40 THEN 'High'
        ELSE 'Very High'
    END AS risk,
    COUNT(*) AS patients,
    AVG(oasis_prob) AS avg_mortality
FROM mimiciv_derived.oasis
GROUP BY risk
ORDER BY avg_mortality;
```

## Important Notes

1. **Pre-ICU LOS scoring is non-linear:**
   - <10 min: 5 points (immediate ICU admission)
   - 10-297 min: 3 points
   - 297-1440 min: 0 points (optimal)
   - 1440-18708 min: 2 points
   - >18708 min: 1 point

2. **Elective surgery requires BOTH:**
   - Elective admission type AND
   - Surgical service

3. **Ventilation flag cannot be missing:** Defaults to 0 if no ventilation data found.

## Backend-Specific Information

### BigQuery
- ✅ Pre-computed tables available
- Location: `physionet-data.mimiciv_derived.oasis`
- No setup required

### DuckDB
- ✅ Derived tables auto-created during `m4 init`
- Location: `mimiciv_derived.oasis` (and related tables)
- For manual setup: [references/setup-duckdb.md](references/setup-duckdb.md)
- SQL files: [scripts/oasis_duckdb.sql](scripts/oasis_duckdb.sql) for custom queries

**Note:** Starting with M4 v0.4, derived tables (age, GCS, vitals, urine output, ventilation, etc.) are automatically created when running `m4 init`. Use `--no-derived` to skip.

For detailed backend guidance, see [references/backend-guide.md](references/backend-guide.md).

## Troubleshooting

**Table not found?** See [references/troubleshooting.md](references/troubleshooting.md)

**Syntax errors?** You may be using BigQuery syntax on DuckDB or vice versa. Check [references/backend-guide.md](references/backend-guide.md) for syntax differences.

**Performance issues?** Pre-computed tables query in <1 second. On-the-fly calculation takes 30+ seconds. See setup guide to create derived tables.

## References

- Johnson AEW, Kramer AA, Clifford GD. "A new severity of illness scale using a subset of Acute Physiology And Chronic Health Evaluation data elements shows comparable predictive accuracy." Critical Care Medicine. 2013;41(7):1711-1718.
- MIMIC-IV Documentation: https://mimic.mit.edu/docs/iv/
- Source SQL: https://github.com/MIT-LCP/mimic-code/tree/main/mimic-iv/concepts/score
