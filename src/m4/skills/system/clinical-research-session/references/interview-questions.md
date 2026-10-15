# Interview questions

Compose one `Form` from the questions the user's message leaves open. Options are
`(label, description)` pairs; every question also takes free text unless `allow_other=False`.
`multiple=True` allows several answers. `r.values[name]` holds each answer.

```python
from vitrine import Form, Question, show

QUESTIONS = {
    "design": Question("design", "Study design", options=[
        ("Descriptive", "Characterise a cohort: demographics, severity, outcomes"),
        ("Comparative", "Compare groups: treated vs untreated, exposed vs unexposed"),
        ("Predictive", "Build or validate a prediction model"),
        ("Exploratory", "Generate hypotheses: clusters, patterns"),
    ]),
    "population": Question("population", "Base population", options=[
        ("Sepsis (Sepsis-3)", "SOFA >= 2 with suspected infection"),
        ("Septic shock", "Sepsis-3 with vasopressors and lactate > 2 mmol/L"),
        ("ARDS / respiratory failure", "Berlin criteria or PaO2/FiO2 ratio"),
        ("Cardiac arrest", "In- or out-of-hospital"),
        ("Heart failure / cardiogenic shock", "Acute decompensated heart failure"),
        ("Acute kidney injury", "KDIGO criteria"),
        ("General ICU", "All ICU admissions"),
    ]),
    "exposure": Question("exposure", "Exposure or intervention", options=[
        ("Treatment timing", "Early vs late start of a therapy"),
        ("Dose or intensity", "High vs low dose, or the course over time"),
        ("Treatment vs none", "Any use within a defined window"),
        ("Score or biomarker", "Continuous or categorical exposure"),
        ("None", "Descriptive study"),
    ]),
    "outcome": Question("outcome", "Primary outcome", options=[
        ("In-hospital mortality", "Death before hospital discharge"),
        ("28-day mortality", "Death within 28 days of time zero"),
        ("90-day mortality", "Death within 90 days of time zero"),
        ("ICU length of stay", "Shortened by early death"),
        ("Hospital length of stay", "Shortened by early death"),
        ("Ventilator-free days", "Days alive and off invasive ventilation, day 0-28"),
        ("Vasopressor-free days", "Days alive and off vasopressors, day 0-28"),
        ("Acute kidney injury", "KDIGO stage 2 or higher after the exposure window"),
    ]),
    "exclusions": Question("exclusions", "Exclusion criteria", multiple=True, options=[
        ("Readmissions", "Keep one ICU stay per patient"),
        ("Age < 18", "Exclude children"),
        ("ICU stay < 24 h", "Minimum observation; risks immortal time bias"),
        ("Early death", "Death within N hours of time zero; give N"),
        ("Treatment limits on admission", "DNR or comfort care"),
        ("End-stage renal disease", "Chronic dialysis before admission"),
        ("Missing key variables", "Name the variables"),
    ]),
    "confounders": Question("confounders", "Adjust for", multiple=True, options=[
        ("Age, sex", "Demographics"),
        ("SOFA at baseline", "Organ dysfunction"),
        ("APACHE III or SAPS-II", "Composite severity"),
        ("Charlson or Elixhauser", "Chronic comorbidity"),
        ("Admission type", "Medical, surgical, trauma"),
        ("Baseline labs", "Lactate, creatinine, bilirubin, platelets"),
        ("Ventilation at baseline", "On invasive ventilation at time zero"),
        ("Vasopressors at baseline", "On vasopressors at time zero"),
    ]),
}
# usable: dataset names from step 1 of the session
QUESTIONS["dataset"] = Question("dataset", "Dataset", options=usable, allow_other=False)

open_questions = ["outcome", "exclusions", "dataset"]  # what the user left open
r = show(Form([QUESTIONS[k] for k in open_questions]), title="Study parameters",
         study=STUDY)
```
