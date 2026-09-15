---
name: sirs-criteria
description: Calculate SIRS (Systemic Inflammatory Response Syndrome) criteria for ICU patients. Use for historical sepsis definitions, inflammatory response assessment, or research comparing SIRS vs Sepsis-3.
tier: validated
category: clinical
kind: domain
---

# SIRS Criteria Calculation

The Systemic Inflammatory Response Syndrome (SIRS) criteria quantify the body's inflammatory response to insult — both **infectious and non-infectious** (trauma, burns, pancreatitis, major surgery). Defined by the 1992 ACCP/SCCM Consensus Conference, SIRS was historically used as part of the sepsis definition (SIRS >= 2 + suspected infection).

The 2016 SCCM Sepsis-3 consensus **removed SIRS from the sepsis definition**, replacing it with SOFA-based criteria (SOFA >= 2 + suspected infection). The rationale: SIRS criteria are overly sensitive and poorly specific for the dysregulated host response that defines sepsis. SIRS remains relevant for research comparing definitions, studying inflammatory response independent of infection, and legacy quality metrics.

## When to Use This Skill

- Historical sepsis research (pre-Sepsis-3 definitions)
- Inflammatory response quantification (infectious and non-infectious)
- Comparing SIRS-based vs Sepsis-3 sepsis definitions
- Identifying patients with systemic inflammation regardless of etiology
- Quality metrics using legacy definitions

## SIRS Criteria (0-4 Points)

Each criterion met = 1 point:

| Criterion | Threshold |
|-----------|-----------|
| **Temperature** | < 36°C OR > 38°C |
| **Heart Rate** | > 90 bpm |
| **Respiratory** | RR > 20/min OR PaCO2 < 32 mmHg |
| **WBC** | < 4 OR > 12 x10^9/L OR > 10% bands |

**SIRS Positive**: >= 2 criteria met

### Pediatric SIRS

The adult thresholds above do not apply to pediatric populations. The 2005 International Pediatric Sepsis Consensus Conference (IPSCC, Goldstein et al.) defines age-adjusted SIRS thresholds for heart rate, respiratory rate, WBC count, and temperature. Normal ranges for HR and RR vary substantially by age group (e.g., tachycardia threshold is >180 bpm in neonates vs >90 bpm in adults). This skill covers adult definitions only.

## Critical Implementation Notes

1. **Band Forms**: The presence of > 10% immature neutrophils (bands) satisfies the WBC criterion, even if total WBC is within normal range. Band counts are variably documented across datasets.

2. **PaCO2 Source**: Should use only arterial blood gas specimens. Venous or mixed venous PaCO2 is unreliable for this criterion.

3. **Time Window**: The original definition does not specify a time window. Most ICU implementations use the first 24 hours, but the criteria can be applied to any clinically relevant window.

4. **Non-Infectious Triggers**: SIRS >= 2 alone does NOT indicate infection. Common non-infectious causes include major surgery, trauma, burns, pancreatitis, and adrenal crisis. The pre-Sepsis-3 "sepsis" definition required SIRS >= 2 PLUS suspected infection.

## General Limitations

1. **Low Specificity for Sepsis**: When used as a sepsis screen (the pre-2016 definition), SIRS has poor specificity — many non-infectious conditions trigger >= 2 criteria. In ICU populations, a large proportion of patients meet SIRS criteria regardless of infection status. This was the primary motivation for Sepsis-3's switch to SOFA.

2. **Sensitivity Gaps**: Immunosuppressed, elderly, and chronically ill patients may not mount a classic inflammatory response despite active infection, leading to false negatives. Kaukonen et al. (2015) found that 1 in 8 patients with infection and organ failure did not meet >= 2 SIRS criteria ("SIRS-negative sepsis"), and these patients still had significant mortality.

3. **Superseded by Sepsis-3**: The 2016 consensus found SIRS criteria had poor discriminant validity for sepsis. SOFA-based Sepsis-3 criteria are now standard. Use SIRS for historical comparison only.

4. **Binary Thresholds**: Each criterion is binary (met/not met), losing information about degree of derangement. A heart rate of 91 and 150 both score 1 point.

## Dataset Availability

### MIMIC-IV

SIRS is available as a pre-computed derived table. Materialize with:

```bash
m4 init-derived mimic-iv          # All derived tables including sirs
```

The derived `mimiciv_derived.sirs` table provides the total `sirs` score (0-4) and individual component scores (`temp_score`, `heart_rate_score`, `resp_score`, `wbc_score`).

BigQuery users already have this table via `physionet-data.mimiciv_derived.sirs` without running `init-derived`.

**MIMIC-IV implementation details:**
- **PaCO2**: Uses arterial specimens only from `first_day_bg_art` derived table.
- **Missing Data Imputation**: Missing components are imputed as 0 (normal). This may underestimate true SIRS in patients with incomplete charting.
- **Band Forms**: Extracted from `first_day_lab.bands_max`, but bands are rarely documented in MIMIC-IV (most stays will have NULL). In practice, the WBC criterion relies almost entirely on total WBC count.

**MIMIC-IV limitations:**
- Calculated over the first 24 hours of ICU stay only. Does not capture ED SIRS or SIRS onset at other time points.
- Missing-as-normal imputation biases toward lower SIRS scores, particularly for patients with short stays or incomplete lab panels.

### eICU

SIRS is **not pre-computed** in eICU. The four components can be derived from raw tables:

| Component | eICU Source |
|-----------|-------------|
| Temperature | `vitalperiodic.temperature` / `vitalaperiodic.temperature` |
| Heart Rate | `vitalperiodic.heartrate` |
| Respiratory Rate | `vitalperiodic.respiratoryrate` |
| PaCO2 | `lab` (labname = `'paCO2'`) |
| WBC | `lab` (labname = `'WBC x 1000'`) |
| Bands | `lab` (labname = `'-bands'`) — note leading dash |

**eICU limitations:**
- **Band forms**: Available via `labname = '-bands'` (note the leading dash), but completeness varies by site. When bands are not documented, the WBC criterion relies on total count only.
- **PaCO2 specimen type**: The `lab` table does not reliably distinguish arterial from venous blood gas specimens. May include venous PaCO2 values, which are systematically higher and could produce false negatives for the respiratory criterion.
- **Multi-site variability**: Charting frequency and completeness vary across the 208 hospitals, which may affect missing data patterns.

An eICU script is not yet available.

## Example: SIRS Distribution

```sql
SELECT
    sirs,
    COUNT(*) AS n_patients,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct
FROM mimiciv_derived.sirs
GROUP BY sirs
ORDER BY sirs;
```

## Example: Compare SIRS vs Sepsis-3 Classification

```sql
WITH classifications AS (
    SELECT
        si.stay_id,
        si.sirs >= 2 AS sirs_positive,
        s3.sepsis3
    FROM mimiciv_derived.sirs si
    LEFT JOIN mimiciv_derived.sepsis3 s3
        ON si.stay_id = s3.stay_id
    WHERE s3.stay_id IS NOT NULL  -- has suspected infection
)
SELECT
    sirs_positive,
    sepsis3,
    COUNT(*) AS n
FROM classifications
GROUP BY sirs_positive, sepsis3
ORDER BY 1, 2;
```

## Related Skills

- [sepsis-3-cohort](../sepsis-3-cohort/SKILL.md) — Current Sepsis-3 definition (SOFA >= 2 + suspected infection); pre-computed in `mimiciv_derived.sepsis3`
- [suspicion-of-infection](../suspicion-of-infection/SKILL.md) — Infection component used by both SIRS-based and Sepsis-3 definitions
- [sofa-score](../sofa-score/SKILL.md) — SOFA calculation that replaced SIRS in the Sepsis-3 definition

## References

- Bone RC et al. "Definitions for sepsis and organ failure and guidelines for the use of innovative therapies in sepsis." Chest. 1992;101(6):1644-1655.
- American College of Chest Physicians/SCCM Consensus Conference. Crit Care Med. 1992;20(6):864-874.
- Kaukonen KM et al. "Systemic inflammatory response syndrome criteria in defining severe sepsis." N Engl J Med. 2015;372(17):1629-1638.
- Singer M et al. "The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3)." JAMA. 2016;315(8):801-810.
- Goldstein B et al. "International pediatric sepsis consensus conference: Definitions for sepsis and organ dysfunction in pediatrics." Pediatr Crit Care Med. 2005;6(1):2-8.
