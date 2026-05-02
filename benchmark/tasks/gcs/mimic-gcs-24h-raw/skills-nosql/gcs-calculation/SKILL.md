---
name: gcs-calculation
description: Extract and calculate Glasgow Coma Scale (GCS) for ICU patients. Use for neurological assessment, consciousness monitoring, or trauma severity scoring.
tier: validated
category: clinical
---

# Glasgow Coma Scale (GCS) Calculation

The Glasgow Coma Scale assesses level of consciousness through three components: Eye opening, Verbal response, and Motor response. This concept extracts and calculates GCS with special handling for intubated patients.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## When to Use This Skill

- Neurological status assessment
- Trauma severity scoring
- Sedation monitoring
- Severity scores (SOFA CNS, APACHE, SAPS)
- Consciousness trajectory analysis

## GCS Components and Scoring

| Response | Score 1 | Score 2 | Score 3 | Score 4 | Score 5 | Score 6 |
|----------|---------|---------|---------|---------|---------|---------|
| **Eye** | None | To pain | To speech | Spontaneous | - | - |
| **Verbal** | None | Incomprehensible | Inappropriate | Confused | Oriented | - |
| **Motor** | None | Extension | Flexion | Withdraws | Localizes | Obeys |

**Total GCS Range**: 3-15 (lower = worse)

## MetaVision Item IDs

| Component | Item ID | Description |
|-----------|---------|-------------|
| Verbal | 223900 | GCS - Verbal Response |
| Motor | 223901 | GCS - Motor Response |
| Eyes | 220739 | GCS - Eye Opening |

## Critical Implementation Notes

1. **Intubated Patients**: When verbal response is documented as "No Response-ETT" (endotracheal tube), the verbal component is set to **0** (not 1, not 5) and flagged with `gcs_unable = 1`. The total GCS is then set to **15** (assumed normal if only intubation prevents assessment). **Important**: report `gcs_verbal = 0` in the output — do NOT replace it with 5. The value 0 is a sentinel meaning "untestable."

2. **Component Carry-Forward**: If only one or two components are documented at a time, previous values from the past 6 hours are carried forward. This prevents artificially low scores from incomplete charting.

3. **Calculation Logic**:
   ```
   GCS = Motor + Verbal + Eyes

   IF current verbal = 0 (intubated) THEN GCS = 15 (but keep gcs_verbal = 0 in output)
   ELSE IF previous verbal = 0 THEN use current components only (don't carry forward)
   ELSE carry forward missing components from past 6 hours
   ```

4. **Sedated Patients**: Per SAPS-II guidelines, sedated patients should use pre-sedation GCS. In practice, if documented as "unable to score due to medication", this is flagged.

5. **Time Series**: Each row represents a charted observation, not an hourly aggregate. Multiple observations per hour are possible.

## References

- Teasdale G, Jennett B. "Assessment of coma and impaired consciousness: A practical scale." Lancet. 1974;2(7872):81-84.
- Teasdale G et al. "The Glasgow Coma Scale at 40 years: standing the test of time." Lancet Neurology. 2014;13(8):844-854.
