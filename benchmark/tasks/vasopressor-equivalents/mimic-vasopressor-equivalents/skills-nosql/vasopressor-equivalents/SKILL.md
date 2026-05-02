---
name: vasopressor-equivalents
description: Calculate norepinephrine-equivalent dose for vasopressor comparison. Use for hemodynamic support quantification, shock severity assessment, or vasopressor weaning studies.
tier: validated
category: clinical
---

# Vasopressor Equivalent Dose

Calculates norepinephrine-equivalent dose (NED) to enable comparison across different vasopressor agents. Based on the Goradia et al. 2020 scoping review of vasopressor dose equivalence.

## M4Bench Use

In M4Bench, target concept tables listed in the task configuration are removed or unavailable in the agent database. Use this skill as procedural guidance and derive the requested output from available source or intermediate tables; do not rely on a precomputed target table or bundled SQL script.

## When to Use This Skill

- Comparing vasopressor exposure across different agents
- Shock severity quantification
- Vasopressor weaning studies
- Hemodynamic support burden calculation
- Cardiovascular SOFA component (uses vasopressor doses)

## Equivalence Factors

| Vasopressor | Equivalence Ratio | Comparison Dose | Units |
|-------------|------------------|-----------------|-------|
| Norepinephrine | 1:1 | 0.1 | mcg/kg/min |
| Epinephrine | 1:1 | 0.1 | mcg/kg/min |
| Dopamine | 1:100 | 10 | mcg/kg/min |
| Phenylephrine | 1:10 | 1 | mcg/kg/min |
| Vasopressin | 1:0.4* | 0.04 | units/min |

*Vasopressin is converted: `vasopressin_units_per_hr * 2.5 / 60`

## Calculation Formula

[SQL fragment removed by NO-SQL ablation]

## Source Tables

Individual vasopressor tables provide dose rates:
- `mimiciv_derived.norepinephrine`
- `mimiciv_derived.epinephrine`
- `mimiciv_derived.dopamine`
- `mimiciv_derived.phenylephrine`
- `mimiciv_derived.vasopressin`

All consolidated in:
- `mimiciv_derived.vasoactive_agent`

## Critical Implementation Notes

1. **Weight-Based Dosing**: All doses are in mcg/kg/min (except vasopressin in units/hr). The underlying tables use patient weight for conversion.

2. **Weight Estimation**: When weight is not documented, it may be estimated. Check `mimiciv_derived.weight_durations` for weight source.

3. **Vasopressin Units**: Vasopressin is charted in units/hour, not units/min. The formula converts appropriately.

4. **Excluded Agents**:
   - Metaraminol: Not used at BIDMC
   - Angiotensin II: Rarely used (could add: angiotensin_ii * 10)
   - Dobutamine: Not a vasopressor (inotrope), excluded from NED

5. **Time Intervals**: Each row has a starttime/endtime representing when that dose was active.

6. **Multiple Simultaneous Agents**: NED sums all concurrent vasopressors.

## References

- Goradia S et al. "Vasopressor dose equivalence: A scoping review and suggested formula." Journal of Critical Care. 2020;61:233-240.
- Brown SM et al. "Survival after shock requiring high-dose vasopressor therapy." Chest. 2013;143(3):664-671.
