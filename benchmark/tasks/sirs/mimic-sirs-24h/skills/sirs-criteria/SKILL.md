---
name: sirs-criteria
description: Calculate SIRS (Systemic Inflammatory Response Syndrome) criteria for ICU patients. Use for historical sepsis definitions, inflammatory response assessment, or research comparing SIRS vs Sepsis-3.
---

# SIRS Criteria Calculation

The Systemic Inflammatory Response Syndrome (SIRS) criteria quantify the body's inflammatory response to insult — both **infectious and non-infectious** (trauma, burns, pancreatitis, major surgery). Defined by the 1992 ACCP/SCCM Consensus Conference, SIRS was historically used as part of the sepsis definition (SIRS >= 2 + suspected infection).

The 2016 SCCM Sepsis-3 consensus **removed SIRS from the sepsis definition**, replacing it with SOFA-based criteria (SOFA >= 2 + suspected infection). The rationale: SIRS criteria are overly sensitive and poorly specific for the dysregulated host response that defines sepsis. SIRS remains relevant for research comparing definitions, studying inflammatory response independent of infection, and legacy quality metrics.

## SIRS Criteria (0-4 Points)

Each criterion met = 1 point:

| Criterion | Threshold |
|-----------|-----------|
| **Temperature** | < 36°C OR > 38°C |
| **Heart Rate** | > 90 bpm |
| **Respiratory** | RR > 20/min OR PaCO2 < 32 mmHg |
| **WBC** | < 4 OR > 12 x10^9/L OR > 10% bands |

**SIRS Positive**: >= 2 criteria met

## Critical Implementation Notes

1. **Band Forms**: The presence of > 10% immature neutrophils (bands) satisfies the WBC criterion, even if total WBC is within normal range. Band counts are variably documented across datasets.

2. **PaCO2 Source**: Should use only arterial blood gas specimens. Venous or mixed venous PaCO2 is unreliable for this criterion.

3. **Time Window**: The original definition does not specify a time window. Most ICU implementations use the first 24 hours, but the criteria can be applied to any clinically relevant window.

4. **Missing Data Imputation**: Missing components should be imputed as 0 (normal). This may underestimate true SIRS in patients with incomplete charting.

## MIMIC-IV Implementation

For MIMIC-IV, the components come from first-day derived tables:

| Component | Source Table | Column(s) |
|-----------|-------------|-----------|
| Temperature | `mimiciv_derived.first_day_vitalsign` | `temperature_min`, `temperature_max` |
| Heart Rate | `mimiciv_derived.first_day_vitalsign` | `heart_rate_max` |
| Respiratory Rate | `mimiciv_derived.first_day_vitalsign` | `resp_rate_max` |
| PaCO2 | `mimiciv_derived.first_day_bg_art` | `pco2_min` |
| WBC | `mimiciv_derived.first_day_lab` | `wbc_min`, `wbc_max` |
| Bands | `mimiciv_derived.first_day_lab` | `bands_max` |

**Key notes:**
- PaCO2 uses arterial specimens only (from `first_day_bg_art`, not `first_day_bg`).
- Bands are rarely documented in MIMIC-IV — the WBC criterion relies almost entirely on total WBC count.
- Calculate one row per ICU stay using `mimiciv_icu.icustays` as the base.

## References

- Bone RC et al. "Definitions for sepsis and organ failure and guidelines for the use of innovative therapies in sepsis." Chest. 1992;101(6):1644-1655.
- American College of Chest Physicians/SCCM Consensus Conference. Crit Care Med. 1992;20(6):864-874.
- Singer M et al. "The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3)." JAMA. 2016;315(8):801-810.
