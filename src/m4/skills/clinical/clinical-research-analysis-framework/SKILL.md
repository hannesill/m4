---
name: clinical-research-analysis-framework
description: Guided workflow for statistical and ML analysis of clinical data. Use when planning or executing research analyses on MIMIC, eICU, or similar EHR data. Ensures methodological rigor through structured consultation, assumption checking, and stepwise execution with audit trails.
tier: expert
category: clinical
---

# Statistical Analysis Framework

## Overview

This skill provides a **consultation-first workflow** for statistical and machine learning analyses. Rather than jumping to implementation, it guides users through structured decision-making to ensure:

- Research intent is fully captured before any code runs
- Method selection is informed by trade-offs, not defaults
- Assumptions and limitations are explicitly acknowledged
- Execution is stepwise with checkpoints for user feedback
- All work is reproducible with complete audit trails

## When to Use This Skill

- Planning a new analysis on MIMIC, eICU, or similar data
- Choosing between statistical inference vs predictive modeling
- Needing guidance on appropriate methods for a research question
- Executing analyses with reproducibility requirements
- Validating ML models or statistical findings

---

## Guiding Philosophy

### This Skill Guides, Not Limits

The methods and checklists in this skill are **starting points, not boundaries**. Claude's statistical knowledge extends far beyond what is explicitly listed here. When a user's problem calls for a method not covered in the references — whether that's g-computation, Bayesian hierarchical models, causal forests, doubly robust estimation, joint longitudinal-survival models, or something else entirely — Claude should:

1. **Suggest it** with clear explanation of why it fits better
2. **Explain the intuition** so the user understands the approach
3. **Compare it** to simpler alternatives with trade-offs
4. **Let the user decide** based on understanding, not just trust

### The Collaboration Model

```
User describes problem
        ↓
Claude suggests methods (from full knowledge, not just this skill)
        ↓
Claude explains: "Here's why this fits your situation..."
        ↓
User asks questions, pushes back, explores alternatives
        ↓
Claude refines: "Given that concern, consider instead..."
        ↓
User makes informed choice
        ↓
Proceed with understanding, not blind execution
```

### Principles

1. **Explain, don't prescribe:** When suggesting a method, explain *why* it's appropriate for this specific problem. The user should understand enough to defend the choice in peer review.

2. **Surface complexity when warranted:** If the user's problem genuinely requires a sophisticated approach (e.g., time-varying confounding needs g-methods, not just regression), say so — don't default to simpler methods just because they're more familiar.

3. **Make trade-offs explicit:** Every method has costs. Simpler methods may be biased but interpretable; complex methods may be less biased but harder to explain. Let the user weigh these.

4. **Welcome pushback:** If the user suggests an alternative or questions the recommendation, engage seriously. They may have domain knowledge that changes the calculus.

5. **Teach through the process:** The goal isn't just to produce an analysis — it's to help the user develop statistical intuition for future work.

### What the Reference Files Are

| Reference | Purpose | What It's NOT |
|-----------|---------|---------------|
| `method-families.md` | Common methods as starting vocabulary | Exhaustive list of all valid approaches |
| `assumptions-limitations.md` | Key checks for common methods | Complete statistical theory |
| `validation-strategy.md` | Standard rigor requirements | Only acceptable validation approaches |
| `reporting-guidelines.md` | Publication standards | Rigid templates |

**If the right method isn't listed, use it anyway and explain why.**

---

## Workflow Overview

```
┌─────────────────────────────────────────────────────────────┐
│  CONSULTATION PHASE (Phases 1-6)                            │
│  - Capture intent                                           │
│  - Clarify data structure                                   │
│  - Present method options                                   │
│  - Acknowledge assumptions                                  │
│  - Agree on validation strategy                             │
│  - Consolidate plan                                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
                   [User confirms plan]
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  EXECUTION PHASE (Phase 7)                                  │
│  - Stepwise execution with checkpoints                      │
│  - Each step: script → run → output → log → user feedback   │
│  - No progression without user confirmation                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
                   [Analysis complete]
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  REPORTING PHASE (Phase 8)                                  │
│  - Select appropriate guideline (STROBE/TRIPOD/etc.)        │
│  - Generate tables, figures, flow diagrams                  │
│  - Complete reporting checklist                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Capture Intent

**Objective:** Understand what the user wants to learn before discussing methods.

**Ask the user:**

1. What is your research question in plain language?
2. Is this exploratory (hypothesis-generating) or confirmatory (hypothesis-testing)?
3. What is your outcome of interest?
   - Binary (yes/no, alive/dead)
   - Continuous (lab value, score)
   - Time-to-event (survival, LOS)
   - Count (number of events)
4. What is your primary exposure or predictor of interest?
5. Is your goal **prediction** (accurate forecasting) or **inference** (understanding associations/causation)?

**Output:** Document research aim, outcome type, and analysis goal.

**Reference:** See `references/question-taxonomy.md` for detailed guidance.

---

## Phase 2: Data Structure Check

**Objective:** Clarify the unit of analysis and data source.

**Ask the user:**

1. Which database? (MIMIC-IV, eICU, both, other)
2. What is your unit of analysis?
   - Patient-level (one row per patient)
   - Admission-level (one row per hospitalization)
   - ICU stay-level (one row per ICU episode)
3. For patients with multiple admissions/stays, how will you handle this?
   - First only
   - Last only
   - All (requires accounting for clustering)
   - Index event defined by specific criteria
4. What defines time-zero for your analysis?
   - Hospital admission
   - ICU admission
   - Specific event (e.g., diagnosis, procedure)
5. What are your key inclusion/exclusion criteria?

**Output:** Document cohort definition and data structure.

**Reference:** See `references/study-design-checklist.md` and `references/ehr-data-considerations.md`.

---

## Phase 3: Method Selection

**Objective:** Present appropriate methods with trade-offs; let user choose.

**Note:** The tables below are common starting points. If the user's problem calls for a method not listed — g-computation, Bayesian hierarchical models, joint longitudinal-survival models, causal forests, or anything else — suggest it and explain why it fits better than the standard options.

**Based on Phases 1-2, present relevant options:**

### For Group Comparisons (Is there a difference?)

| Method | When to Use | Key Assumption |
|--------|-------------|----------------|
| t-test | 2 groups, continuous outcome | Normality (or n>30) |
| Mann-Whitney U | 2 groups, non-normal/ordinal | Independent observations |
| ANOVA | 3+ groups, continuous | Normality, equal variance |
| Kruskal-Wallis | 3+ groups, non-normal | Independent observations |
| Chi-square | Categorical outcome | Expected counts ≥5 |
| Fisher's exact | Categorical, small n | None (exact test) |

### For Association/Inference (Is X associated with Y?)

| Method | When to Use | Key Considerations |
|--------|-------------|-------------------|
| Linear regression | Continuous outcome | Linearity, homoscedasticity |
| Logistic regression | Binary outcome | No perfect separation |
| Poisson/Negative binomial | Count outcome | Overdispersion check |
| Cox proportional hazards | Time-to-event | PH assumption |
| Competing risks (Fine-Gray) | Time-to-event with competing events | Competing event definition |
| IPTW / Propensity matching | Causal inference aim | Positivity, no unmeasured confounding |

### For Prediction (Can we forecast Y?)

| Method | Strengths | Limitations |
|--------|-----------|-------------|
| Logistic regression | Interpretable, calibrated | May underfit complex relationships |
| LASSO/Ridge/Elastic net | Handles many predictors | Less interpretable |
| Random forest | Captures non-linearity | Black box, can overfit |
| Gradient boosting (XGBoost, LightGBM) | Often best performance | Requires careful tuning |
| Neural networks | Flexible | Needs large data, black box |

**Ask the user:**

1. Which method family aligns with your goal?
2. Do you need interpretable coefficients or prioritize predictive accuracy?
3. If inference: Are you aiming for causal claims? (Requires stronger assumptions)

**Output:** Document selected method with rationale.

**Reference:** See `references/method-families.md` for detailed trade-offs.

---

## Phase 4: Assumptions & Limitations Acknowledgment

**Objective:** Ensure user understands what must hold for valid results.

**Based on chosen method, present:**

1. **Required assumptions** and how to check them
2. **What happens if violated** and alternatives available
3. **Inherent limitations** of the method
4. **EHR-specific concerns** (selection bias, missingness, etc.)

**Example for Cox regression:**
```
Assumptions:
- Proportional hazards: Check with Schoenfeld residuals, log-log plot
- Non-informative censoring: Consider if dropout relates to outcome
- Linearity of continuous covariates: Check with martingale residuals

If PH violated:
- Stratified Cox (if categorical violator)
- Time-varying coefficients
- Restricted mean survival time (RMST)
- Accelerated failure time (AFT) models

EHR-specific concerns:
- Immortal time bias if time-zero misaligned
- Informative censoring (transfer, discharge)
- Competing risks (death vs discharge)
```

**Ask the user:**

1. Are you comfortable proceeding with these assumptions?
2. Should we plan sensitivity analyses to test robustness?

**Output:** Document acknowledged assumptions and planned sensitivity analyses.

**Reference:** See `references/assumptions-limitations.md`.

---

## Phase 5: Validation Strategy

**Objective:** Agree on how results will be validated.

### For Predictive Models (ML Path)

**Ask:**
1. How should we split data?
   - Random (ensure patient-level, not admission-level)
   - Temporal (train on earlier, test on later)
   - Site-based (for eICU multi-center)
2. What validation approach?
   - Single train/test split (minimum)
   - k-fold cross-validation
   - Nested CV (if tuning hyperparameters)
   - Bootstrap for confidence intervals
3. What metrics matter?
   - Discrimination: AUROC, AUPRC
   - Calibration: Brier score, calibration plot
   - Clinical utility: decision curve analysis

### For Statistical Inference Path

**Ask:**
1. What is your significance threshold (α)? (Default: 0.05)
2. Are multiple comparisons planned? If so, correction method?
   - Bonferroni (conservative)
   - Benjamini-Hochberg FDR (less conservative)
   - Pre-specified primary outcome (no correction needed)
3. Do you want confidence intervals reported? (Recommended: yes)
4. Is this adequately powered? (Discuss sample size if relevant)

**Output:** Document validation plan.

**Reference:** See `references/validation-strategy.md`.

---

## Phase 6: Consolidated Plan

**Objective:** Summarize everything before execution.

**Generate a structured analysis plan:**

```
═══════════════════════════════════════════════════════════════
                      ANALYSIS PLAN
═══════════════════════════════════════════════════════════════

Research Question: [plain language statement]

Study Design:
  - Type: [cohort / case-control / cross-sectional]
  - Database: [MIMIC-IV / eICU / other]
  - Unit of analysis: [patient / admission / ICU stay]

Cohort Definition:
  - Inclusion: [criteria]
  - Exclusion: [criteria]
  - Time-zero: [definition]

Outcome:
  - Primary: [outcome, type]
  - Secondary: [if any]

Exposure/Predictors:
  - Primary: [exposure of interest]
  - Covariates: [adjustment variables]

Analysis Method:
  - Primary: [method]
  - Alternatives if assumptions fail: [methods]

Assumptions to Check:
  - [list]

Validation Strategy:
  - [ML: split strategy, metrics]
  - [Statistical: α, multiple comparisons, CIs]

Sensitivity Analyses:
  - [planned robustness checks]

Known Limitations:
  - [acknowledged limitations]

═══════════════════════════════════════════════════════════════
```

**Ask the user:** "Does this plan look correct? Ready to proceed with execution?"

**Only proceed to Phase 7 after explicit confirmation.**

---

## Phase 7: Stepwise Execution

**Objective:** Execute the plan with full reproducibility and user checkpoints.

### File Organization

```
project_analysis/
├── scripts/
│   ├── 01_cohort_definition_20250203.py
│   ├── 02_descriptive_statistics_20250203.py
│   ├── 03_missing_data_assessment_20250203.py
│   ├── 04_assumption_checks_20250204.py
│   ├── 05_primary_analysis_20250204.py
│   └── 06_sensitivity_analysis_20250205.py
├── outputs/
│   ├── 01_cohort_flowchart_20250203.png
│   ├── 01_cohort_data_20250203.csv
│   ├── 02_table1_20250203.csv
│   ├── 03_missingness_summary_20250203.csv
│   ├── 04_schoenfeld_plot_20250204.png
│   ├── 05_cox_results_20250204.csv
│   └── 05_km_curve_20250204.png
├── logs/
│   └── analysis_log.md
```

### Naming Convention

- **Scripts:** `{##}_{description}_{YYYYMMDD}.py`
- **Outputs:** `{##}_{description}_{YYYYMMDD}.{ext}`
- **Date** always at end, before extension
- **Numbers** link scripts to their outputs

### Execution Steps

| Step | Purpose | Key Outputs | Checkpoint |
|------|---------|-------------|------------|
| 01 | Cohort definition | Flowchart, cohort CSV | Approve N, criteria |
| 02 | Descriptive statistics | Table 1 | Review balance, distributions |
| 03 | Missing data assessment | Missingness summary | Decide imputation strategy |
| 04 | Assumption checks | Diagnostic plots/tests | Proceed or modify method |
| 05 | Primary analysis | Results, figures | Interpret together |
| 06 | Sensitivity analyses | Alternative results | Compare robustness |

### Execution Protocol

At each step, Claude will:

1. **Announce intent:** State what will be done
2. **Create script:** Save to `scripts/` with proper naming
3. **Execute:** Run and save outputs to `outputs/`
4. **Update log:** Append entry to `analysis_log.md`
5. **Present results:** Show key findings (summarized, not raw dumps)
6. **Ask for confirmation:**
   - "Does this look correct?"
   - "Any adjustments needed?"
   - "Ready to proceed to next step?"
7. **Wait** for user response before continuing

### Analysis Log Format

The `analysis_log.md` file maintains a complete audit trail:

```markdown
# Analysis Log: [Project Name]

## Analysis Plan Summary
- Research Question: ...
- Method: ...
- Plan confirmed: [date]

---

## Step 01: Cohort Definition
- **Script:** `01_cohort_definition_20250203.py`
- **Outputs:**
  - `01_cohort_flowchart_20250203.png`
  - `01_cohort_data_20250203.csv` (n=12,847)
- **Summary:** Started 58,976 admissions → excluded <18yo (8,234),
  LOS<24h (15,102), missing outcome (3,201) → final n=12,847
- **Decision:** Approved. Proceed to descriptives.
- **Date:** 2025-02-03

---

## Step 02: Descriptive Statistics
- **Script:** `02_descriptive_statistics_20250203.py`
- **Outputs:**
  - `02_table1_20250203.csv`
- **Summary:** Groups balanced on age, sex. Imbalance in creatinine.
- **Decision:** Add creatinine as covariate. Updated plan.
- **Date:** 2025-02-03

---
[continues for each step]
```

### Handling Revisions

When user requests changes:

1. Create new script version: `05_primary_analysis_20250204_v2.py`
2. Generate new outputs with matching version
3. Log the change with rationale
4. Show comparison with previous results if relevant

---

## Phase 8: Final Reporting

**Objective:** Ensure results are reported according to appropriate guidelines.

### Guideline Selection

| Study Type | Use |
|------------|-----|
| Observational (association) | STROBE + RECORD |
| Prediction model | TRIPOD (+ TRIPOD+AI for ML) |
| Diagnostic accuracy | STARD |

### Reporting Outputs

Claude can assist with generating:

1. **Flow diagram:** CONSORT-style participant flow
2. **Table 1:** Baseline characteristics with appropriate statistics
3. **Results table:** Estimates, CIs, p-values (crude and adjusted)
4. **Figures:** Calibration plots, ROC curves, Kaplan-Meier, forest plots
5. **Supplementary materials:** Full model coefficients, sensitivity analyses
6. **Checklist:** Completed reporting guideline checklist

### Minimum Reporting Checklist

Before finalizing, verify:

- [ ] Study design stated in title/abstract
- [ ] Database, version, time period documented
- [ ] Flow diagram with numbers at each step
- [ ] All variable definitions with codes
- [ ] Missing data extent and handling reported
- [ ] Appropriate effect measures with 95% CIs
- [ ] Sensitivity analyses included
- [ ] Limitations explicitly discussed
- [ ] Code/data availability statement

**Reference:** See `references/reporting-guidelines.md` for detailed checklists.

---

## References

This skill includes detailed reference files:

| File | Content |
|------|---------|
| `references/question-taxonomy.md` | Research question types, prediction vs inference |
| `references/method-families.md` | Available methods, when to use, trade-offs |
| `references/assumptions-limitations.md` | By-method assumptions and violation remedies |
| `references/validation-strategy.md` | ML validation rigor, statistical inference standards |
| `references/ehr-data-considerations.md` | MIMIC/eICU specific pitfalls and biases |
| `references/study-design-checklist.md` | Cohort definition, time-zero, confounding |
| `references/reporting-guidelines.md` | STROBE, RECORD, TRIPOD, STARD checklists |

---

## Quick Reference: Common Workflows

### Workflow A: "Is treatment X associated with outcome Y?"

```
Phase 1: Inference goal, binary/time-to-event outcome
Phase 2: Define exposed vs unexposed, time-zero
Phase 3: Logistic regression, Cox, or IPTW
Phase 4: Check confounding, PH assumption
Phase 5: CI reporting, sensitivity analyses
Phase 7: Execute with focus on adjusted estimates
```

### Workflow B: "Can we predict outcome Y at admission?"

```
Phase 1: Prediction goal, define prediction horizon
Phase 2: Define features available at prediction time
Phase 3: ML methods (logistic, XGBoost, etc.)
Phase 4: Acknowledge limited interpretability
Phase 5: Patient-level split, AUROC/AUPRC, calibration
Phase 7: Execute with focus on validation metrics
```

### Workflow C: "Are groups different on outcome Y?"

```
Phase 1: Group comparison, identify outcome type
Phase 2: Define groups, ensure independence
Phase 3: t-test/ANOVA or non-parametric alternative
Phase 4: Check normality, equal variance
Phase 5: Set α, plan for multiple comparisons if needed
Phase 7: Execute with focus on effect sizes + p-values
```

---

## Critical Reminders

1. **Never skip consultation phases** — method selection without understanding intent leads to misaligned analyses

2. **Always use patient-level splitting** for ML — admission-level splits cause data leakage

3. **Document everything** — the analysis log is the audit trail

4. **No step proceeds without user confirmation** — this is a collaboration, not automation

5. **Assumptions matter** — a method applied with violated assumptions gives misleading results

6. **EHR data is not clean** — always assess missingness, selection bias, and temporal issues

7. **Go beyond this skill when needed** — if the right method isn't listed here, use it anyway and explain why

8. **Teach, don't just execute** — the user should understand enough to defend choices in peer review

9. **Welcome pushback** — user domain knowledge may reveal considerations that change the recommendation

10. **Make trade-offs explicit** — every method has costs; let the user weigh them
