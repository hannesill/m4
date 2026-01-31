# Standardized Mean Difference (SMD) Interpretation Guide

## What is SMD?

SMD measures the difference in distributions between two groups, standardized by the pooled standard deviation. In EquiFlow, it quantifies how much each variable's distribution changes after applying an exclusion criterion.

## SMD Formula

**Continuous variables:**
```
SMD = (mean₁ - mean₂) / √[(SD₁² + SD₂²) / 2]
```

**Categorical variables (proportion p):**
```
SMD = (p₁ - p₂) / √[(p₁(1-p₁) + p₂(1-p₂)) / 2]
```

## Interpretation Thresholds

| |SMD| | Interpretation | Clinical Significance | Action |
|-------|----------------|----------------------|--------|
| < 0.1 | Negligible | No meaningful difference | ✓ No concern |
| 0.1 - 0.2 | Small | Minor imbalance | Monitor, document |
| **0.2 - 0.5** | **Medium** | **Potential selection bias** | ⚠️ Investigate |
| > 0.5 | Large | Serious imbalance | ⛔ Reconsider criteria |

## Equity Variables - What to Watch

### Demographics
| Variable | High SMD Concern |
|----------|------------------|
| **Race** | Certain racial groups disproportionately excluded |
| **Gender** | Sex-based exclusion patterns |
| **Age** | Expected for age-based criteria, but watch magnitude |

### Socioeconomic
| Variable | High SMD Concern |
|----------|------------------|
| **Insurance** | Uninsured/Medicaid patients excluded more |
| **Language** | Non-English speakers excluded |
| **Marital status** | Single/widowed patients affected |

### Outcome
| Variable | High SMD Concern |
|----------|------------------|
| **Mortality** | Sicker patients excluded → survivorship bias |

## Example Interpretation

```
SMD Table (after "Complete lab data" exclusion):

Variable          SMD     Interpretation
────────────────────────────────────────
gender            0.05    ✓ Balanced
race              0.28    ⚠️ Racial disparity in missing labs
insurance         0.35    ⚠️ Uninsured have more missing data
language          0.42    ⚠️ Non-English speakers excluded more
age               0.08    ✓ Balanced
los              -0.12    ~ Minor (shorter stays have more missing)
mortality         0.31    ⛔ Deaths have more missing data
```

**Interpretation:** 
- "Complete lab data" criterion disproportionately excludes:
  - Certain racial groups
  - Uninsured patients
  - Non-English speakers
  - Patients who died
- This suggests **missing data is NOT random** - it correlates with socioeconomic factors and severity
- Final cohort may not represent the true patient population

## Recommendations

### When SMD > 0.2 is Found

1. **Document prominently** in your methods section
2. **Consider alternatives:**
   - Imputation instead of complete case analysis
   - Relaxing the criterion
   - Sensitivity analysis with/without the criterion
3. **Adjust downstream analysis:**
   - Include affected variables as covariates
   - Use propensity score methods
   - Report stratified results

### Reporting Template

> "Application of [criterion] resulted in exclusion of N patients. 
> This step showed differential impact on [variable] (SMD = X.XX), 
> with [group] being disproportionately excluded. 
> We addressed this by [mitigation strategy]."

## Common Patterns

### Pattern 1: Missing Data Bias
```
Criterion: "Complete vital signs"
High SMD: race (0.25), insurance (0.30), mortality (0.35)
Meaning: Marginalized groups have more missing data
```

### Pattern 2: Age-Related Exclusion
```
Criterion: "Age ≥ 18"
High SMD: age (0.80) - expected
         race (0.05) - OK
         mortality (0.02) - OK
Meaning: Age criterion affects only age (as expected)
```

### Pattern 3: Severity-Based Exclusion
```
Criterion: "ICU stay ≥ 24 hours"
High SMD: mortality (0.45), los (0.60)
         race (0.08), insurance (0.10)
Meaning: Short stays (often deaths or transfers) excluded
         → Survivorship bias
```

## References

- Austin PC. Balance diagnostics for comparing distributions in propensity-score matched samples. Stat Med. 2009;28(25):3083-107.
- Ellen JG, et al. Participant flow diagrams for health equity in AI. J Biomed Inform. 2024;152:104631.
- Zhang Z, et al. Balance diagnostics after propensity score matching. Ann Transl Med. 2019;7(1):16.
