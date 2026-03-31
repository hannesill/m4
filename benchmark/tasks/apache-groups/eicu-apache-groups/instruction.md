# Task: Map APACHE IV Diagnosis Groups (eICU)

Map each ICU patient's APACHE IV admission diagnosis into one of these
clinically meaningful diagnosis groups:

ACS, ChestPainUnknown, CHF, CVOther, CardiacArrest, CABG, ValveDz,
PNA, RespMedOther, Asthma-Emphys, GIBleed, GIObstruction, CVA, Neuro,
Coma, Overdose, Sepsis, ARF, DKA, Trauma, Other

Patients with no admission diagnosis should be mapped to "Other".

Output a CSV file to `{output_path}` with these exact columns:
patientunitstayid, uniquepid, patienthealthsystemstayid, apachedxgroup, apacheadmissiondx

One row per ICU stay (all patients).
