# M4 Skills Index

This directory contains skills for the M4 framework, covering clinical research concepts and system functionality.

## Clinical Skills

### Severity Scores

| Skill | Description |
|-------|-------------|
| [sofa-score](clinical/sofa-score/SKILL.md) | Sequential Organ Failure Assessment score calculation |
| [apache-iv-score](clinical/apache-iv-score/SKILL.md) | APACHE IV with mortality prediction |
| [apsiii-score](clinical/apsiii-score/SKILL.md) | APACHE III (Acute Physiology Score III) with mortality prediction |
| [sapsii-score](clinical/sapsii-score/SKILL.md) | SAPS-II score with mortality prediction |
| [oasis-score](clinical/oasis-score/SKILL.md) | Oxford Acute Severity of Illness Score (no labs required) |
| [lods-score](clinical/lods-score/SKILL.md) | Logistic Organ Dysfunction Score |
| [sirs-criteria](clinical/sirs-criteria/SKILL.md) | Systemic Inflammatory Response Syndrome criteria |
| [hfrs](clinical/hfrs/SKILL.md) | Hospital Frailty Risk Score from ICD codes (Gilbert 2018) |
| [comorbidity-score](clinical/comorbidity-score/SKILL.md) | Charlson and Elixhauser comorbidity indices for risk adjustment |

### Sepsis and Infection

| Skill | Description |
|-------|-------------|
| [sepsis-3-cohort](clinical/sepsis-3-cohort/SKILL.md) | Sepsis-3 cohort identification (SOFA >= 2 + infection) |
| [suspicion-of-infection](clinical/suspicion-of-infection/SKILL.md) | Suspected infection events (antibiotic + culture) |

### Organ Failure

| Skill | Description |
|-------|-------------|
| [kdigo-aki-staging](clinical/kdigo-aki-staging/SKILL.md) | KDIGO AKI staging using creatinine and urine output |

### Medications and Treatments

| Skill | Description |
|-------|-------------|
| [vasopressor-equivalents](clinical/vasopressor-equivalents/SKILL.md) | Norepinephrine-equivalent dose calculation |

### Laboratory and Measurements

| Skill | Description |
|-------|-------------|
| [baseline-creatinine](clinical/baseline-creatinine/SKILL.md) | Baseline creatinine estimation for AKI staging |
| [gcs-calculation](clinical/gcs-calculation/SKILL.md) | Glasgow Coma Scale extraction with intubation handling |

### Cohort Definitions

| Skill | Description |
|-------|-------------|
| [first-icu-stay](clinical/first-icu-stay/SKILL.md) | First ICU stay selection and cohort construction |

### Research Methodology

| Skill | Description |
|-------|-------------|
| [clinical-research-pitfalls](clinical/clinical-research-pitfalls/SKILL.md) | Common methodological mistakes and how to avoid them |
| [clinical-research-analysis-framework](clinical/clinical-research-analysis-framework/SKILL.md) | Guided statistical/ML analysis workflow with structured consultation and audit trails |
| [equiflow](clinical/equiflow/SKILL.md) | Equity-focused cohort flow diagrams with SMD bias detection (Ellen 2024) |

## System Skills

### Data Structure

| Skill | Description |
|-------|-------------|
| [mimic-table-relationships](system/mimic-table-relationships/SKILL.md) | MIMIC-IV table relationships and join patterns |
| [mimic-eicu-mapping](system/mimic-eicu-mapping/SKILL.md) | Mapping between MIMIC-IV and eICU databases |

### M4 Framework

| Skill | Description |
|-------|-------------|
| [m4-api](system/m4-api/SKILL.md) | Python API for M4 clinical data queries |
| [m4-display](system/m4-display/SKILL.md) | Display server API for presenting results to researchers |
| [m4-research](system/m4-research/SKILL.md) | Structured clinical research workflow and protocol drafting |
| [create-m4-skill](system/create-m4-skill/SKILL.md) | Guide for creating new M4 skills |

---

## Gaps and Future Work

### Concepts Not Yet Extracted

The following valuable concepts exist in the source repositories but were not extracted:

1. **APACHE-II Score**: Older scoring system, still used in some contexts
2. **Ventilation Duration**: Time on mechanical ventilation
3. **Antibiotic Classification**: Categorization by class/spectrum
4. **MELD Score**: Model for End-Stage Liver Disease
5. **CRRT Concepts**: Continuous renal replacement therapy details
6. **Code Status**: DNR/DNI documentation

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

1. **Dataset-Agnostic Design**: Skills document concepts, not dataset-specific implementations. Dataset-specific SQL lives in each skill's `scripts/` subdirectory.

2. **Pre-computed Tables**: Most clinical skills reference pre-computed derived tables in `mimiciv_derived` schema. These are available on BigQuery and can be regenerated locally via `m4 init-derived`.

3. **Script Files**: Full SQL implementations are in each skill's `scripts/` subdirectory, with separate files per dataset where applicable.

4. **Format Reference**: See [SKILL_FORMAT.md](SKILL_FORMAT.md) for the canonical skill structure specification.

---

## References

- MIMIC-IV: https://mimic.mit.edu/docs/iv/
- eICU: https://eicu-crd.mit.edu/
- mimic-code: https://github.com/MIT-LCP/mimic-code
- eicu-code: https://github.com/MIT-LCP/eicu-code
- Agent Skills Standard: https://agentskills.io
