---
name: apsiii-score
description: Calculate APACHE III (Acute Physiology Score III) for ICU patients. Use for mortality prediction, severity stratification, case-mix adjustment, or risk-adjusted outcome comparisons.
tier: validated
category: clinical
---

# APACHE III (APS III) Score Calculation

The Acute Physiology Score III (APS III) is the physiological component of APACHE III. It measures patient severity of illness on the first day of ICU stay and provides hospital mortality probability estimates.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## When to Use This Skill

- Hospital mortality prediction
- Severity stratification and risk adjustment
- Case-mix adjustment for benchmarking
- Comparing outcomes across ICUs or time periods
- Research cohort severity matching

## Score Components

The APS III uses the **worst values** from the first 24 hours of ICU stay:

### Vital Signs
- Heart rate (normal reference: 75 bpm)
- Mean blood pressure (normal reference: 90 mmHg)
- Temperature (normal reference: 38C)
- Respiratory rate (normal reference: 19 breaths/min)

### Laboratory Values
- Hematocrit (normal reference: 45.5%)
- WBC (normal reference: 11.5 x10^9/L)
- Creatinine (normal reference: 1.0 mg/dL)
- BUN (scored from 0, higher is worse)
- Sodium (normal reference: 145.5 mEq/L)
- Albumin (normal reference: 3.5 g/dL)
- Bilirubin (scored from 0, higher is worse)
- Glucose (normal reference: 130 mg/dL)

### Blood Gas
- PaO2 (for non-ventilated patients with FiO2 < 50%)
- A-aDO2 (for ventilated patients with FiO2 >= 50%)
- pH and PaCO2 interaction scoring

### Other
- GCS (complex interaction between eye, verbal, motor components)
- Urine output (24-hour total)
- Mechanical ventilation status
- Acute renal failure flag

## Critical Implementation Notes

1. **Worst Value Definition**: "Worst" means furthest from a predefined normal reference value, not simply min or max. For example:
   - Heart rate worst = MAX(|HR - 75|)
   - If equally distant from normal, use the higher score

2. **Acute Renal Failure (ARF) Modifier**: ARF is defined as:
   - Creatinine >= 1.5 mg/dL AND
   - Urine output < 410 mL/day AND
   - No chronic kidney disease (CKD stages 4-6)

3. **Ventilation Interaction**:
   - For ventilated patients with FiO2 >= 50%: use A-aDO2
   - For non-ventilated patients with FiO2 < 50%: use PaO2
   - Only arterial blood gas specimens are used

4. **pH/PaCO2 Interaction**: The acid-base score requires both pH and PaCO2 together - different combinations yield different scores.

5. **GCS Scoring**: Complex interaction matrix between eye, verbal, and motor scores. Sedated/intubated patients default to normal (score 0).

6. **Temperature**: Axillary measurements should theoretically be increased by 1 degree, but this is not implemented.

7. **Mortality Probability**: Calculated using logistic regression:
   ```
   apsiii_prob = 1 / (1 + exp(-(-4.4360 + 0.04726 * apsiii)))
   ```

## References

- Knaus WA et al. "The APACHE III prognostic system: Risk prediction of hospital mortality for critically ill hospitalized adults." Chest. 1991;100(6):1619-1636.
- Johnson AEW. "Mortality prediction and acuity assessment in critical care." University of Oxford. 2015. (Calibration equation source)
