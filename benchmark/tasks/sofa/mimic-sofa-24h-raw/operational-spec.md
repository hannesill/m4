# Operational Spec: SOFA 24-Hour Score

## Output Contract

Return one row per ICU stay. The key is `stay_id`.

Required columns, in order:
`subject_id, hadm_id, stay_id, sofa, respiration, coagulation, liver,
cardiovascular, cns, renal`.

`sofa` is the sum of the six component scores. Treat missing component data as
normal by assigning score 0 before summing.

## Time Window

Use data from 6 hours before ICU admission through 24 hours after ICU admission.
For each component, use the worst qualifying value observed in this window.

## Component Scoring

Respiration, using arterial PaO2/FiO2 ratio and invasive ventilation status:

- `>= 400`: 0
- `< 400`: 1
- `< 300`: 2
- `< 200` while invasively ventilated: 3
- `< 100` while invasively ventilated: 4

Coagulation, using minimum platelet count:

- `>= 150`: 0
- `< 150`: 1
- `< 100`: 2
- `< 50`: 3
- `< 20`: 4

Liver, using maximum bilirubin:

- `< 1.2`: 0
- `1.2 to 1.9`: 1
- `2.0 to 5.9`: 2
- `6.0 to 11.9`: 3
- `>= 12.0`: 4

Cardiovascular, using minimum mean arterial pressure and vasopressor exposure:

- no hypotension and no qualifying vasoactive support: 0
- MAP `< 70`: 1
- dopamine `> 0 to <= 5` or any dobutamine: 2
- dopamine `> 5 to <= 15`, epinephrine `> 0 to <= 0.1`, or norepinephrine
  `> 0 to <= 0.1`: 3
- dopamine `> 15`, epinephrine `> 0.1`, or norepinephrine `> 0.1`: 4

Vasopressor doses are in mcg/kg/min.

CNS, using worst Glasgow Coma Score:

- `15`: 0
- `13 to 14`: 1
- `10 to 12`: 2
- `6 to 9`: 3
- `< 6`: 4

Renal, using maximum creatinine and total urine output:

- creatinine `< 1.2`: 0
- creatinine `1.2 to 1.9`: 1
- creatinine `2.0 to 3.4`: 2
- creatinine `3.5 to 4.9` or urine output `< 500 mL/day`: 3
- creatinine `>= 5.0` or urine output `< 200 mL/day`: 4

When creatinine and urine output imply different renal scores, use the higher
renal score.

## Missingness and Tie-Breakers

If a component cannot be computed because all source measurements for that
component are missing, set the component score to 0. If multiple values qualify
within a component, use the value that yields the highest SOFA component score.
