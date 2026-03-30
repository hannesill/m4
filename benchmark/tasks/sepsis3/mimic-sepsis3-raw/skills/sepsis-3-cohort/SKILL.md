---
name: sepsis-3-cohort
description: Identify Sepsis-3 patients using the consensus definition (SOFA >= 2 + suspected infection). Use for sepsis cohort studies, outcome research, or quality metrics.
tier: validated
category: clinical
---

# Sepsis-3 Cohort Identification

The Sepsis-3 definition (Singer et al. 2016) identifies sepsis as **life-threatening organ dysfunction caused by a dysregulated host response to infection**. This is a conceptual definition; the operationalization is a proxy:

- **Suspected infection** (antibiotics + culture within time window) AND
- **SOFA score >= 2** (within 48h before to 24h after suspected infection)

### Related Sepsis-3 Constructs

- **qSOFA** (quick SOFA): Bedside screening tool for patients outside the ICU (RR >= 22, altered mentation, SBP <= 100). Not a diagnostic criterion — meant to prompt further assessment. Sensitivity is limited; a negative qSOFA does not rule out sepsis.
- **Septic Shock**: Sepsis with vasopressor requirement to maintain MAP >= 65 mmHg AND lactate > 2 mmol/L despite adequate fluid resuscitation. Carries substantially higher mortality than sepsis alone.

## When to Use This Skill

- Creating sepsis patient cohorts for research
- Sepsis outcome studies
- Quality improvement and benchmarking
- Comparing sepsis populations across studies
- Validating machine learning models on sepsis data

## Sepsis-3 Definition Details

### Suspected Infection Criteria
A patient has suspected infection when:
1. **Antibiotics are administered** (systemic, excluding topical) AND
2. **Cultures are obtained** within a time window:
   - Culture within 72h BEFORE antibiotic, OR
   - Culture within 24h AFTER antibiotic

See [suspicion-of-infection](../suspicion-of-infection/SKILL.md) for detailed matching logic.

### SOFA Criteria
SOFA >= 2 points, where SOFA is calculated using 24-hour worst values:
- Must occur within 48h before to 24h after suspected infection time

See [sofa-score](../sofa-score/SKILL.md) for SOFA component details.

### Baseline SOFA Assumption
**Baseline SOFA is assumed to be 0** for all patients. The true Sepsis-3 definition requires an acute *change* of >= 2 points from baseline, but pre-hospital baseline organ function is rarely available in retrospective data. This assumption may over-classify patients with chronic organ dysfunction (e.g., chronic kidney disease, cirrhosis) as having sepsis.

## Critical Implementation Notes

1. **ICU-Only by Design**: SOFA requires ICU-level monitoring data (vasopressors, mechanical ventilation status, hourly urine output). This inherently limits Sepsis-3 operationalization to ICU stays. ED sepsis and floor sepsis are not captured.

2. **Time of Sepsis Onset**: Defined as the earliest `suspected_infection_time`. This is typically the culture time if culture preceded antibiotics, or the antibiotic time if antibiotics came first.

3. **First Event**: A patient may have multiple antibiotic-culture pairs. Implementations typically return the first (earliest) suspected infection event per ICU stay.

4. **Culture Positivity Not Required**: Sepsis-3 does not require positive cultures. Clinical suspicion (antibiotics ordered + cultures sent) is sufficient.

5. **SOFA Time Window**: The [-48h, +24h] window around suspected infection time is the Seymour et al. operationalization. Some studies use narrower windows.

## General Limitations

1. **Baseline SOFA Unknown**: Assumes baseline SOFA = 0. Patients with pre-existing organ dysfunction (CKD, cirrhosis, chronic respiratory failure) may be over-classified as septic.

2. **ICU-Only**: Cannot identify ED sepsis, floor sepsis, or sepsis present on ICU admission. This systematically excludes patients who die before ICU transfer or are managed on the floor.

3. **Antibiotic-Dependent**: Requires antibiotic administration — may miss untreated infections or patients who die before antibiotics are started.

4. **Culture-Dependent**: Requires cultures obtained — may miss clinically diagnosed infections where cultures were not sent (e.g., empiric treatment of pneumonia without sputum culture).

5. **Does Not Capture Septic Shock**: The sepsis3 derived table identifies sepsis only. Septic shock identification requires additional vasopressor and lactate criteria.

## Dataset Availability

### MIMIC-IV

Sepsis-3 is available as a pre-computed derived table. Materialize with:

```bash
m4 init-derived mimic-iv          # All derived tables including sepsis3
```

```sql
SELECT
    subject_id,
    stay_id,
    antibiotic_time,
    culture_time,
    suspected_infection_time,
    sofa_time,
    sofa_score,
    respiration, coagulation, liver, cardiovascular, cns, renal,
    sepsis3
FROM mimiciv_derived.sepsis3;
```

BigQuery users already have this table via `physionet-data.mimiciv_derived.sepsis3` without running `init-derived`.

**MIMIC-IV implementation details:**
- The derived tables originate from the [MIT-LCP mimic-code](https://github.com/MIT-LCP/mimic-code) repository. The full SQL query is in `scripts/mimic-iv.sql`.
- Joins `mimiciv_derived.suspicion_of_infection` (infection component) with `mimiciv_derived.sofa` (organ dysfunction component).
- Returns one row per ICU stay (earliest suspected infection event with SOFA >= 2).
- The `sepsis3` boolean flag is TRUE when both criteria are met.
- SOFA uses 24-hour rolling worst values (`sofa_24hours` from derived SOFA table).

**MIMIC-IV limitations:**
- Depends on upstream derived tables (`sofa`, `suspicion_of_infection`). Any limitations in those tables propagate here.
- SOFA components draw from ICU charting tables — onset timing is relative to ICU admission, not hospital admission.

### eICU

Sepsis-3 is **not pre-computed** in eICU. Building it requires constructing both components from raw tables:

**Suspected infection component:**

| eICU Table | Columns | Maps to MIMIC |
|------------|---------|---------------|
| `medication` | `drugname`, `routeadmin`, `drugstartoffset` | `prescriptions` / derived `antibiotic` |
| `microlab` | `culturetakenoffset`, `culturesite`, `organism` | `microbiologyevents` |

**SOFA component sources:**

| SOFA Component | eICU Table | Column(s) |
|----------------|-----------|-----------|
| Respiration (PaO2/FiO2) | `lab` | labname = `'paO2'`, `'FiO2'` |
| Coagulation (Platelets) | `lab` | labname = `'platelets x 1000'` |
| Liver (Bilirubin) | `lab` | labname = `'total bilirubin'` |
| Cardiovascular (MAP) | `vitalperiodic` | `systemicmean`; also `vitalaperiodic.noninvasivemean` |
| Cardiovascular (Vasopressors) | `infusiondrug` | `drugname`, `infusionrate` |
| CNS (GCS) | `nursecharting` | `nursingchartcelltypevalname` (Eyes, Motor, Verbal) |
| Renal (Creatinine) | `lab` | labname = `'creatinine'` |
| Renal (Urine Output) | `intakeoutput` | `celllabel` (filter for urine-related entries) |

**eICU limitations:**
- **Center variability in missingness**: Charting practices, medication naming, and data completeness vary substantially across the 208 hospitals. Missingness is not random — it correlates with hospital size, teaching status, and EHR system. This affects both infection identification and SOFA computation.
- **Medication naming**: `medication.drugname` is free-text and varies across sites. The same antibiotic may appear as "Vancomycin", "VANCOMYCIN", "vancomycin 1g IV", etc. Antibiotic identification requires extensive text matching.
- **Culture timing**: `microlab.culturetakenoffset` provides timing in minutes from unit admission. The antibiotic-culture pairing logic must be rebuilt for the eICU offset-based time system.
- **SOFA computation**: Each component comes from a different table with different naming conventions. The eicu-code repository provides pivoted tables (`pivoted_lab`, `pivoted_bg`, `pivoted_score`, `pivoted_uo`) that can simplify extraction.
- **APACHE IV alternative**: eICU provides pre-computed APACHE IV scores in `apachepatientresult`, which includes a severity/mortality prediction. While not the same as Sepsis-3, APACHE IV combined with an infection flag may serve as a pragmatic alternative for eICU sepsis studies.

An eICU script is not yet available.

## Example: Identify Sepsis Cohort

```sql
SELECT
    s.stay_id,
    ie.subject_id,
    ie.hadm_id,
    s.suspected_infection_time AS sepsis_onset,
    s.sofa_score,
    adm.hospital_expire_flag AS mortality
FROM mimiciv_derived.sepsis3 s
INNER JOIN mimiciv_icu.icustays ie ON s.stay_id = ie.stay_id
INNER JOIN mimiciv_hosp.admissions adm ON ie.hadm_id = adm.hadm_id
WHERE s.sepsis3 = TRUE;
```

## Example: Sepsis Severity Distribution

```sql
SELECT
    CASE
        WHEN sofa_score < 5 THEN 'Mild (SOFA 2-4)'
        WHEN sofa_score < 10 THEN 'Moderate (SOFA 5-9)'
        WHEN sofa_score < 15 THEN 'Severe (SOFA 10-14)'
        ELSE 'Very Severe (SOFA 15+)'
    END AS severity,
    COUNT(*) AS n_patients,
    ROUND(AVG(adm.hospital_expire_flag), 3) AS mortality_rate
FROM mimiciv_derived.sepsis3 s
INNER JOIN mimiciv_icu.icustays ie ON s.stay_id = ie.stay_id
INNER JOIN mimiciv_hosp.admissions adm ON ie.hadm_id = adm.hadm_id
WHERE s.sepsis3 = TRUE
GROUP BY 1
ORDER BY 1;
```

## Related Skills

- [suspicion-of-infection](../suspicion-of-infection/SKILL.md) — Infection component (antibiotic + culture timing)
- [sofa-score](../sofa-score/SKILL.md) — Organ dysfunction component
- [sirs-criteria](../sirs-criteria/SKILL.md) — Historical pre-Sepsis-3 inflammatory response criteria

## References

- Singer M et al. "The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3)." JAMA. 2016;315(8):801-810.
- Seymour CW et al. "Assessment of Clinical Criteria for Sepsis." JAMA. 2016;315(8):762-774.
- Shankar-Hari M et al. "Developing a New Definition and Assessing New Clinical Criteria for Septic Shock." JAMA. 2016;315(8):775-787.
