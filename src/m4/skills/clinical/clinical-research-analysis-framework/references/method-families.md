# Method Families

## Overview

This reference provides a conceptual overview of statistical and ML methods commonly used in clinical research. The goal is to help users understand **when to use what** and **key trade-offs**, not implementation details.

**Important:** This is a starting vocabulary, not an exhaustive list. Many valid methods are not listed here — Bayesian approaches, g-methods for time-varying confounding, causal machine learning, functional data analysis, joint models, and many others may be more appropriate for specific problems. When the user's situation calls for something beyond this list, suggest it and explain why.

---

## Group Comparison Methods

For answering: "Is there a difference between groups?"

### Continuous Outcomes

| Method | Groups | Assumptions | When to Use |
|--------|--------|-------------|-------------|
| Independent t-test | 2 | Normality, equal variance | Standard comparison of means |
| Welch's t-test | 2 | Normality | Unequal variances |
| Paired t-test | 2 (matched) | Normality of differences | Before/after, matched pairs |
| Mann-Whitney U | 2 | None (non-parametric) | Non-normal data, ordinal data |
| Wilcoxon signed-rank | 2 (matched) | None | Paired, non-normal |
| One-way ANOVA | 3+ | Normality, equal variance | Multiple group means |
| Welch's ANOVA | 3+ | Normality | Unequal variances |
| Kruskal-Wallis | 3+ | None | Non-normal, ordinal |
| Repeated measures ANOVA | 3+ (matched) | Sphericity | Same subjects, multiple conditions |
| Friedman test | 3+ (matched) | None | Repeated measures, non-parametric |

**Trade-off:** Parametric tests (t-test, ANOVA) have more power when assumptions hold; non-parametric tests are safer but less powerful.

### Categorical Outcomes

| Method | Use Case | Assumptions |
|--------|----------|-------------|
| Chi-square test | 2×2 or larger tables | Expected counts ≥5 |
| Fisher's exact test | Small samples | None (exact) |
| McNemar's test | Paired categorical | Matched pairs |
| Cochran's Q | Repeated binary measures | Multiple matched groups |

---

## Regression Methods

For answering: "Is X associated with Y, adjusting for covariates?"

### Linear Regression Family

| Method | Outcome | When to Use |
|--------|---------|-------------|
| Ordinary Least Squares (OLS) | Continuous | Standard case |
| Weighted Least Squares (WLS) | Continuous | Heteroscedasticity with known structure |
| Generalized Least Squares (GLS) | Continuous | Correlated errors |
| Quantile regression | Continuous | Interest in medians/quantiles, robust to outliers |
| Ridge/LASSO/Elastic net | Continuous | Many predictors, multicollinearity |

**Key assumptions for OLS:**
- Linearity of relationship
- Independence of errors
- Homoscedasticity (constant variance)
- Normality of residuals (for inference)

### Generalized Linear Models (GLM)

| Outcome Type | Distribution | Link | Model Name |
|--------------|--------------|------|------------|
| Binary (0/1) | Binomial | Logit | Logistic regression |
| Binary (0/1) | Binomial | Probit | Probit regression |
| Count | Poisson | Log | Poisson regression |
| Count (overdispersed) | Negative binomial | Log | Negative binomial regression |
| Positive continuous | Gamma | Log | Gamma regression |
| Proportion | Beta | Logit | Beta regression |

**Trade-off:** GLMs require correct specification of distribution and link; misspecification biases estimates.

### Models for Correlated Data

| Method | Correlation Structure | When to Use |
|--------|----------------------|-------------|
| Mixed effects models | Hierarchical / clustered | Patients within hospitals, repeated measures |
| Generalized Estimating Equations (GEE) | Clustered | Population-averaged effects, robust to misspecification |
| Fixed effects regression | Panel data | Control for time-invariant confounders |

**Trade-off:** Mixed models give subject-specific estimates; GEE gives population-averaged estimates. Choose based on research question.

---

## Survival / Time-to-Event Methods

For answering: "When does the event occur? What affects time-to-event?"

| Method | Key Feature | Assumptions |
|--------|-------------|-------------|
| Kaplan-Meier | Non-parametric survival curve | Non-informative censoring |
| Log-rank test | Compare survival curves | PH (approximately) |
| Cox proportional hazards | Covariate-adjusted hazard ratios | Proportional hazards |
| Stratified Cox | Stratify by PH violator | PH within strata |
| Time-varying Cox | Coefficients change over time | None on time-dependence |
| Accelerated Failure Time (AFT) | Models survival time directly | Distributional assumption |
| Restricted Mean Survival Time (RMST) | Difference in area under curve | None (non-parametric) |
| Fine-Gray (competing risks) | Subdistribution hazards | Competing event defined |
| Cause-specific hazards | Event-specific hazards | Competing events identified |

**When Cox PH assumption fails:**
1. **Stratify** by the violating variable (if categorical)
2. **Time-varying coefficients** (if effect changes over time)
3. **RMST** (avoids PH assumption entirely)
4. **AFT models** (if distributional assumption is reasonable)

**Trade-off:** Cox is semiparametric and robust; AFT requires distributional assumption but directly models survival time.

---

## Causal Inference Methods

For answering: "What is the causal effect of X on Y?"

| Method | Approach | Key Assumption |
|--------|----------|----------------|
| Multivariable regression | Adjust for confounders | All confounders measured and included |
| Propensity score matching | Match treated/untreated | No unmeasured confounding, positivity |
| IPTW | Weight by inverse propensity | No unmeasured confounding, positivity |
| Doubly robust estimation | Combine PS and outcome models | One of two models correct |
| Instrumental variables | Use instrument to isolate effect | Valid instrument exists |
| Regression discontinuity | Exploit threshold assignment | No manipulation at threshold |
| Difference-in-differences | Pre/post with control group | Parallel trends |

**Critical assumptions for observational causal inference:**
1. **Exchangeability:** No unmeasured confounding
2. **Positivity:** All covariate patterns have both treated and untreated
3. **Consistency:** Well-defined intervention
4. **No interference:** One unit's treatment doesn't affect another's outcome

**Trade-off:** These methods enable causal claims from observational data but require strong, untestable assumptions. Sensitivity analyses are essential.

---

## Machine Learning Methods

For answering: "Can we accurately predict Y?"

### Traditional ML

| Method | Strengths | Limitations |
|--------|-----------|-------------|
| Logistic regression | Interpretable, calibrated, fast | May underfit complex patterns |
| LASSO/Ridge/Elastic Net | Handles many predictors, regularized | Less interpretable than plain logistic |
| Decision tree | Highly interpretable | Unstable, prone to overfit |
| Random forest | Handles non-linearity, robust | Black box, slow prediction |
| Gradient boosting (XGBoost, LightGBM) | Often best performance | Requires tuning, black box |
| Support vector machines | Good for high-dimensional | Sensitive to scaling, less common now |

### Deep Learning

| Method | Use Case | Requirements |
|--------|----------|--------------|
| Feedforward neural networks | Tabular data | Large n, careful tuning |
| Recurrent neural networks (RNN/LSTM) | Sequential data (time series) | Very large n, computational resources |
| Transformers | Complex sequential patterns | Massive data, specialized expertise |

**Trade-off:** More complex models may achieve better prediction but sacrifice interpretability and require more data/tuning.

### Interpretability Spectrum

```
More interpretable                              Less interpretable
├──────────────────────────────────────────────────────────────┤
Logistic   →   LASSO   →   Tree   →   Forest   →   XGBoost   →   Neural Net
```

---

## Model Selection Guidance

### By Research Goal

| Goal | Recommended Approach |
|------|---------------------|
| Understand association | Regression with careful confounder adjustment |
| Claim causation | Causal inference methods + sensitivity analysis |
| Predict accurately | ML methods with rigorous validation |
| Describe population | Descriptive statistics, visualization |

### By Outcome Type

| Outcome | Standard Choice | Alternative |
|---------|-----------------|-------------|
| Continuous | Linear regression | Quantile regression, GAM |
| Binary | Logistic regression | Random forest, XGBoost |
| Time-to-event | Cox regression | AFT, competing risks |
| Count | Poisson regression | Negative binomial, zero-inflated |
| Ordinal | Ordinal logistic | Multinomial (if few categories) |

### By Data Structure

| Structure | Consideration | Methods |
|-----------|---------------|---------|
| Independent observations | Standard methods | All above |
| Clustered (patients in hospitals) | Account for clustering | Mixed models, GEE, cluster-robust SE |
| Repeated measures | Account for correlation | Mixed models, GEE |
| Time series | Account for autocorrelation | ARIMA, state space models |

---

## Common Pitfalls in Method Selection

1. **Using prediction metrics for inference:** High AUROC doesn't mean the coefficient is unbiased

2. **Ignoring clustering:** Standard errors are wrong if observations aren't independent

3. **Cox when PH fails:** Hazard ratios are uninterpretable if PH is violated

4. **Poisson with overdispersion:** SEs are too small; use negative binomial

5. **Causal claims from regression:** Adjustment doesn't equal causation without design

6. **ML without validation:** Training metrics are meaningless; always use held-out data

---

## Beyond This List: Advanced Methods

The methods above cover common scenarios. For complex problems, consider approaches not detailed here:

### Causal Inference (Time-Varying)
- **G-computation / G-formula:** When confounders are affected by prior treatment
- **Marginal structural models:** IPTW for time-varying treatments
- **Targeted learning (TMLE):** Doubly robust, handles high-dimensional confounders
- **Causal forests:** Heterogeneous treatment effect estimation

### Bayesian Approaches
- **Bayesian regression:** When priors are informative or sample size is small
- **Bayesian hierarchical models:** Multi-level data with borrowing of information
- **Bayesian survival models:** Flexible hazard specifications

### Joint and Longitudinal Models
- **Joint longitudinal-survival models:** When a biomarker trajectory predicts time-to-event
- **Latent class mixed models:** Subgroup discovery with longitudinal data
- **Functional data analysis:** When predictors are curves (e.g., continuous vital signs)

### Modern ML Extensions
- **Survival forests / DeepSurv:** ML for time-to-event
- **Conformal prediction:** Distribution-free prediction intervals
- **Multi-task learning:** Predicting multiple related outcomes

### When to Surface These

Suggest advanced methods when:
- Standard assumptions clearly fail (e.g., time-varying confounding)
- The user's question specifically requires it (e.g., heterogeneous effects)
- Simpler methods would give misleading answers
- The user has sufficient data and expertise to implement properly

Always explain **why** the advanced method is needed and **what** it buys compared to simpler alternatives.
