# Operational Spec: Suspicion of Infection

## Output Contract

Return one row per systemic antibiotic order. The key is `subject_id, ab_id`.

Required columns, in order:
`subject_id, stay_id, hadm_id, ab_id, antibiotic, antibiotic_time,
suspected_infection, suspected_infection_time, culture_time, specimen,
positive_culture`.

Assign `ab_id` as a row number per subject ordered by antibiotic start time,
stop time, and antibiotic name. Use stable identifiers as later tie-breakers
when timestamps and names are identical.

## Antibiotic Eligibility

Include systemic antibacterial therapy. Exclude topical, ophthalmic, otic,
cream, ointment, and other local-only formulations. Each eligible antibiotic
order remains a separate output row.

## Culture Eligibility

Include all culture specimen types. Culture positivity is not required for
suspected infection. Set `positive_culture` to 1 when an organism is reported
for the culture and 0 otherwise.

If a culture has a collection date but no exact collection time, use the date as
the collection timestamp for output and apply day-level matching windows.

## Pairing Rules

For each antibiotic row, search for cultures from the same subject in two
directions:

- culture before antibiotic: culture collected within 72 hours before the
  antibiotic start time;
- culture after antibiotic: culture collected within 24 hours after the
  antibiotic start time.

If both directions have an eligible culture, the culture-before-antibiotic match
takes precedence. Within each direction, choose the earliest eligible culture by
collection date, collection time, and stable culture identifier.

For date-only cultures, use a 3-day lookback for culture-before-antibiotic
matches and a 1-day lookahead for culture-after-antibiotic matches.

## Derived Fields

Set `suspected_infection = 1` when either pairing direction finds a culture;
otherwise set it to 0.

For culture-before-antibiotic matches, set `suspected_infection_time` to the
culture time. For culture-after-antibiotic matches, set
`suspected_infection_time` to the antibiotic time. If no culture is matched,
set `suspected_infection_time`, `culture_time`, `specimen`, and
`positive_culture` to null.

Populate `stay_id` when the antibiotic timing overlaps an ICU stay; it may be
null for antibiotics outside ICU stays.
