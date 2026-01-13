# M4 Clinical Research Skills Index

This directory contains Agent Skills extracted from the MIT-LCP repositories (mimic-code, eicu-code) to enable clinical research with the M4 framework.

## Skills by Category

### Severity Scores

| Skill | Description | Database |
|-------|-------------|----------|
| [sofa-score](sofa-score/SKILL.md) | Sequential Organ Failure Assessment score calculation | MIMIC-IV |
| [apsiii-score](apsiii-score/SKILL.md) | APACHE III (Acute Physiology Score III) with mortality prediction | MIMIC-IV |
| [sapsii-score](sapsii-score/SKILL.md) | SAPS-II score with mortality prediction | MIMIC-IV |
| [oasis-score](oasis-score/SKILL.md) | Oxford Acute Severity of Illness Score (no labs required) | MIMIC-IV |
| [lods-score](lods-score/SKILL.md) | Logistic Organ Dysfunction Score | MIMIC-IV |
| [sirs-criteria](sirs-criteria/SKILL.md) | Systemic Inflammatory Response Syndrome criteria | MIMIC-IV |

### Sepsis and Infection

| Skill | Description | Database |
|-------|-------------|----------|
| [sepsis-3-cohort](sepsis-3-cohort/SKILL.md) | Sepsis-3 cohort identification (SOFA >= 2 + infection) | MIMIC-IV |
| [suspicion-of-infection](suspicion-of-infection/SKILL.md) | Suspected infection events (antibiotic + culture) | MIMIC-IV |

### Organ Failure

| Skill | Description | Database |
|-------|-------------|----------|
| [kdigo-aki-staging](kdigo-aki-staging/SKILL.md) | KDIGO AKI staging using creatinine and urine output | MIMIC-IV |

### Medications and Treatments

| Skill | Description | Database |
|-------|-------------|----------|
| [vasopressor-equivalents](vasopressor-equivalents/SKILL.md) | Norepinephrine-equivalent dose calculation | MIMIC-IV |

### Laboratory and Measurements

| Skill | Description | Database |
|-------|-------------|----------|
| [baseline-creatinine](baseline-creatinine/SKILL.md) | Baseline creatinine estimation for AKI staging | MIMIC-IV |
| [gcs-calculation](gcs-calculation/SKILL.md) | Glasgow Coma Scale extraction with intubation handling | MIMIC-IV |

### Cohort Definitions

| Skill | Description | Database |
|-------|-------------|----------|
| [first-icu-stay](first-icu-stay/SKILL.md) | First ICU stay selection and cohort construction | MIMIC-IV |

### Data Quality and Structure

| Skill | Description | Database |
|-------|-------------|----------|
| [mimic-table-relationships](mimic-table-relationships/SKILL.md) | MIMIC-IV table relationships and join patterns | MIMIC-IV |
| [mimic-eicu-mapping](mimic-eicu-mapping/SKILL.md) | Mapping between MIMIC-IV and eICU databases | Both |
| [clinical-research-pitfalls](clinical-research-pitfalls/SKILL.md) | Common methodological mistakes and how to avoid them | Both |

### M4 Framework

| Skill | Description | Database |
|-------|-------------|----------|
| [m4-api](m4-api/SKILL.md) | Python API for M4 clinical data queries | Both |

---

## Skill Statistics

- **Total Skills**: 17
- **MIMIC-IV Specific**: 13
- **eICU Specific**: 0
- **Multi-Database**: 4

## Category Distribution

- Severity Scores: 6
- Sepsis/Infection: 2
- Organ Failure: 1
- Medications: 1
- Lab/Measurements: 2
- Cohort Definitions: 1
- Data Quality: 3
- M4 Framework: 1

---

## Gaps and Future Work

### Concepts Not Yet Extracted

The following valuable concepts exist in the source repositories but were not extracted:

1. **APACHE-II Score**: Older scoring system, still used in some contexts
2. **Charlson Comorbidity Index**: Important confounder adjustment
3. **Ventilation Duration**: Time on mechanical ventilation
4. **Antibiotic Classification**: Categorization by class/spectrum
5. **MELD Score**: Model for End-Stage Liver Disease
6. **CRRT Concepts**: Continuous renal replacement therapy details
7. **Code Status**: DNR/DNI documentation

### eICU-Specific Concepts Needed

- APACHE IV (pre-computed in eICU)
- eICU pivoted lab values
- eICU vasopressor concepts
- Hospital-level clustering

### Additional Data Quality Skills

- Unit conversion guidelines
- Outlier detection thresholds
- Timestamp and time zone handling

---

## Usage Notes

1. **Pre-computed Tables**: Most skills reference pre-computed derived tables in `mimiciv_derived` schema. These are available on BigQuery and can be regenerated for PostgreSQL.

2. **SQL Dialect**: SQL examples use BigQuery syntax. For PostgreSQL, convert using the `convert_bigquery_to_postgres.sh` script in mimic-code.

3. **Script Files**: Full SQL implementations are in each skill's `scripts/` subdirectory.

4. **Validation Status**: All skills are derived from MIT-LCP validated code repositories.

---

## References

- MIMIC-IV: https://mimic.mit.edu/docs/iv/
- eICU: https://eicu-crd.mit.edu/
- mimic-code: https://github.com/MIT-LCP/mimic-code
- eicu-code: https://github.com/MIT-LCP/eicu-code
- Agent Skills Standard: https://agentskills.io
