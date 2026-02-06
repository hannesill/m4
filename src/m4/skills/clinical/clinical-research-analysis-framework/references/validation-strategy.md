# Validation Strategy

## Overview

Validation ensures that findings are reliable and generalizable. The approach differs between predictive modeling (ML) and statistical inference, though both require rigor.

---

## Machine Learning Validation

### Core Principle

**Training performance means nothing. Only held-out performance matters.**

### Data Splitting Strategies

#### Simple Train/Test Split

```
Full Data
├── Training (70-80%) → fit model
└── Test (20-30%) → evaluate final model (touch ONCE)
```

- **Pros:** Simple, fast
- **Cons:** Single estimate, variance in performance
- **Use when:** Large dataset, quick baseline

#### Train/Validation/Test Split

```
Full Data
├── Training (60%) → fit model
├── Validation (20%) → tune hyperparameters, select model
└── Test (20%) → final evaluation (touch ONCE)
```

- **Pros:** Separates tuning from evaluation
- **Cons:** Less training data, still single test estimate
- **Use when:** Hyperparameter tuning needed

#### K-Fold Cross-Validation

```
Full Data split into K folds
Repeat K times:
  - Train on K-1 folds
  - Validate on 1 fold
Report mean ± SD across folds
```

- **Pros:** Uses all data, variance estimate
- **Cons:** Computationally expensive, no single "final" model
- **Use when:** Moderate sample size, want uncertainty

#### Nested Cross-Validation

```
Outer loop: K-fold for performance estimation
  Inner loop: K-fold for hyperparameter tuning
```

- **Pros:** Unbiased performance estimate with tuning
- **Cons:** Very computationally expensive
- **Use when:** Hyperparameters must be tuned, rigorous reporting needed

---

### Critical: Patient-Level Splitting

**NEVER split at the admission or ICU-stay level if patients have multiple records.**

**Wrong:**
```
Admission 1 (Patient A) → Train
Admission 2 (Patient A) → Test  ← DATA LEAKAGE!
```

**Correct:**
```
All of Patient A's admissions → Train
All of Patient B's admissions → Test
```

Implementation:
```python
from sklearn.model_selection import GroupKFold

# 'subject_id' ensures all admissions from same patient stay together
gkf = GroupKFold(n_splits=5)
for train_idx, test_idx in gkf.split(X, y, groups=df['subject_id']):
    ...
```

---

### Temporal Validation

For EHR data, temporal splits often better reflect real-world deployment:

```
Data from 2008-2016 → Train
Data from 2017-2019 → Test
```

**Why:**
- Simulates prospective deployment
- Accounts for temporal drift (practice changes, ICD-10 transition)
- More honest estimate of future performance

---

### Multi-Site Validation (eICU)

For multi-center data, consider site-level splits:

```
Hospitals A, B, C → Train
Hospitals D, E → Test
```

**Why:** Tests generalizability across institutions

---

### Metrics for Binary Outcomes

| Metric | What It Measures | When to Use |
|--------|------------------|-------------|
| **AUROC** | Discrimination (ranking) | Standard overall performance |
| **AUPRC** | Precision-recall trade-off | Imbalanced outcomes (rare events) |
| **Brier score** | Calibration + discrimination | When probability accuracy matters |
| **Calibration slope/intercept** | Calibration only | Clinical decision support |
| **Sensitivity/Specificity** | At a threshold | When threshold is clinically defined |
| **PPV/NPV** | Predictive values | Depends on prevalence |

#### Discrimination vs. Calibration

- **Discrimination:** Can the model rank patients? (Higher risk → higher score)
- **Calibration:** Are predicted probabilities accurate? (30% prediction → 30% actually have event)

**Both matter for clinical use.** A well-discriminating but poorly calibrated model gives misleading risk estimates.

#### Calibration Assessment

1. **Calibration plot:** Predicted vs observed, should follow 45° line
2. **Hosmer-Lemeshow test:** Formal test (but sensitive to sample size)
3. **Calibration slope:** Should be ~1.0 (if <1, overfitting; if >1, underfitting)

---

### Handling Class Imbalance

| Strategy | Approach | When to Use |
|----------|----------|-------------|
| Do nothing | Rely on proper metrics (AUPRC) | Often the best approach |
| Class weights | Upweight minority class in loss | Easy, often effective |
| SMOTE | Synthetic minority oversampling | Moderate imbalance |
| Undersampling | Reduce majority class | Very large dataset |
| Threshold tuning | Adjust decision threshold | Deployment stage |

**Warning:** SMOTE and oversampling can leak information if done before splitting. Always apply **within** each training fold, never to full data.

---

### Bootstrap for Confidence Intervals

```
Repeat B times (e.g., B=1000):
  1. Sample with replacement from test set
  2. Calculate metric on bootstrap sample
Report: median and 2.5th/97.5th percentiles
```

Gives confidence intervals for AUROC, AUPRC, etc.

---

## Statistical Inference Validation

### Confidence Intervals

**Always report CIs alongside point estimates.**

| Estimate | CI Interpretation |
|----------|-------------------|
| OR = 1.5, 95% CI [1.1, 2.0] | Effect likely between 1.1 and 2.0 |
| OR = 1.5, 95% CI [0.8, 2.8] | Effect uncertain; CI includes null |

CIs are more informative than p-values alone.

---

### Significance Testing Framework

| Component | Standard Choice | Notes |
|-----------|-----------------|-------|
| α level | 0.05 | Pre-specify; consider 0.01 for exploratory |
| Sidedness | Two-sided | Unless strong prior for direction |
| Primary outcome | One | Pre-specify to avoid p-hacking |

---

### Multiple Comparisons

**Problem:** Testing 20 hypotheses at α=0.05 expects 1 false positive by chance.

| Method | Approach | When to Use |
|--------|----------|-------------|
| Pre-specify primary | No correction needed | Single confirmatory question |
| Bonferroni | α / n tests | Few planned comparisons, conservative |
| Holm-Bonferroni | Step-down Bonferroni | Slightly more power than Bonferroni |
| Benjamini-Hochberg | Controls FDR | Many tests, exploratory |
| No correction | Report all | Clearly exploratory, for hypothesis generation |

---

### Effect Sizes

**P-values alone are insufficient. Report effect sizes.**

| Outcome | Effect Size | Interpretation Aid |
|---------|-------------|--------------------|
| Continuous | Cohen's d, mean difference | d: 0.2 small, 0.5 medium, 0.8 large |
| Binary | Odds ratio, risk ratio, risk difference | Clinical significance depends on context |
| Time-to-event | Hazard ratio | HR 2.0 = doubled instantaneous risk |

---

### Power and Sample Size

#### Pre-Study Power Analysis

Before starting:
- Define minimum clinically important effect
- Calculate required n for 80% or 90% power

#### Post-Study: Sensitivity, Not Power

**Do NOT compute post-hoc power** (it's a function of p-value, tells nothing new).

Instead, compute **detectable effect size:**
- "With n=500 and α=0.05, we had 80% power to detect OR ≥ 1.3"

---

### Sensitivity Analyses

Planned analyses to test robustness:

| Type | Purpose | Example |
|------|---------|---------|
| Different inclusion criteria | Check if results depend on cohort definition | Include vs exclude patients with missing data |
| Different adjustment sets | Check if results depend on confounder choice | Minimal vs full adjustment |
| Different model specification | Check functional form assumptions | Continuous vs categorical exposure |
| Different time windows | Check temporal sensitivity | 30-day vs 90-day mortality |
| E-value (causal) | Assess unmeasured confounding | How strong would unmeasured confounder need to be? |

---

## Reporting Checklist

### For Predictive Models

- [ ] Split strategy clearly described (patient-level, temporal, etc.)
- [ ] Cross-validation or held-out test used
- [ ] Discrimination metrics (AUROC, AUPRC)
- [ ] Calibration assessed (plot, slope)
- [ ] Confidence intervals via bootstrap
- [ ] Class imbalance handling described
- [ ] Feature selection done within CV (no leakage)

### For Statistical Inference

- [ ] Primary outcome pre-specified
- [ ] Sample size justification
- [ ] Effect size with confidence interval
- [ ] P-value and α level stated
- [ ] Multiple comparison correction (if applicable)
- [ ] Sensitivity analyses performed
- [ ] Assumptions checked and reported

---

## Common Validation Mistakes

1. **Reporting training AUROC:** Always use held-out data

2. **Admission-level splits with repeated patients:** Data leakage

3. **Tuning on test set:** Use separate validation set

4. **SMOTE before splitting:** Information leakage

5. **Only reporting p-values:** Effect size and CI needed

6. **Post-hoc power analysis:** Uninformative; use sensitivity analysis

7. **Single train/test split with small data:** High variance; use CV

8. **Ignoring calibration:** Discrimination alone insufficient for clinical use
