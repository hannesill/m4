# Operational Spec: Sepsis-3

## Output Contract

Return one row per ICU stay that has a qualifying suspected-infection and SOFA
window match. The key is `stay_id`.

Required columns, in order:
`subject_id, stay_id, antibiotic_time, culture_time, suspected_infection_time,
sofa_time, sofa_score, respiration, coagulation, liver, cardiovascular, cns,
renal, sepsis3`.

`sofa_time` is the end time of the SOFA measurement window.

## Suspected Infection

Identify suspected infection from systemic antibiotic therapy paired with a
culture from the same subject:

- culture collected within 72 hours before antibiotic start, or
- culture collected within 24 hours after antibiotic start.

Culture-before-antibiotic matches take precedence over culture-after-antibiotic
matches. Within each direction, choose the earliest eligible culture by
collection date, collection time, and stable culture identifier.

Set `suspected_infection_time` to the culture time when culture came first, and
to the antibiotic time when antibiotic came first. Culture positivity is not
required.

## SOFA Measurement

Calculate SOFA over rolling 24-hour windows for each ICU stay. Each component is
scored from 0 to 4 and the total `sofa_score` is the sum of respiration,
coagulation, liver, cardiovascular, CNS, and renal components. Treat missing
component data as normal by assigning score 0.

Use the standard SOFA component bins:

- respiration, PaO2/FiO2: `>= 400` = 0, `< 400` = 1, `< 300` = 2, `< 200` with
  invasive ventilation = 3, `< 100` with invasive ventilation = 4;
- coagulation, platelets: `>= 150` = 0, `< 150` = 1, `< 100` = 2, `< 50` = 3,
  `< 20` = 4;
- liver, bilirubin: `< 1.2` = 0, `1.2 to 1.9` = 1, `2.0 to 5.9` = 2,
  `6.0 to 11.9` = 3, `>= 12.0` = 4;
- cardiovascular: no hypotension = 0, MAP `< 70` = 1, dopamine `> 0 to <= 5`
  or any dobutamine = 2, dopamine `> 5 to <= 15`, epinephrine `> 0 to <= 0.1`,
  or norepinephrine `> 0 to <= 0.1` = 3, dopamine `> 15`, epinephrine `> 0.1`,
  or norepinephrine `> 0.1` = 4;
- CNS, Glasgow Coma Score: `15` = 0, `13 to 14` = 1, `10 to 12` = 2,
  `6 to 9` = 3, `< 6` = 4;
- renal, creatinine or urine output: creatinine `< 1.2` = 0, `1.2 to 1.9` = 1,
  `2.0 to 3.4` = 2, `3.5 to 4.9` or urine output `< 500 mL/day` = 3,
  creatinine `>= 5.0` or urine output `< 200 mL/day` = 4.

For components with multiple qualifying values in a window, use the worst score.

## Sepsis-3 Match

A SOFA window qualifies when `sofa_score >= 2` and `sofa_time` falls from 48
hours before through 24 hours after `suspected_infection_time`.

Set `sepsis3` to true when both `suspected_infection = 1` and
`sofa_score >= 2`.

If an ICU stay has multiple qualifying matches, return only the first by this
ordering:

1. `suspected_infection_time`, nulls first
2. `antibiotic_time`, nulls first
3. `culture_time`, nulls first
4. `sofa_time`, nulls first
