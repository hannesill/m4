# EHR Data Considerations

## Overview

Electronic Health Record (EHR) data from MIMIC, eICU, and similar databases present unique methodological challenges. This reference covers pitfalls specific to clinical database research.

---

## Selection Bias

### ICU Selection Bias (Survivorship Bias)

**Problem:** Patients in the ICU are a highly selected population.

- They survived long enough to be admitted to the ICU
- Someone decided they needed ICU care
- They had access to ICU beds

**Implications:**
- Findings may not generalize to non-ICU patients
- Comparing ICU patients to general population is problematic
- "Sicker" patients in ICU may actually be more salvageable (otherwise why admit?)

**Mitigation:**
- Clearly define target population
- Don't generalize beyond ICU patients
- Consider severity adjustment (APACHE, SOFA)

---

### Single-Center Bias (MIMIC)

**Problem:** MIMIC is from Beth Israel Deaconess Medical Center in Boston.

- Academic tertiary care center
- Specific patient demographics (Boston area)
- Specific practice patterns
- May not represent other hospitals

**Implications:**
- External validity is unknown
- Validation on other datasets essential before clinical deployment

**Mitigation:**
- Validate on eICU (multi-center) or other databases
- Report center characteristics
- Acknowledge generalizability limitations

---

### Temporal Selection

**Problem:** Who gets included depends on data availability period.

- MIMIC-IV: 2008-2019
- Practice patterns changed over this period
- ICD-9 → ICD-10 transition (Oct 2015)
- Patients who died early vs. late in the study period differ

**Mitigation:**
- Consider temporal validation (train early, test late)
- Check for secular trends
- Stratify by era if appropriate

---

## Time-Related Biases

### Immortal Time Bias

**Problem:** Time between cohort entry and treatment initiation during which the outcome cannot occur.

**Classic example:** "Patients who received Drug X had lower mortality"
- But to receive Drug X, you had to survive long enough to get it
- Deaths in the "immortal time" are misclassified

**Detection:**
- Is there a gap between time-zero and treatment?
- Could outcomes occur during this gap?

**Mitigation:**
- Align time-zero with treatment decision point
- Landmark analysis (start follow-up at fixed time)
- Time-varying exposure models

---

### Time-Zero Definition

**Problem:** When does follow-up start?

| Choice | Issue |
|--------|-------|
| Hospital admission | May precede ICU; different risk profile |
| ICU admission | Most common; but which admission for readmits? |
| Treatment initiation | Immortal time if not everyone treated immediately |
| Diagnosis time | Variable latency to diagnosis |

**Best practice:**
- Time-zero should be the point of decision/eligibility
- All patients should be "at risk" for outcome at time-zero
- Document and justify clearly

---

### Lead Time Bias

**Problem:** Earlier detection ≠ longer survival.

If an exposure is associated with earlier testing/diagnosis:
- Patients appear to survive longer
- But they just knew about their condition longer

**Mitigation:**
- Use clinically meaningful endpoints
- Landmark analysis
- Consider time from symptom onset, not diagnosis

---

## Missing Data

### Missingness Is Informative in EHR

**Key insight:** In clinical data, missingness is rarely random.

| Pattern | Likely Meaning |
|---------|----------------|
| Lab value missing | Clinician didn't think it was needed |
| Vital sign gap | Patient stable (or recorder busy) |
| Med never given | Not indicated (or contraindicated) |
| Note not written | Nothing concerning to document |

**Implications:**
- MCAR (missing completely at random) assumption usually wrong
- Complete case analysis may be biased
- Imputation must be done thoughtfully

---

### Handling Missing Data

| Approach | When Appropriate | Caution |
|----------|------------------|---------|
| Complete case | Truly MCAR (rare) | Loses power, may bias |
| Single imputation (mean, median) | Quick exploration | Underestimates variance |
| Multiple imputation | MAR plausible | Requires careful modeling |
| Indicator method | Missingness is meaningful | Only if theory supports |
| Model-based (mice, etc.) | MAR, complex patterns | Computationally intensive |

**For prediction models:**
- Missingness indicators can be features (missingness is information)
- Tree-based models can handle missing values natively

**For inference:**
- Multiple imputation preferred
- Sensitivity analysis under MNAR scenarios

---

### Common Missing Data Patterns in MIMIC/eICU

| Data Type | Typical Pattern | Notes |
|-----------|-----------------|-------|
| Labs | Ordered when clinically indicated | More missing = likely more stable |
| Vitals | Charted periodically | Gaps during transport, procedures |
| Medications | Documented when given | Absence ≈ not indicated |
| Notes | Written when events occur | Sparse = uneventful |
| Diagnoses (ICD) | Coded at discharge | Retrospective, billing-driven |

---

## Coding and Definition Issues

### ICD Code Transition

**Problem:** ICD-9-CM → ICD-10-CM on October 1, 2015.

- Codes are not 1:1 mappable
- Specificity changed (ICD-10 more granular)
- Same condition may be coded differently pre/post

**Mitigation:**
- Use validated crosswalk mappings
- Check consistency across eras
- Consider ICD-agnostic definitions (lab-based, clinical criteria)

---

### Diagnosis Timing

**Problem:** ICD codes are assigned at discharge, not in real-time.

- Codes reflect billing, not clinical reasoning during stay
- Cannot use discharge diagnoses to define who "had" a condition at admission
- Present-on-admission (POA) flag helps but is imperfect

**Implications for prediction:**
- Don't use discharge diagnoses as predictors at admission
- Use admission diagnoses (often limited) or prior history

---

### Medication Data Complexity

| Issue | Description |
|-------|-------------|
| Order vs. administration | Order ≠ given; use MAR for actual receipt |
| PRN medications | May be ordered but rarely given |
| Infusions | Rates change; need to model over time |
| Generic vs. brand | Same drug, different names |
| Units | mcg vs mg; mL/hr vs dose |

---

### Lab Value Interpretation

| Issue | Description |
|-------|-------------|
| Reference ranges | Vary by lab; not always provided |
| Critical values | May trigger repeated testing |
| Timing | First value? Worst value? Closest to event? |
| Multiple samples | Same timepoint may have multiple results |
| Units | Some values in different units (e.g., glucose mg/dL vs mmol/L) |

---

## Confounding in Observational Data

### Confounding by Indication

**Problem:** Treatments are given for reasons related to outcome.

Example: "Vasopressors associated with higher mortality"
- But vasopressors are given to sicker patients
- The indication (shock) causes both treatment and outcome

**Mitigation:**
- Careful confounder adjustment
- Propensity methods
- Consider indication directly
- Acknowledge limitations

---

### Severity Scores as Confounders

Common severity scores in ICU data:
- APACHE II/III/IV
- SOFA (Sequential Organ Failure Assessment)
- SAPS II/III
- Charlson/Elixhauser comorbidity indices

**Considerations:**
- Calculated at different timepoints (admission vs. first 24h)
- May include components on causal pathway (mediators)
- Adjust for, but don't over-adjust

---

## eICU-Specific Considerations

### Multi-Center Structure

**eICU:** 208 hospitals across the US, 2014-2015.

**Strengths:**
- Geographic diversity
- Allows site-level validation
- More generalizable than single-center

**Challenges:**
- Clustering by hospital (must account for)
- Variable data quality by site
- Different practice patterns

**Analysis considerations:**
- Mixed models or GEE with hospital as cluster
- Site-level random effects
- Consider site as stratification variable for validation

---

### Telehealth Context

eICU patients were monitored by telehealth ICU system.
- May differ from non-telehealth ICUs
- Additional monitoring may affect documentation patterns

---

## Reproducibility Considerations

### Version Control

MIMIC and eICU have multiple versions:
- MIMIC-III vs MIMIC-IV (different schemas, patients)
- Derived tables may change between releases

**Best practice:**
- Document exact version used
- Pin to specific derived table versions if possible
- Include data extraction date

---

### Cohort Definition Documentation

Always document:
- Inclusion criteria (with counts)
- Exclusion criteria (with counts at each step)
- Time period
- Unit of analysis
- Handling of multiple admissions per patient

---

## Checklist: EHR Data Quality Assessment

Before analysis, check:

- [ ] **Cohort:** Appropriate inclusion/exclusion applied?
- [ ] **Time-zero:** Clearly defined, appropriate for question?
- [ ] **Outcome:** Defined, measured consistently?
- [ ] **Predictors:** Available at prediction time? No leakage?
- [ ] **Missing data:** Patterns assessed? Handling strategy justified?
- [ ] **Confounding:** Key confounders identified? Adjustment plan?
- [ ] **Coding:** ICD version consistent? Definitions validated?
- [ ] **Clustering:** Patient/hospital clustering accounted for?
- [ ] **Temporality:** Secular trends checked? ICD transition handled?
- [ ] **Generalizability:** Limitations acknowledged?
