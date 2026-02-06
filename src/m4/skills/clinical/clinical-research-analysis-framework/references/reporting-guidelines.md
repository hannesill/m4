# Reporting Guidelines

## Overview

Reporting guidelines ensure transparent, complete, and reproducible research communication. Journals increasingly require adherence to specific guidelines. This reference covers guidelines most relevant to EHR-based clinical research.

---

## Which Guideline to Use?

| Study Type | Primary Guideline | Extension |
|------------|-------------------|-----------|
| Observational (cohort, case-control, cross-sectional) | STROBE | RECORD (for routinely collected data) |
| Prediction model development | TRIPOD | TRIPOD+AI (if ML/AI methods) |
| Prediction model validation | TRIPOD | - |
| Diagnostic accuracy | STARD | - |
| Randomized trial | CONSORT | - |
| Systematic review | PRISMA | - |
| Clinical practice guideline | AGREE | - |

**For most MIMIC/eICU research:** STROBE + RECORD (observational) or TRIPOD (prediction)

---

## STROBE: Observational Studies

**STrengthening the Reporting of OBservational studies in Epidemiology**

Website: [strobe-statement.org](https://www.strobe-statement.org/)

### Checklist Summary

| Section | Item | Key Requirements |
|---------|------|------------------|
| **Title/Abstract** | 1 | Indicate study design in title or abstract |
| **Introduction** | 2 | Scientific background and rationale |
| | 3 | Specific objectives, including pre-specified hypotheses |
| **Methods** | 4 | Study design: cohort, case-control, cross-sectional |
| | 5 | Setting: locations, dates, periods of recruitment/exposure/follow-up |
| | 6 | Participants: eligibility criteria, sources, selection methods |
| | 7 | Variables: outcomes, exposures, predictors, confounders, effect modifiers |
| | 8 | Data sources/measurement: for each variable of interest |
| | 9 | Bias: efforts to address potential sources |
| | 10 | Study size: how determined, power calculation if applicable |
| | 11 | Quantitative variables: how handled in analysis |
| | 12 | Statistical methods: all methods including confounding control |
| **Results** | 13 | Participants: numbers at each stage, reasons for non-participation |
| | 14 | Descriptive data: characteristics, missing data |
| | 15 | Outcome data: numbers of events or summary measures |
| | 16 | Main results: unadjusted and adjusted estimates, precision |
| | 17 | Other analyses: subgroups, interactions, sensitivity |
| **Discussion** | 18 | Key results with reference to objectives |
| | 19 | Limitations: sources of bias, imprecision |
| | 20 | Interpretation: cautious, considering objectives and limitations |
| | 21 | Generalizability: external validity |
| **Other** | 22 | Funding and role of funders |

### STROBE Common Gaps in EHR Research

| Gap | What's Missing | How to Fix |
|-----|----------------|------------|
| Vague eligibility | "ICU patients" without specifics | Report exact codes, criteria, dates |
| Missing flow diagram | No participant numbers | Include CONSORT-style flowchart |
| Undefined variables | "Sepsis" without definition | Specify Sepsis-3 or ICD codes used |
| No missing data info | Extent and handling not reported | Report % missing, imputation method |
| Unadjusted only | No confounder adjustment shown | Report both crude and adjusted |

---

## RECORD: Routinely Collected Health Data

**REporting of studies Conducted using Observational Routinely-collected health Data**

Website: [record-statement.org](https://www.record-statement.org/)

RECORD extends STROBE specifically for database studies (EHR, claims, registries).

### Additional RECORD Items

| STROBE Item | RECORD Extension |
|-------------|------------------|
| 4 (Study design) | 4.1: Describe database(s) used |
| 6 (Participants) | 6.1: Methods of selecting patients from database |
| | 6.2: Codes/algorithms for identifying participants |
| | 6.3: Validation of codes if applicable |
| 7 (Variables) | 7.1: Codes/algorithms used to define variables |
| 12 (Statistical methods) | 12.1: How data linkage was performed (if applicable) |
| 13 (Participants) | 13.1: Data cleaning steps |
| 19 (Limitations) | 19.1: Implications of using routinely collected data |
| | RECORD 22.1: Data access and cleaning methods availability |

### RECORD-Specific Reporting for MIMIC/eICU

| Element | What to Report |
|---------|----------------|
| Database version | MIMIC-IV v2.2, eICU v2.0, etc. |
| Access/ethics | PhysioNet credentialing, IRB status |
| Time period | Exact admission dates included |
| Code definitions | ICD-9/10 codes, lab LOINC codes, drug codes |
| Validation | Were codes validated against chart review? |
| Data linkage | How tables were joined (keys used) |
| Cleaning | Outlier handling, impossible values removed |

---

## TRIPOD: Prediction Models

**Transparent Reporting of a multivariable prediction model for Individual Prognosis Or Diagnosis**

Website: [tripod-statement.org](https://www.tripod-statement.org/)

### TRIPOD Checklist Summary

| Section | Item | Key Requirements |
|---------|------|------------------|
| **Title/Abstract** | 1 | Identify as prediction model; state development/validation |
| | 2 | Summary of objectives, participants, predictors, outcome, results |
| **Introduction** | 3 | Background and objectives |
| **Methods** | 4 | Source of data (development and validation) |
| | 5 | Participants: eligibility, recruitment, sampling |
| | 6 | Outcome: definition, timing, blinding |
| | 7 | Predictors: definitions, timing of measurement |
| | 8 | Sample size: how determined |
| | 9 | Missing data: handling strategy |
| | 10 | Statistical methods: model building, selection, internal validation |
| | 11 | Risk groups: how created if applicable |
| **Results** | 12 | Participants: flow diagram with numbers |
| | 13 | Model development: participant characteristics |
| | 14 | Model specification: coefficients, hazard ratios, etc. |
| | 15 | Model performance: discrimination, calibration |
| | 16 | Model updating: if applicable |
| **Discussion** | 17 | Limitations |
| | 18 | Interpretation: clinical use, comparison to existing models |
| | 19 | Implications for practice and future research |
| **Other** | 20 | Supplementary information: full model available |
| | 21 | Funding |

### TRIPOD Study Types

| Type | Description | Key Reporting |
|------|-------------|---------------|
| 1a | Development only | Internal validation required |
| 1b | Development + validation (same data, random split) | Report both sets |
| 2a | Development + validation (non-random split, e.g., temporal) | Specify split method |
| 2b | Development + validation (external data) | Describe both populations |
| 3 | Validation only (existing model) | Full model specification needed |
| 4 | Model updating | Original model + updates |

### TRIPOD Critical Items for ML Models

| Item | Requirement |
|------|-------------|
| Full model | Provide all coefficients/model specification or code |
| Internal validation | Cross-validation or bootstrap |
| Discrimination | AUROC with 95% CI |
| Calibration | Calibration plot, slope, intercept |
| Clinical utility | Decision curve analysis (recommended) |
| Missing data | Report approach and proportion missing |
| Sample size | Events per variable ratio |

---

## TRIPOD+AI: AI/ML Prediction Models

Extension for studies using artificial intelligence/machine learning methods.

### Additional TRIPOD+AI Items

| Category | Item | Requirement |
|----------|------|-------------|
| **Data** | Preprocessing | Detail all transformations, normalization |
| | Features | Feature selection/engineering methods |
| | Class imbalance | How handled |
| **Model** | Architecture | Full description of model structure |
| | Hyperparameters | Values used and tuning approach |
| | Training | Optimization algorithm, stopping criteria |
| | Software | Libraries, versions, random seeds |
| **Validation** | Splits | Exact split method, stratification |
| | Leakage | Steps to prevent data leakage |
| | Uncertainty | Confidence intervals via bootstrap/CV |
| **Interpretability** | Explainability | SHAP, feature importance, etc. |
| **Reproducibility** | Code | Availability of code and data |

---

## STARD: Diagnostic Accuracy

**STAndards for Reporting of Diagnostic accuracy studies**

Use when evaluating a test/marker's ability to distinguish disease states.

### Key STARD Elements

| Element | Requirement |
|---------|-------------|
| Index test | Fully describe the test being evaluated |
| Reference standard | Gold standard for true disease status |
| Participants | Spectrum of disease severity included |
| Flow diagram | All participants accounted for |
| 2×2 table | TP, FP, TN, FN counts |
| Metrics | Sensitivity, specificity, LR+, LR-, with CIs |
| Thresholds | How cutoffs were determined |

---

## Reporting Metrics

### For Association Studies (STROBE)

| Metric | What to Report |
|--------|----------------|
| Effect estimate | OR, RR, HR, mean difference |
| Precision | 95% confidence interval |
| P-value | Exact value (not "<0.05") |
| Crude and adjusted | Both estimates |
| Confounders | List all variables in adjusted model |

**Example:**
> Mortality was higher in the exposed group (adjusted HR 1.45, 95% CI 1.12–1.88, p=0.005) after adjustment for age, sex, SOFA score, and Charlson comorbidity index.

### For Prediction Models (TRIPOD)

| Metric | What to Report |
|--------|----------------|
| Discrimination | AUROC (95% CI), AUPRC if imbalanced |
| Calibration | Calibration plot, slope, intercept |
| Overall | Brier score |
| Classification | Sensitivity, specificity at chosen threshold |
| Clinical utility | Net benefit at threshold range (decision curve) |

**Example:**
> The model demonstrated good discrimination (AUROC 0.82, 95% CI 0.78–0.86) and adequate calibration (slope 0.94, intercept -0.12). Decision curve analysis showed net benefit over treating all/none for threshold probabilities between 10% and 40%.

---

## Tables and Figures Checklist

### Table 1: Baseline Characteristics

- [ ] Stratified by exposure/outcome group
- [ ] Continuous: mean (SD) or median (IQR) based on distribution
- [ ] Categorical: n (%)
- [ ] Missing data: n (%) per variable
- [ ] Standardized mean differences (for propensity studies)

### Flow Diagram

- [ ] Initial population screened
- [ ] Excluded at each step with counts and reasons
- [ ] Final analytic sample
- [ ] Lost to follow-up (if applicable)

### Results Table

- [ ] Crude and adjusted estimates
- [ ] 95% confidence intervals
- [ ] P-values
- [ ] Number of events and total N

### Prediction Model

- [ ] Calibration plot
- [ ] ROC curve with AUC and CI
- [ ] Model coefficients or code availability
- [ ] Performance in validation set

---

## Journal-Specific Requirements

Many journals require:
- Completed checklist uploaded as supplementary material
- Statement of adherence in methods section
- Data availability statement
- Code availability statement

**Check target journal's author guidelines.**

---

## Common Reporting Deficiencies

| Deficiency | Frequency | Impact |
|------------|-----------|--------|
| Missing flow diagram | Very common | Cannot assess selection bias |
| No missing data info | Very common | Cannot assess bias |
| No confidence intervals | Common | Cannot assess precision |
| Validation not reported | Common (ML) | Cannot assess generalizability |
| Model not reproducible | Common (ML) | Cannot implement or verify |
| Crude estimates missing | Common | Cannot assess confounding |
| Subgroup analyses post-hoc | Common | Inflated false positives |

---

## Quick Reference: Minimum Reporting

### Observational Study (STROBE + RECORD)

1. Study design in title
2. Database name, version, time period
3. Eligibility criteria with codes
4. Flow diagram with numbers
5. Variable definitions (codes)
6. Missing data extent and handling
7. Crude and adjusted estimates with CIs
8. Sensitivity analyses
9. Limitations section addressing bias

### Prediction Model (TRIPOD)

1. Development or validation study in title
2. Outcome and predictor definitions with timing
3. Sample size and events per variable
4. Missing data handling
5. Model specification (full coefficients or code)
6. Internal validation method
7. Discrimination (AUROC with CI)
8. Calibration (plot + metrics)
9. External validation if applicable
10. Limitations and clinical applicability

---

## Resources

| Guideline | Website | Checklist |
|-----------|---------|-----------|
| STROBE | strobe-statement.org | 22-item checklist |
| RECORD | record-statement.org | STROBE + 13 items |
| TRIPOD | tripod-statement.org | 22-item checklist |
| TRIPOD+AI | In development | Extended ML items |
| STARD | stard-statement.org | 30-item checklist |
| CONSORT | consort-statement.org | 25-item checklist |
| PRISMA | prisma-statement.org | 27-item checklist |

**EQUATOR Network** ([equator-network.org](https://www.equator-network.org/)): Central repository for all reporting guidelines.
