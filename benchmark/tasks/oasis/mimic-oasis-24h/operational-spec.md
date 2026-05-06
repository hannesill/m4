# Operational Spec: OASIS 24-Hour Score

## Output Contract

Return one row per ICU stay. The key is `stay_id`.

Required columns, in order:
`subject_id, hadm_id, stay_id, oasis, preiculos_score, age_score, gcs_score,
heart_rate_score, mbp_score, resp_rate_score, temp_score,
urineoutput_score, mechvent_score, electivesurgery_score`.

`oasis` is the sum of the 10 component scores. Treat missing component data as
normal by assigning score 0 before summing.

## Time Window

Use data from the first ICU day. For heart rate, mean blood pressure,
respiratory rate, temperature, and Glasgow Coma Score, include observations from
6 hours before ICU admission through 24 hours after ICU admission. For urine
output and invasive ventilation, use the first 24 hours after ICU admission.
Pre-ICU length of stay is the time from hospital admission to ICU admission,
measured in hours.

## Component Scoring

Apply the rules in the order listed for each component; the first matching rule
wins.

Pre-ICU length of stay, in hours:

- `< 0.17`: 5
- `0.17 to < 4.95`: 3
- `4.95 to < 24.00`: 0
- `24.00 to < 311.80`: 2
- `>= 311.80`: 1

Age, in years:

- `< 24`: 0
- `24 to 53`: 3
- `54 to 77`: 6
- `78 to 89`: 9
- `>= 90`: 7

Worst Glasgow Coma Score:

- `3 to 7`: 10
- `8 to 13`: 4
- `14`: 3
- `15`: 0

Heart rate, using first-24-hour minimum and maximum:

- maximum `> 125`: 6
- minimum `< 33`: 4
- maximum `107 to 125`: 3
- maximum `89 to 106`: 1
- otherwise: 0

Mean blood pressure, using first-24-hour minimum and maximum:

- minimum `< 20.65`: 4
- minimum `< 51`: 3
- maximum `> 143.44`: 3
- minimum `51 to < 61.33`: 2
- otherwise: 0

Respiratory rate, using first-24-hour minimum and maximum:

- minimum `< 6`: 10
- maximum `> 44`: 9
- maximum `> 30`: 6
- maximum `> 22`: 1
- minimum `< 13`: 1
- otherwise: 0

Temperature in degrees C, using first-24-hour minimum and maximum:

- maximum `> 39.88`: 6
- minimum or maximum `33.22 to 35.93`: 4
- minimum `< 33.22`: 3
- minimum `> 35.93 to 36.39`: 2
- maximum `36.89 to 39.88`: 2
- otherwise: 0

First-24-hour urine output in mL:

- `< 671.09`: 10
- `> 6896.80`: 8
- `671.09 to 1426.99`: 5
- `1427.00 to 2544.14`: 1
- otherwise: 0

Mechanical ventilation:

- any invasive ventilation overlapping the first 24 hours: 9
- no invasive ventilation record in the first 24 hours: 0

Elective surgery:

- elective hospital admission with a surgical service assignment before the end
  of the first ICU day: 0
- all other admissions: 6

## Missingness and Tie-Breakers

If a component value is unavailable, assign that component score 0. When a
component uses both minimum and maximum values, apply the ordered rules above
rather than independently selecting the most severe-looking low or high value.
