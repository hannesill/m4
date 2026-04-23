---
name: sirs-criteria
description: Calculate SIRS (Systemic Inflammatory Response Syndrome) criteria for ICU patients. Use for historical sepsis definitions, inflammatory response assessment, or research comparing SIRS vs Sepsis-3.
---

# SIRS Criteria Calculation

The Systemic Inflammatory Response Syndrome (SIRS) criteria quantify the body's inflammatory response to insult — both **infectious and non-infectious** (trauma, burns, pancreatitis, major surgery). Defined by the 1992 ACCP/SCCM Consensus Conference, SIRS was historically used as part of the sepsis definition (SIRS >= 2 + suspected infection).

The 2016 SCCM Sepsis-3 consensus **removed SIRS from the sepsis definition**, replacing it with SOFA-based criteria (SOFA >= 2 + suspected infection). The rationale: SIRS criteria are overly sensitive and poorly specific for the dysregulated host response that defines sepsis. SIRS remains relevant for research comparing definitions, studying inflammatory response independent of infection, and legacy quality metrics.


## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

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

2. **PaCO2 Source**: Should use only arterial blood gas specimens. Venous or mixed venous PaCO2 is unreliable for this criterion. In MIMIC-IV, filter by specimen type `'ART.'` using the specimen itemid 52033 in `labevents`.

3. **Time Window**: The original definition does not specify a time window. Most ICU implementations use the first 24 hours, but the criteria can be applied to any clinically relevant window. Include measurements from 6 hours before ICU admission to capture ED data.

4. **Missing Data Imputation**: Missing components should be imputed as 0 (normal). This may underestimate true SIRS in patients with incomplete charting.

5. **Temperature Units**: MIMIC-IV stores temperature in both Fahrenheit (itemid 223761) and Celsius (itemid 223762). Convert Fahrenheit to Celsius before applying thresholds.

## MIMIC-IV Raw Table Implementation

The components can be extracted from raw MIMIC-IV tables:

| Component | Source Table | ItemID(s) | Notes |
|-----------|-------------|-----------|-------|
| Temperature (°C) | `mimiciv_icu.chartevents` | 223762 | Direct Celsius |
| Temperature (°F) | `mimiciv_icu.chartevents` | 223761 | Convert: (°F - 32) / 1.8 |
| Heart Rate | `mimiciv_icu.chartevents` | 220045 | Valid range: 0-300 |
| Respiratory Rate | `mimiciv_icu.chartevents` | 220210, 224690 | Valid range: 0-70 |
| PaCO2 | `mimiciv_hosp.labevents` | 50818 | Arterial only (specimen 52033 = 'ART.') |
| WBC | `mimiciv_hosp.labevents` | 51300, 51301 | x10^9/L |
| Bands | `mimiciv_hosp.labevents` | 51144 | % immature neutrophils |

**Key notes:**
- Use `mimiciv_icu.icustays` as the base table (one row per ICU stay).
- Join `chartevents` on `stay_id`; join `labevents` on `subject_id` with time filtering.
- For PaCO2: identify arterial specimens via itemid 52033 (`value = 'ART.'`) in `labevents`, then filter pCO2 values to those specimen_ids.
- Apply min/max aggregation within the time window per stay.

## References

- Bone RC et al. "Definitions for sepsis and organ failure and guidelines for the use of innovative therapies in sepsis." Chest. 1992;101(6):1644-1655.
- American College of Chest Physicians/SCCM Consensus Conference. Crit Care Med. 1992;20(6):864-874.
- Singer M et al. "The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3)." JAMA. 2016;315(8):801-810.
