---
name: ventilation-classification
description: Classify ventilation status into InvasiveVent, NonInvasiveVent, HFNC, SupplementalOxygen, Tracheostomy, or None from charting data. Use for ventilation duration analysis, respiratory support characterization, or as a component of severity scores (SOFA respiratory, OASIS).
tier: validated
category: clinical
---

# Ventilation Classification

Classifies each ICU charting observation into a ventilation status category and groups consecutive observations into ventilation episodes. This concept is used directly by SOFA (respiratory component requires mechanical ventilation for scores 3-4), OASIS, and many other severity scores and research definitions.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## When to Use This Skill

- Determining ventilation type and duration for ICU stays
- SOFA respiratory scoring (requires knowing if patient is on invasive mechanical ventilation)
- Weaning studies (tracking transitions between ventilation modes)
- Respiratory support characterization in cohort studies
- Any task requiring classification of oxygen delivery or ventilator data

## Ventilation Categories

| Category | Description | Examples |
|----------|-------------|---------|
| **Tracheostomy** | Patient has a tracheostomy tube | Tracheostomy tube, Trach mask |
| **InvasiveVent** | Invasive mechanical ventilation via endotracheal tube or ventilator mode | Endotracheal tube, CMV, SIMV, PRVC/AC, VOL/AC, etc. |
| **NonInvasiveVent** | Non-invasive positive pressure ventilation | BiPAP mask, CPAP mask, NIV modes |
| **HFNC** | High-flow nasal cannula | High flow nasal cannula |
| **SupplementalOxygen** | Low-flow or standard oxygen delivery | Nasal cannula, Non-rebreather, Face tent, Venti mask |
| **None** | No supplemental oxygen (room air) | None |

### Classification Priority

When multiple indicators are present simultaneously, the classification follows this priority (highest first):

1. **Tracheostomy** — `o2_delivery_device_1` is 'Tracheostomy tube' or 'Trach mask '
2. **InvasiveVent** — `o2_delivery_device_1` is 'Endotracheal tube' OR any invasive ventilator mode present
3. **NonInvasiveVent** — `o2_delivery_device_1` is 'Bipap mask ' or 'CPAP mask ' OR Hamilton NIV modes
4. **HFNC** — `o2_delivery_device_1` is 'High flow nasal cannula'
5. **SupplementalOxygen** — Other oxygen delivery devices
6. **None** — `o2_delivery_device_1` is 'None'

## Classification Rules

### By Oxygen Delivery Device (`o2_delivery_device_1`)

| Device Value | Category |
|-------------|----------|
| `'Tracheostomy tube'` | Tracheostomy |
| `'Trach mask '` | Tracheostomy |
| `'Endotracheal tube'` | InvasiveVent |
| `'Bipap mask '` | NonInvasiveVent |
| `'CPAP mask '` | NonInvasiveVent |
| `'High flow nasal cannula'` | HFNC |
| `'Non-rebreather'` | SupplementalOxygen |
| `'Face tent'` | SupplementalOxygen |
| `'Aerosol-cool'` | SupplementalOxygen |
| `'Venti mask '` | SupplementalOxygen |
| `'Medium conc mask '` | SupplementalOxygen |
| `'Ultrasonic neb'` | SupplementalOxygen |
| `'Vapomist'` | SupplementalOxygen |
| `'Oxymizer'` | SupplementalOxygen |
| `'High flow neb'` | SupplementalOxygen |
| `'Nasal cannula'` | SupplementalOxygen |
| `'None'` | None |

Note: Some device values have trailing spaces (e.g., `'Trach mask '`, `'Bipap mask '`, `'Venti mask '`). These must be matched exactly.

### By Ventilator Mode (`ventilator_mode`)

All of these map to **InvasiveVent**:

`'(S) CMV'`, `'APRV'`, `'APRV/Biphasic+ApnPress'`, `'APRV/Biphasic+ApnVol'`, `'APV (cmv)'`, `'Ambient'`, `'Apnea Ventilation'`, `'CMV'`, `'CMV/ASSIST'`, `'CMV/ASSIST/AutoFlow'`, `'CMV/AutoFlow'`, `'CPAP/PPS'`, `'CPAP/PSV'`, `'CPAP/PSV+Apn TCPL'`, `'CPAP/PSV+ApnPres'`, `'CPAP/PSV+ApnVol'`, `'MMV'`, `'MMV/AutoFlow'`, `'MMV/PSV'`, `'MMV/PSV/AutoFlow'`, `'P-CMV'`, `'PCV+'`, `'PCV+/PSV'`, `'PCV+Assist'`, `'PRES/AC'`, `'PRVC/AC'`, `'PRVC/SIMV'`, `'PSV/SBT'`, `'SIMV'`, `'SIMV/AutoFlow'`, `'SIMV/PRES'`, `'SIMV/PSV'`, `'SIMV/PSV/AutoFlow'`, `'SIMV/VOL'`, `'SYNCHRON MASTER'`, `'SYNCHRON SLAVE'`, `'VOL/AC'`

### By Hamilton Ventilator Mode (`ventilator_mode_hamilton`)

**InvasiveVent**: `'APRV'`, `'APV (cmv)'`, `'Ambient'`, `'(S) CMV'`, `'P-CMV'`, `'SIMV'`, `'APV (simv)'`, `'P-SIMV'`, `'VS'`, `'ASV'`

**NonInvasiveVent**: `'DuoPaP'`, `'NIV'`, `'NIV-ST'`

## Episode Boundary Detection

Individual charting observations are grouped into ventilation episodes using these rules:

1. **New episode starts when**:
   - First observation for a stay (no previous observation)
   - Gap of >= 14 hours between consecutive observations of the same status
   - Ventilation status changes from previous observation

2. **Episode boundaries**:
   - `starttime` = earliest charttime in the episode
   - `endtime` = latest charttime in the episode (or the next observation's charttime if it's within 14 hours)
   - Single-observation episodes (starttime == endtime) are excluded

3. **14-hour gap rule**: If two consecutive observations of the same ventilation status are more than 14 hours apart, they are treated as separate episodes. This prevents spanning overnight gaps where ventilation may have been discontinued and restarted.

## Required Tables for Custom Calculation

### Raw Mode (from chartevents directly)

**Ventilator settings** — itemids from `mimiciv_icu.chartevents`:
- 224688: Respiratory Rate (Set)
- 224689: Respiratory Rate (spontaneous)
- 224690: Respiratory Rate (Total)
- 224687: Minute Volume
- 224684: Tidal Volume (set)
- 224685: Tidal Volume (observed)
- 224686: Tidal Volume (spontaneous)
- 224696: Plateau Pressure
- 220339, 224700: PEEP
- 223835: Inspired O2 Fraction (FiO2)
- 223849: Ventilator Mode
- 229314: Ventilator Mode (Hamilton)
- 223848: Ventilator Type
- 224691: Flow Rate

**Oxygen delivery** — itemids from `mimiciv_icu.chartevents`:
- 223834, 227582: O2 Flow
- 227287: O2 Flow (additional)
- 226732: O2 Delivery Device

For classification, the critical itemids are:
- **223849** (Ventilator Mode) — text value maps to InvasiveVent
- **229314** (Ventilator Mode Hamilton) — text value maps to InvasiveVent or NonInvasiveVent
- **226732** (O2 Delivery Device) — text value maps to all categories

## Critical Implementation Notes

1. **Trailing Spaces in Device Names**: Several `o2_delivery_device_1` values have trailing spaces (e.g., `'Trach mask '`, `'Bipap mask '`, `'Venti mask '`, `'Medium conc mask '`). These must be matched exactly as stored in MIMIC-IV.

2. **Priority of Device over Mode**: Tracheostomy and Endotracheal tube (from `o2_delivery_device_1`) take priority over ventilator mode classification. A patient on a tracheostomy with a ventilator mode set is classified as Tracheostomy, not InvasiveVent.

3. **CPAP/PSV Modes Are Invasive**: In MIMIC-IV charting conventions, CPAP/PSV and related modes (CPAP/PPS, CPAP/PSV+ApnPres, etc.) are recorded as ventilator modes on patients with endotracheal tubes. These are classified as InvasiveVent, not NonInvasiveVent. Non-invasive CPAP is identified by the CPAP mask device, not the ventilator mode.

4. **Hamilton vs Standard Modes**: MIMIC-IV has two ventilator mode columns — `ventilator_mode` (standard ventilators) and `ventilator_mode_hamilton` (Hamilton ventilators). These are combined with COALESCE for classification purposes.

5. **Single-Observation Episodes Excluded**: Episodes where starttime equals endtime are filtered out. This removes transient or erroneous observations that don't represent sustained ventilation periods.

6. **NULL Ventilation Status Excluded**: Observations that don't match any classification rule produce NULL status and are excluded from episode detection.

7. **LAG Partitioning**: The gap detection LAG function partitions by `(stay_id, ventilation_status)` — not just `stay_id`. This means the 14-hour gap rule applies within each status category separately.

## References

- Johnson AEW et al. "MIMIC-IV, a freely accessible electronic health record dataset." Scientific Data. 2023;10(1):1.
- MIT-LCP mimic-code repository: ventilation concept definition.
