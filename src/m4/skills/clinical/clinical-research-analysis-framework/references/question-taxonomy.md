# Question Taxonomy

## Overview

The type of research question determines the appropriate analytical approach. Misclassifying a question leads to methods that don't answer what you actually want to know.

---

## Primary Question Types

### 1. Prediction

**"Can we accurately forecast outcome Y given information X?"**

- Goal: Maximize predictive accuracy for new, unseen cases
- Focus: Model performance (discrimination, calibration)
- Coefficients: Not the primary interest; may be uninterpretable
- Causation: Not claimed or required

**Examples:**
- "Can we predict ICU mortality at admission?"
- "Which patients will develop AKI in the next 24 hours?"
- "What is the risk of readmission for this patient?"

**Appropriate methods:** Logistic regression, random forest, gradient boosting, neural networks, penalized regression

**Key considerations:**
- Features must be available at prediction time (no future information leakage)
- Validation on truly held-out data is essential
- Calibration matters for clinical use, not just discrimination

---

### 2. Inference (Association)

**"Is X associated with Y, accounting for confounders?"**

- Goal: Estimate the relationship between exposure and outcome
- Focus: Effect size, confidence interval, statistical significance
- Coefficients: Primary interest; must be interpretable
- Causation: Claimed only with strong design (RCT, quasi-experimental)

**Examples:**
- "Is vasopressor choice associated with mortality?"
- "Do patients with diabetes have longer ICU stays?"
- "Is early mobilization associated with reduced delirium?"

**Appropriate methods:** Linear/logistic regression, Cox regression, GEE, mixed models

**Key considerations:**
- Confounder identification and adjustment
- Model specification (correct functional form)
- Effect modification / interaction

---

### 3. Causal Inference

**"Does X cause Y?"**

- Goal: Estimate the causal effect of an intervention
- Focus: What would happen if we changed X?
- Requires: Strong assumptions (exchangeability, positivity, consistency)
- Gold standard: Randomized controlled trial

**Examples:**
- "Does early intubation reduce mortality compared to delayed intubation?"
- "What is the effect of a restrictive transfusion strategy on outcomes?"

**Appropriate methods:** IPTW, propensity score matching, instrumental variables, difference-in-differences, regression discontinuity

**Key considerations:**
- Causal assumptions must be explicitly stated and defended
- Unmeasured confounding is always a threat in observational data
- Sensitivity analyses for violations are essential

---

### 4. Description

**"What is the distribution/frequency of X?"**

- Goal: Characterize a population or phenomenon
- Focus: Summary statistics, patterns, trends
- No exposure-outcome relationship tested

**Examples:**
- "What is the 30-day mortality rate in sepsis patients?"
- "How has ICU length of stay changed over time?"
- "What are the most common diagnoses in our cohort?"

**Appropriate methods:** Descriptive statistics, data visualization, trend analysis

**Key considerations:**
- Clearly define the population
- Report variability (SD, IQR, range), not just central tendency
- Consider selection bias in who enters the cohort

---

### 5. Clustering / Subgroup Discovery

**"Are there natural subgroups within this population?"**

- Goal: Identify latent structure or phenotypes
- Focus: Group membership, cluster characteristics
- Unsupervised: No predefined outcome

**Examples:**
- "Are there distinct sepsis phenotypes?"
- "Can we identify patient subgroups with different treatment responses?"

**Appropriate methods:** K-means, hierarchical clustering, latent class analysis, Gaussian mixture models

**Key considerations:**
- Cluster validity (internal and external)
- Clinical interpretability of clusters
- Stability across samples

---

## Secondary Distinctions

### Exploratory vs. Confirmatory

| Aspect | Exploratory | Confirmatory |
|--------|-------------|--------------|
| Hypothesis | Generated from data | Pre-specified |
| Multiple testing | Expected | Must be controlled |
| Reporting | All findings | Primary outcome focus |
| Replication | Needed | Is the replication |

### Cross-sectional vs. Longitudinal

| Aspect | Cross-sectional | Longitudinal |
|--------|-----------------|--------------|
| Timepoints | Single | Multiple |
| Causation | Cannot establish temporal order | Can establish temporal sequence |
| Analysis | Standard regression | Mixed models, GEE, survival |

### Time-to-Event vs. Binary/Continuous

| Outcome Type | Characteristics | Methods |
|--------------|-----------------|---------|
| Binary | Yes/no at fixed time | Logistic regression, chi-square |
| Continuous | Measured value | Linear regression, t-test, ANOVA |
| Time-to-event | When did it happen? + censoring | Cox, Kaplan-Meier, competing risks |
| Count | Number of events | Poisson, negative binomial |

---

## Decision Aid: What Type is My Question?

```
START: What do you want to learn?
│
├─ "How well can we forecast Y?"
│   └─ → PREDICTION
│
├─ "Is X related to Y?"
│   ├─ "...and I want to claim X causes Y"
│   │   └─ → CAUSAL INFERENCE (requires strong assumptions)
│   └─ "...adjusting for confounders"
│       └─ → INFERENCE (association)
│
├─ "What does Y look like in this population?"
│   └─ → DESCRIPTION
│
└─ "Are there natural groups in my data?"
    └─ → CLUSTERING
```

---

## Common Misclassifications

### Prediction disguised as inference
- **Red flag:** "We found that feature X has high importance in predicting Y, therefore X is associated with Y"
- **Problem:** Variable importance ≠ causal effect; prediction models optimize for accuracy, not interpretability

### Association claimed as causation
- **Red flag:** "Patients who received treatment X had lower mortality, so X reduces mortality"
- **Problem:** Without randomization or causal methods, confounding by indication is likely

### Description without context
- **Red flag:** "Mortality was 25% in our cohort"
- **Problem:** Without comparison group or benchmark, the number is uninterpretable

---

## Implications for Analysis Planning

| Question Type | What to prioritize |
|---------------|-------------------|
| Prediction | Validation strategy, calibration, feature engineering |
| Inference | Confounder identification, model specification, CIs |
| Causal | Assumptions, sensitivity analysis, design elements |
| Description | Population definition, complete reporting |
| Clustering | Validity metrics, interpretability, stability |
