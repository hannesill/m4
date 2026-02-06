# Study Design Checklist

## Overview

Good analysis starts with good study design. This checklist ensures key design elements are addressed before analysis begins.

---

## Research Question Formulation

### PICO(T) Framework

| Component | Question | Example |
|-----------|----------|---------|
| **P**opulation | Who are we studying? | Adult ICU patients with sepsis |
| **I**ntervention/Exposure | What exposure or treatment? | Early vs. late vasopressor initiation |
| **C**omparison | Compared to what? | Standard care, alternative treatment, no exposure |
| **O**utcome | What are we measuring? | 28-day mortality |
| **T**ime | Over what period? | Within first 24 hours of ICU admission |

### Question Checklist

- [ ] Is the question clearly stated in plain language?
- [ ] Is it answerable with available data?
- [ ] Is it clinically meaningful?
- [ ] Is it novel or confirmatory of prior work?

---

## Cohort Definition

### Inclusion Criteria

Define who enters the study:

| Criterion Type | Examples |
|----------------|----------|
| Diagnosis | Sepsis-3 criteria, ICD codes, clinical definition |
| Setting | ICU admission, specific unit type |
| Age | Adults (≥18), specific range |
| Time | Admission within study period |
| Data quality | Required variables available |

### Exclusion Criteria

Define who is removed (with justification):

| Criterion | Justification |
|-----------|---------------|
| Age <18 | Pediatric physiology differs |
| LOS <24h | Insufficient observation time |
| Readmission | Avoid correlated observations |
| Missing outcome | Cannot assess endpoint |
| Prior exposure | Clean exposure window needed |
| Comfort care only | Different treatment goals |

### Documentation Requirements

For each criterion, document:
- Exact definition (codes, thresholds, timing)
- Number excluded at each step
- Justify each exclusion

**CONSORT-style flow diagram recommended.**

---

## Unit of Analysis

### Options

| Unit | When to Use | Watch For |
|------|-------------|-----------|
| Patient | One observation per person | Multiple admissions → choose first, last, or random |
| Admission | One observation per hospitalization | Same patient multiple times → clustering |
| ICU stay | One observation per ICU episode | Transfers between units |
| Patient-day | Time-varying exposures | Autocorrelation |

### Key Decision: Multiple Events per Patient

If patients can have multiple admissions/stays:

| Approach | Pros | Cons |
|----------|------|------|
| First only | Simple, independent | Loses data, selection bias |
| Last only | May capture sickest | Selection bias |
| Random one | Unbiased selection | Loses data |
| All (clustered) | Uses all data | Must model clustering |
| Index event (defined criteria) | Clinically meaningful | Requires clear definition |

---

## Time-Zero and Follow-Up

### Time-Zero Definition

Time-zero is the moment when:
- Follow-up begins
- Patient becomes "at risk" for outcome
- Exposure status should be determined (or treatment assigned)

| Common Choices | Appropriate When |
|----------------|------------------|
| Hospital admission | Studying hospital-wide exposures |
| ICU admission | ICU-specific questions |
| Diagnosis time | Studying disease course |
| Treatment initiation | Caution: immortal time bias if not universal |
| Fixed landmark (e.g., day 3) | Ensuring minimum exposure time |

### Follow-Up Period

- **Start:** Time-zero
- **End:** Outcome, death, discharge, loss to follow-up, or administrative censoring
- **Fixed horizon:** e.g., 30 days, 90 days, hospital stay

### Censoring

Define what ends follow-up without outcome:
- Discharge alive
- Transfer to another facility
- End of study period
- Loss of data availability

**Consider:** Is censoring informative? (Related to outcome?)

---

## Exposure / Predictor Definition

### For Observational Studies

| Consideration | Question |
|---------------|----------|
| Binary vs. continuous | Is exposure yes/no or a dose/level? |
| Timing | When was exposure measured? Before outcome possible? |
| Duration | Single point or cumulative? |
| Variability | Does exposure change over time? |

### Avoiding Data Leakage

For prediction models:
- Features must be available at prediction time
- Cannot use information that comes after time-zero
- Cannot use information that requires knowing the outcome

**Red flags:**
- Using discharge diagnoses to predict at admission
- Using lab values from after the event
- Using length of stay to predict mortality

---

## Outcome Definition

### Characteristics of Good Outcomes

| Property | Description |
|----------|-------------|
| Clinically meaningful | Matters to patients or clinicians |
| Objective | Clearly measurable, reproducible |
| Available | Ascertainable in the data |
| Appropriate timing | Sufficient follow-up to observe |

### Common ICU Outcomes

| Outcome | Type | Definition Considerations |
|---------|------|---------------------------|
| Mortality | Binary / Time-to-event | ICU, hospital, 28-day, 90-day? |
| Length of stay | Continuous / Time-to-event | ICU or hospital? Censor deaths? |
| Readmission | Binary / Time-to-event | To ICU? To hospital? Time window? |
| AKI | Binary / Ordinal | KDIGO stage? Timing relative to exposure? |
| Ventilator-free days | Count (composite) | Accounts for death as competing event |
| Organ dysfunction | Continuous | SOFA score, specific organ scores |

### Competing Events

Some outcomes have competing events:
- Studying ICU discharge → death is competing event
- Studying readmission → death prevents readmission

Options:
- Composite outcome (either event)
- Competing risk analysis (Fine-Gray)
- Cause-specific analysis

---

## Confounding

### Identifying Confounders

A confounder is a variable that:
1. Is associated with the exposure
2. Is associated with the outcome
3. Is NOT on the causal pathway between exposure and outcome

### Common Confounder Categories in ICU Research

| Category | Examples |
|----------|----------|
| Demographics | Age, sex, race |
| Comorbidities | Charlson, Elixhauser, specific diseases |
| Acute severity | APACHE, SOFA, SAPS |
| Admission characteristics | Admission source, admission type |
| Process measures | Time of day, day of week |

### Adjustment Strategies

| Strategy | Description | Assumption |
|----------|-------------|------------|
| Multivariable regression | Include confounders as covariates | Correct model specification |
| Propensity score matching | Match on PS | Sufficient overlap, balance achieved |
| IPTW | Weight by inverse PS | Sufficient overlap, correct PS model |
| Stratification | Analyze within strata | Sufficient data per stratum |

### Unmeasured Confounding

**Problem:** Can never prove no unmeasured confounding in observational data.

**Mitigation:**
- Be explicit about assumed confounders
- Use negative control outcomes
- Quantitative bias analysis (E-value)
- Discuss plausible unmeasured confounders

---

## Sensitivity Analysis Planning

### Pre-Specified Sensitivity Analyses

Plan before looking at data:

| Type | Purpose | Example |
|------|---------|---------|
| Different cohort | Check robustness to inclusion criteria | Include vs. exclude missing data |
| Different outcome | Check outcome definition sensitivity | 28-day vs. hospital mortality |
| Different model | Check model specification | Add/remove covariates |
| Different method | Check analytic approach | Propensity matching vs. IPTW |
| Subgroup | Check effect modification | Stratify by severity |

### Bias Quantification

For causal inference:
- **E-value:** How strong would unmeasured confounding need to be to nullify the result?
- **Probabilistic bias analysis:** Model uncertainty about bias

---

## Power and Sample Size

### Pre-Study Considerations

Before starting, determine:
- Minimum clinically important effect size
- Expected event rate
- Required sample size for adequate power

### Rules of Thumb

| Analysis | Minimum |
|----------|---------|
| Regression | 10-20 observations per predictor |
| Logistic regression | 10-20 events per predictor |
| Cox regression | 10-20 events per predictor |
| Propensity matching | Sufficient overlap for matching |

### What If Underpowered?

- Acknowledge limitation
- Report effect size and CI (even if non-significant)
- Consider as hypothesis-generating

---

## Reproducibility Checklist

Before finalizing design, ensure:

- [ ] **Research question** is clearly stated (PICO format)
- [ ] **Population** is defined with explicit inclusion/exclusion
- [ ] **Unit of analysis** is specified
- [ ] **Time-zero** is clearly defined
- [ ] **Follow-up** period is specified
- [ ] **Outcome** is objectively defined
- [ ] **Exposure/predictors** are defined and temporally appropriate
- [ ] **Confounders** are identified with adjustment plan
- [ ] **Missing data** handling is planned
- [ ] **Sensitivity analyses** are pre-specified
- [ ] **Sample size** is adequate for planned analyses

---

## Common Design Pitfalls

| Pitfall | Problem | Fix |
|---------|---------|-----|
| Vague inclusion criteria | Unreproducible cohort | Use explicit codes/thresholds |
| Time-zero after exposure | Immortal time bias | Align time-zero with eligibility |
| Outcome available at baseline | Prevalent vs. incident confusion | Exclude baseline cases |
| Future information as predictor | Data leakage | Restrict to pre-time-zero data |
| Ignoring clustering | Wrong standard errors | Model correlation structure |
| Post-hoc subgroups | Inflated false positive rate | Pre-specify or label exploratory |
