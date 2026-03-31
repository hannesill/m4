# Task: Calculate OASIS Score (eICU)

You have access to an eICU Collaborative Research Database (DuckDB) at `{db_path}`.
It contains ICU patient data from 208 US hospitals in the `main` schema.
There are no pre-computed derived tables — you must work from raw tables.

Key tables: `patient` (demographics + ICU stay info), `vitalperiodic`
(periodic vitals), `vitalaperiodic` (non-invasive BP), `nursecharting`
(bedside observations including temperature), `intakeoutput` (fluid I/O),
`respiratorycare` (ventilation records), `apacheapsvar` (APACHE physiology),
`apachepredvar` (APACHE predictor variables including elective surgery flag).

**Important eICU conventions:**
- The primary ICU stay identifier is `patientunitstayid`
- Time is in **offset minutes** from ICU admission (not timestamps).
  `observationoffset = 0` means ICU admission time.
- `patient.age` is stored as a **string**; elderly patients have `"> 89"`
- `patient.hospitaladmitoffset` is negative when hospital admission was
  before ICU admission (e.g., -120 means admitted to hospital 120 min
  before ICU)
- `vitalperiodic` uses 0 for missing values in some columns (heartrate,
  respiration) — filter these out
- Patient identifiers: `uniquepid` (patient), `patienthealthsystemstayid`
  (hospital stay), `patientunitstayid` (ICU stay)

Calculate the Oxford Acute Severity of Illness Score (OASIS) for each
ICU stay using data from the first 24 hours of ICU admission
(Johnson et al., Critical Care Medicine, 2013).

OASIS uses 10 components (no laboratory values required):

| Variable | Points | Scoring Logic |
|----------|--------|---------------|
| Pre-ICU LOS (minutes from hospital admit to ICU) | 0-5 | 5 (<10.2), 3 (10.2-296), 0 (297-1439), 2 (1440-18707), 1 (>=18708) |
| Age | 0-9 | 0 (<24), 3 (24-53), 6 (54-77), 9 (78-89), 7 (>=90) |
| GCS | 0-10 | 10 (<=7), 4 (8-13), 3 (14), 0 (15) |
| Heart Rate | 0-6 | 6 (>125 bpm), 4 (<33), 3 (107-125), 1 (89-106), 0 (33-88) |
| Mean BP | 0-4 | 4 (<20.65 mmHg), 3 (<51 or >143.44), 2 (51-61.33), 0 (61.33-143.44) |
| Respiratory Rate | 0-10 | 10 (<6), 9 (>44), 6 (>30), 1 (>22 or <13), 0 (13-22) |
| Temperature | 0-6 | 6 (>39.88C), 4 (33.22-35.93), 3 (<33.22), 2 (35.93-36.39 or 36.89-39.88), 0 (36.39-36.89) |
| Urine Output (mL/day) | 0-10 | 10 (<671), 8 (>6897), 5 (671-1427), 1 (1427-2544), 0 (2544-6897) |
| Mechanical Ventilation | 0-9 | 9 (ventilated), 0 (not ventilated) |
| Elective Surgery | 0-6 | 0 (elective surgical admission), 6 (all others) |

The total OASIS score ranges from 0 to 71. Treat missing data as
normal (score 0).

Output a CSV file to `{output_path}` with these exact columns:
patientunitstayid, uniquepid, patienthealthsystemstayid, oasis, preiculos_score, age_score, gcs_score,
heart_rate_score, mbp_score, resp_rate_score, temp_score, urineoutput_score,
mechvent_score, electivesurgery_score

One row per ICU stay. The `oasis` column is the sum of the 10 component scores.
