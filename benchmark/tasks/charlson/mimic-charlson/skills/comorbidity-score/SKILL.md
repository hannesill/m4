---
name: comorbidity-score
description: Calculate Charlson Comorbidity Index (CCI) and Elixhauser Comorbidity Index for hospital admissions. Use for risk adjustment, mortality prediction, case-mix analysis, or comparing comorbidity burden across patient populations.
tier: validated
category: clinical
---

# Comorbidity Scores

Two validated comorbidity indices for risk adjustment: Charlson Comorbidity Index (CCI) and Elixhauser Comorbidity Index. Both are most commonly implemented using Quan 2005 ICD-9/ICD-10 coding algorithms, though other mapping algorithms exist.

## When to Use This Skill

- Risk adjustment in outcome studies
- Mortality prediction models
- Case-mix comparison across cohorts
- Matching/stratification by comorbidity burden
- Resource utilization analysis

## Index Comparison

| Aspect | Charlson | Elixhauser |
|--------|----------|------------|
| Categories | 17 conditions | 31 conditions |
| Output | Weighted score (0-33+) | Binary flags ± weighted score |
| Primary use | Mortality prediction | Risk adjustment, resource use |
| Age component | Included (0-4 points) | Not included |
| Weighting | Original 1987 fixed weights | Multiple options (unweighted, van Walraven) |

**Charlson:** Single summary score; simpler models; established benchmarks.

**Elixhauser:** Granular profiles; flexible modeling (flags as covariates); captures conditions not in Charlson (obesity, depression, substance abuse).

## Weighting Systems

### Charlson Original Weights (1987)

| Weight | Conditions |
|--------|------------|
| 1 | MI, CHF, PVD, CVD, Dementia, COPD, Rheumatic, PUD, Mild liver, DM w/o CC |
| 2 | DM w/ CC, Paraplegia, Renal disease, Cancer (non-metastatic) |
| 3 | Moderate/severe liver disease |
| 6 | Metastatic cancer, AIDS |

### Charlson Age Score

| Age | Points |
|-----|--------|
| ≤50 | 0 |
| 51-60 | 1 |
| 61-70 | 2 |
| 71-80 | 3 |
| >80 | 4 |

### Elixhauser van Walraven Weights (selected)

| Weight | Conditions |
|--------|------------|
| +12 | Metastatic cancer |
| +11 | Liver disease |
| +9 | Lymphoma |
| +7 | CHF, Paralysis |
| +6 | Other neurological, Weight loss |
| +5 | Cardiac arrhythmias, Renal failure, Fluid/electrolyte |
| +4 | Pulmonary circulation, Solid tumor |
| +3 | Chronic pulmonary, Coagulopathy |
| +2 | Peripheral vascular |
| -1 | Valvular disease |
| -2 | Blood loss anemia, Deficiency anemias |
| -3 | Depression |
| -4 | Obesity |
| -7 | Drug abuse |
| 0 | HTN, DM, Hypothyroid, PUD, AIDS, RA, Alcohol, Psychoses |

## Critical Implementation Notes

1. **Hierarchy Rules** (applies to all implementations):
   - Liver: severe overrides mild
   - Diabetes: complicated overrides uncomplicated
   - Cancer: metastatic overrides solid tumor

2. **ICD Code Algorithms**: Quan 2005 provides the most widely used and validated ICD-9-CM and ICD-10-CM mappings for both indices. Other algorithms exist (e.g., Deyo 1992 for Charlson, AHRQ for Elixhauser) and may be appropriate depending on the study context.

3. **Primary Diagnosis Exclusion**: Elixhauser methodology excludes the primary diagnosis from comorbidity flagging (comorbidities should be conditions *other than* the reason for admission). Charlson typically includes all diagnoses. In administrative databases where the "primary" diagnosis field may not reflect the clinically principal diagnosis, this exclusion should be interpreted with caution.

## Dataset Availability

### MIMIC-IV

**Charlson** is available as a pre-computed derived table. Materialize with:

```bash
m4 init-derived mimic-iv          # All derived tables including charlson
```

The derived `mimiciv_derived.charlson` table provides `charlson_comorbidity_index` (total weighted score), `age_score`, and binary flags for all 17 conditions.

BigQuery users already have this table via `physionet-data.mimiciv_derived.charlson` without running `init-derived`.

**Elixhauser** is **not** in the derived tables or BigQuery. The SQL was adapted from the mimic-code MIMIC-III Elixhauser script with ICD-10-CM mappings added from Quan 2005.

**MIMIC-IV implementation details:**
- **Charlson ICD Mappings**: Uses MIT-LCP mimic-code mappings (Quan 2005).
- **Elixhauser ICD Mappings**: ICD-10-CM mappings derived from Quan 2005 original paper, as MIT-LCP provides ICD-9-CM only.
- **Diabetes Classification**: Quan 2005 classifies E10.6 (diabetic foot ulcer) as "uncomplicated." Clinically debatable, but implementations follow Quan strictly.
- **Primary Diagnosis Handling**: Charlson includes all diagnoses. Elixhauser excludes `seq_num = 1` per the original methodology. However, MIMIC's `seq_num` does not reliably indicate the clinically principal diagnosis — it reflects billing order, not clinical primacy. This is a known limitation; alternative approaches include filtering by DRG or accepting the imprecision.
- **ICD Version Transition**: MIMIC-IV spans ICD-9 (pre-Oct 2015) and ICD-10 (post-Oct 2015). Both versions mapped.

See `scripts/mimic-iv/` for both Charlson and Elixhauser implementations.

### eICU

Comorbidity indices are **not pre-computed** in eICU. Three data sources are available, each with trade-offs:

| Source | Coverage | Reliability | Notes |
|--------|----------|-------------|-------|
| `diagnosis.icd9code` | Full (Charlson 17, Elixhauser 31) | Varies by site | Same Quan 2005 ICD-9 algorithms; ICD-9 only (pre-ICD-10 transition) |
| `pasthistory` | Partial (~12-14 Charlson categories) | More consistent | Structured text (e.g., "CHF", "COPD"); requires mapping table; less granular (cannot distinguish mild vs severe liver, DM with vs without CC) |
| `apacheapsvar` | Limited (~7 conditions) | High (required for APACHE IV) | AIDS, hepatic failure, immunosuppression, leukemia, lymphoma, metastatic cancer, cirrhosis |

**eICU limitations:**
- **ICD completeness varies by site**: `icd9code` population ranges from near-complete to sparse across the 208 hospitals. A site-level completeness check (proportion of admissions with at least one ICD code) is recommended before using the ICD-only approach.
- **No ICD-10 codes**: eICU data (2014-2015) predates the ICD-10 transition. Only the ICD-9 portion of Quan 2005 algorithms applies.
- **Primary diagnosis exclusion**: The Elixhauser `seq_num != 1` exclusion is even less reliable in eICU than MIMIC, as diagnosis ordering conventions vary across sites.
- **Hybrid approach**: Combining ICD-9 codes with `pasthistory` text matching and `apacheapsvar` flags may improve sensitivity but adds complexity and requires clinical validation of the text-to-category mapping.

An eICU script is not yet available.

## Example: CCI Distribution

```sql
SELECT
    charlson_comorbidity_index AS cci,
    COUNT(*) AS n_admissions,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM mimiciv_derived.charlson
GROUP BY cci
ORDER BY cci;
```

## Example: Elixhauser Flags for Regression

```sql
SELECT
    e.hadm_id,
    e.congestive_heart_failure,
    e.diabetes_complicated,
    e.renal_failure,
    e.metastatic_cancer,
    CASE WHEN a.deathtime IS NOT NULL THEN 1 ELSE 0 END AS in_hospital_death
FROM mimiciv_derived.elixhauser e
JOIN mimiciv_hosp.admissions a USING (hadm_id);
```

## Example: High-Risk Identification

```sql
SELECT c.subject_id, c.hadm_id, c.charlson_comorbidity_index,
       e.congestive_heart_failure, e.renal_failure, e.metastatic_cancer
FROM mimiciv_derived.charlson c
JOIN mimiciv_derived.elixhauser e USING (hadm_id)
WHERE c.charlson_comorbidity_index >= 5;
```

## References

- Charlson ME, et al. "A new method of classifying prognostic comorbidity." J Chronic Dis. 1987;40(5):373-83.
- Elixhauser A, et al. "Comorbidity measures for use with administrative data." Med Care. 1998;36(1):8-27.
- Quan H, et al. "Coding algorithms for defining comorbidities in ICD-9-CM and ICD-10 administrative data." Med Care. 2005;43(11):1130-9.
- van Walraven C, et al. "A modification of the Elixhauser comorbidity measures into a point system for hospital death." Med Care. 2009;47(6):626-33.
