# Assumptions and Limitations

## Overview

Every statistical method has assumptions. When assumptions are violated, results may be biased, inefficient, or misleading. This reference lists key assumptions by method, how to check them, and what to do when they fail.

---

## Linear Regression (OLS)

### Assumptions

| Assumption | What It Means | How to Check | Consequence if Violated |
|------------|---------------|--------------|------------------------|
| Linearity | Relationship is linear | Residual vs fitted plot | Biased estimates |
| Independence | Errors are independent | Study design, Durbin-Watson | Wrong SEs, invalid inference |
| Homoscedasticity | Constant error variance | Residual plot, Breusch-Pagan | Inefficient estimates, wrong SEs |
| Normality | Residuals are normal | Q-Q plot, Shapiro-Wilk | Invalid inference (small n) |
| No multicollinearity | Predictors not highly correlated | VIF (>10 concerning) | Unstable estimates |

### Remedies

| Violation | Options |
|-----------|---------|
| Non-linearity | Transform variables, add polynomial terms, use GAM |
| Heteroscedasticity | Robust (HC) standard errors, WLS, transform outcome |
| Non-independence | Cluster-robust SEs, mixed models, GEE |
| Non-normality | Bootstrap CIs, transform outcome (large n usually OK) |
| Multicollinearity | Remove redundant predictors, combine, regularization |

---

## Logistic Regression

### Assumptions

| Assumption | What It Means | How to Check | Consequence if Violated |
|------------|---------------|--------------|------------------------|
| Linearity in log-odds | Linear relationship on logit scale | Box-Tidwell test | Biased estimates |
| Independence | Observations are independent | Study design | Wrong SEs |
| No perfect separation | Both outcomes exist for all predictor values | Check for infinite coefficients | Model fails to converge |
| No multicollinearity | Predictors not highly correlated | VIF | Unstable estimates |

### Remedies

| Violation | Options |
|-----------|---------|
| Non-linearity | Splines, categorize continuous variables |
| Non-independence | GEE, mixed logistic models, cluster-robust SEs |
| Perfect separation | Firth's penalized logistic regression, exact logistic |
| Multicollinearity | Remove predictors, regularization (LASSO) |

### Additional Considerations

- **Rare events:** When outcome prevalence <10%, consider exact logistic or Firth's method
- **Sample size rule of thumb:** ~10-20 events per predictor variable

---

## Cox Proportional Hazards

### Assumptions

| Assumption | What It Means | How to Check | Consequence if Violated |
|------------|---------------|--------------|------------------------|
| Proportional hazards | Hazard ratio constant over time | Schoenfeld residuals, log-log plot | HR is time-averaged, misleading |
| Non-informative censoring | Censoring unrelated to outcome | Cannot test; assess plausibility | Biased estimates |
| Linearity | Continuous covariates linear in log-hazard | Martingale residuals | Biased estimates |
| Independence | Observations independent | Study design | Wrong SEs |

### Checking Proportional Hazards

1. **Schoenfeld residual test:** `cox.zph()` in R, `proportional_hazard_test` in lifelines
2. **Log-log plot:** Parallel lines indicate PH holds
3. **Include time interaction:** If significant, PH violated

### Remedies

| Violation | Options |
|-----------|---------|
| PH violated (categorical) | Stratified Cox |
| PH violated (continuous) | Time-varying coefficient, piecewise Cox |
| PH generally problematic | AFT models, RMST |
| Informative censoring | Sensitivity analysis, consider competing risks |
| Non-linearity | Splines, categorize |

---

## Poisson Regression

### Assumptions

| Assumption | What It Means | How to Check | Consequence if Violated |
|------------|---------------|--------------|------------------------|
| Mean = Variance | Equidispersion | Compare mean and variance, deviance/df | Wrong SEs (usually too small) |
| Independence | Events are independent | Study design | Wrong SEs |
| Log-linear relationship | Correct functional form | Residual plots | Biased estimates |

### Checking Overdispersion

- Dispersion ratio = Pearson χ² / df (or deviance / df)
- Ratio > 1.5 suggests overdispersion

### Remedies

| Violation | Options |
|-----------|---------|
| Overdispersion | Negative binomial, quasi-Poisson |
| Excess zeros | Zero-inflated Poisson, hurdle model |
| Non-independence | GEE, mixed Poisson models |

---

## IPTW / Propensity Score Methods

### Assumptions

| Assumption | What It Means | How to Check | Consequence if Violated |
|------------|---------------|--------------|------------------------|
| No unmeasured confounding | All confounders in PS model | Cannot test; defend with theory | Biased causal estimate |
| Positivity | All covariate patterns have treated & untreated | Check PS distribution overlap | Extreme weights, instability |
| Correct PS model | Propensity model well-specified | Covariate balance after weighting | Residual confounding |
| Consistency | Well-defined treatment | Conceptual | Effect not interpretable |

### Checking Balance

After weighting or matching, check:
- Standardized mean differences (SMD < 0.1 ideal)
- Variance ratios (0.5-2.0 acceptable)
- Visual: distribution overlap plots

### Remedies

| Violation | Options |
|-----------|---------|
| Poor overlap | Trim extreme weights, match instead of weight |
| Residual imbalance | Adjust PS model, add interactions |
| Extreme weights | Truncate or stabilize weights |
| Unmeasured confounding | Sensitivity analysis (E-value), different design |

---

## Mixed Effects Models

### Assumptions

| Assumption | What It Means | How to Check | Consequence if Violated |
|------------|---------------|--------------|------------------------|
| Random effects normal | Random effects follow normal distribution | Q-Q plot of BLUPs | Usually robust |
| Residuals normal & homoscedastic | Standard regression assumptions | Residual plots | Biased SEs |
| Correct random structure | Random effects specified correctly | Model comparison (AIC/BIC) | Biased estimates or SEs |
| Independence of clusters | Clusters are independent | Study design | Wrong inference |

### Remedies

| Violation | Options |
|-----------|---------|
| Non-normal random effects | Bootstrap, robust SEs |
| Heteroscedasticity | Model variance by group |
| Uncertain random structure | Compare models, keep parsimonious |

---

## Machine Learning Models

### Considerations (Not Traditional Assumptions)

| Issue | What It Means | How to Address |
|-------|---------------|----------------|
| Overfitting | Model memorizes training data | Cross-validation, regularization, early stopping |
| Data leakage | Future info in training | Careful feature engineering, temporal splits |
| Class imbalance | Rare outcome | SMOTE, class weights, AUPRC instead of AUROC |
| Feature scaling | Algorithms sensitive to scale | Standardize/normalize (tree-based models don't need) |
| Missing data | Incomplete features | Imputation, models that handle missingness |

### Validation Requirements

- **Always** use held-out test set or cross-validation
- **Never** report training metrics as final performance
- **Patient-level splits** to avoid data leakage across admissions

---

## Universal Considerations

### Sample Size

| Method | Rule of Thumb |
|--------|---------------|
| Linear regression | 10-20 observations per predictor |
| Logistic regression | 10-20 events per predictor |
| Cox regression | 10-20 events per predictor |
| ML models | Hundreds to thousands; more for complex models |

### Missing Data

| Mechanism | Description | Appropriate Approach |
|-----------|-------------|---------------------|
| MCAR | Missingness completely random | Complete case (but loses power) |
| MAR | Missingness depends on observed data | Multiple imputation |
| MNAR | Missingness depends on missing value | Sensitivity analysis, pattern mixture |

### Multiple Testing

If testing multiple hypotheses:
- Pre-specify primary outcome
- Bonferroni: α / number of tests (conservative)
- Benjamini-Hochberg: Controls false discovery rate (less conservative)
- Report all tests performed, not just significant ones

---

## Quick Reference: Assumption → Check → Fix

| Assumption | Quick Check | Quick Fix |
|------------|-------------|-----------|
| Linearity | Residual vs fitted plot | Transform, splines, GAM |
| Homoscedasticity | Residual spread pattern | Robust SEs, WLS |
| Normality | Q-Q plot | Bootstrap (or ignore if n>30) |
| Independence | Study design | Cluster methods, GEE |
| PH (Cox) | Schoenfeld test | Stratify, time-varying, AFT |
| Overdispersion | Mean vs variance | Negative binomial |
| PS overlap | Weight distribution | Trim, match, bound |
| Multicollinearity | VIF | Remove, combine, regularize |
