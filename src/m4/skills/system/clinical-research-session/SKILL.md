---
name: clinical-research-session
description: Start a structured clinical research session. Use when users describe research goals, want to analyze cohorts, investigate hypotheses, or need a rigorous research plan. Interviews the user, then produces a research protocol.
tier: validated
category: system
---

# M4 Clinical Research Workflow

Structured clinical research from hypothesis through analysis. All work is tracked in a **vitrine study** — see CLAUDE.md for the vitrine quick reference or `/vitrine-api` for the full API.

## When This Skill Activates

- User invokes `/research` command
- User describes research intent: "I want to study...", "Can we analyze...", "What's the mortality rate for..."
- User mentions cohort analysis, hypothesis testing, or comparative studies

## Terminal and Vitrine

The researcher has the terminal and vitrine open side by side. Vitrine is where structured interaction happens — forms, data review, approvals. The terminal is where you discuss, explain reasoning, and refine.

**When blocking for input (`wait=True`), always narrate the handoff in the terminal** before the `show()` call. Tell the researcher what you've posted and what you need: "I've posted the study parameters form in vitrine — please fill in your outcome and exclusion criteria."

## Study Setup

Every research session is organized as a **study** — one study per research question, spanning one or more conversations.

```python
from m4.vitrine import (
    show, section, register_output_dir, study_context,
    list_studies, export, set_status, Form, Question,
)

STUDY = "early-vasopressors-sepsis-v1"
output_dir = register_output_dir(study=STUDY)

# FIRST card: study description as the opening vitrine card
show("""# Early Vasopressor Use in Sepsis
...research question, design, key definitions...
""", title="Study Description", study=STUDY)
```

**Continuing a study:** Call `list_studies()` and `study_context(study)` to re-orient. Use `section()` to mark a new conversation within an ongoing study — not a new study.

**Branching:** Create a new version (`v2`) when the researcher wants a different approach.

**File artifacts are mandatory.** Every DataFrame, figure, and analysis script MUST be saved to `output_dir`. Never save to `/tmp/` or rely on vitrine cards alone — cards document the narrative, files ARE the science. If the session ends, files must be the complete reproducible record.

**Required output files:**
- Numbered scripts: `01_cohort_definition.py`, `02_analysis.py`, etc. — the code that produced results
- Data: `.parquet` files for every significant DataFrame
- Figures: `.png` for every chart shown in vitrine (do NOT save `.html` — vitrine cards already store the interactive spec)

---

## Phase 1: Research Interview

Collect study parameters through vitrine forms. The interview is **adaptive** — compose questions based on what you already know from the user's initial description.

**Guidelines:**
- **Skip questions** the user already answered in their prompt
- **Add questions** not in the library if the research question demands it (time windows, subgroup definitions, method preferences)
- **Split into multiple forms** when it makes sense — quick basics first, targeted follow-up after processing answers
- Narrate each blocking call in the terminal before posting

### Question Library

Use `from m4.vitrine import Form, Question` and compose from these. **Use `multiple=True` for any question where multiple answers make sense** (e.g., exclusion criteria, confounders). Without it, options render as single-select radio buttons.

**Research question:**
```python
Question("question", question="Research Question",
         options=[
             ("Association study", "Is variable X associated with outcome Y?"),
             ("Prediction model", "Can we predict outcome Y from variables X?"),
             ("Cohort characterization", "What are the characteristics of population P?"),
         ], allow_other=True)
```

**Study design:**
```python
Question("design", question="Study Design",
         options=[
             ("Descriptive", "Characterize a cohort — demographics, severity, outcomes"),
             ("Comparative", "Compare groups — treatment vs control, exposed vs unexposed"),
             ("Predictive", "Build or validate a prediction model"),
             ("Exploratory", "Hypothesis-generating — clustering, pattern discovery"),
         ])
```

**Primary outcome:**
```python
Question("outcome", question="Primary Outcome",
         options=[
             ("In-hospital mortality", "hospital_expire_flag in admissions"),
             ("28-day mortality", "dod relative to admission or ICU entry"),
             ("90-day mortality", "dod relative to admission or ICU entry"),
             ("ICU length of stay", "los in icustays — beware survivor bias"),
             ("Hospital length of stay", "dischtime minus admittime — beware survivor bias"),
             ("Ventilator-free days", "28 minus days on mechanical ventilation"),
             ("Vasopressor-free days", "28 minus days on vasopressors"),
             ("AKI incidence", "KDIGO stage 2+ after exposure window"),
         ])
```

**Exposure / intervention:**
```python
Question("exposure", question="Exposure / Intervention",
         options=[
             ("Treatment timing", "Early vs late initiation of a therapy"),
             ("Treatment dose / intensity", "High vs low dose, or trajectory over time"),
             ("Treatment received vs not", "Binary: any use within a defined window"),
             ("Severity score / biomarker", "Continuous or categorical exposure variable"),
             ("None (descriptive study)", "No exposure — cohort characterization only"),
         ])
```

**Population:**
```python
Question("population", question="Base Population",
         options=[
             ("Sepsis (Sepsis-3)", "SOFA >= 2 + suspected infection"),
             ("Septic shock", "Sepsis-3 + vasopressor + lactate > 2 mmol/L"),
             ("ARDS / respiratory failure", "Berlin criteria or P/F ratio-based"),
             ("Cardiac arrest", "In- or out-of-hospital cardiac arrest"),
             ("Heart failure / cardiogenic shock", "Acute decompensated HF"),
             ("Acute kidney injury", "KDIGO criteria"),
             ("General ICU", "All ICU admissions, no disease-specific filter"),
         ])
```

**Exclusion criteria:**
```python
Question("exclusions", question="Exclusion Criteria", multiple=True,
         options=[
             ("First ICU stay only", "Exclude readmissions — one observation per patient"),
             ("Age < 18", "Exclude pediatric patients"),
             ("ICU stay < 24h", "Minimum observation window — watch for immortal time bias"),
             ("Early death", "Exclude death within N hours — specify N"),
             ("DNR / comfort care on admission", "Exclude treatment limitations"),
             ("Chronic dialysis / ESRD", "Exclude pre-existing end-stage renal disease"),
             ("Missing key variables", "Exclude if critical data points are absent"),
         ])
```

**Confounders:**
```python
Question("confounders", question="Key Confounders", multiple=True,
         options=[
             ("Age, sex", "Basic demographics"),
             ("Illness severity (SOFA)", "Organ dysfunction at baseline"),
             ("Illness severity (APACHE III / SAPS-II)", "Composite severity scores"),
             ("Charlson / Elixhauser comorbidities", "Pre-existing chronic conditions"),
             ("Admission type", "Medical vs surgical vs trauma"),
             ("Baseline labs", "Lactate, creatinine, bilirubin, platelets, etc."),
             ("Mechanical ventilation status", "On/off MV at baseline"),
             ("Vasopressor use at baseline", "Already on vasopressors at time zero"),
         ])
```

**Dataset:**
```python
Question("dataset", question="Primary Dataset",
         options=[
             ("mimic-iv", "Full MIMIC-IV"),
             ("mimic-iv-demo", "100 patients, good for testing"),
             ("eicu", "Multi-center ICU database"),
         ], allow_other=False)
```

### After the Interview

Review answers in the terminal. Pay attention to "Other" entries — help make them precise.

Key refinements to consider:
- **Research question** — Make specific and answerable: "Are sicker patients dying more?" → "Is day-1 SOFA independently associated with 30-day mortality in sepsis?"
- **Outcome** — Confirm operationalization (which table/column, survivor bias for LOS, follow-up window for X-free days)
- **Exposure** — Nail down time window, comparator, and immortal time bias risk
- **Population & Exclusions** — Check that exclusions don't introduce bias for this specific design
- **Confounders** — Check for mediators on the causal path (should NOT be adjusted for); consider propensity scores for treatment comparisons

---

## Phase 2: Research Protocol

Draft a structured protocol. Save to `output_dir / "PROTOCOL.md"` and show with `wait=True` for approval.

```markdown
## Research Protocol: [Title]

### Research Question
[Specific, answerable question]

### Study Design
[Descriptive/Comparative/Predictive/Exploratory]

### Population
**Inclusion:** [criteria]
**Exclusion:** [criteria with rationale]

### Variables
**Primary Outcome:** [definition and measurement]
**Exposure:** [definition and timing]
**Covariates:** [list with definitions]

### Analysis Plan
1. [Step with rationale]
2. ...

### Potential Biases & Limitations
- [Known limitation]

### M4 Skills to Use
- [Skill]: [Why]
```

---

## Phase 3: Scientific Integrity Guardrails

Apply throughout the analysis.

### Bias Prevention

**Immortal Time Bias**
- Define exposure at a FIXED time point (admission, 24h, 48h)
- Never use "ever received during stay" for treatments
- Use landmark analysis when appropriate

**Selection Bias**
- Report all exclusions with counts (CONSORT diagram)
- Analyze whether excluded patients differ
- Avoid conditioning on post-treatment variables

**Information Leakage**
- ICD codes are assigned at DISCHARGE — don't use for admission predictions
- Length of stay is only known at discharge
- Labs/vitals must be timestamped appropriately

**Confounding by Indication**
- Treatments are given to sicker patients
- Always adjust for severity (SOFA, APACHE, SAPS)
- Consider propensity scores for treatment comparisons

### Statistical Rigor

- Pre-specify primary outcome; apply Bonferroni/FDR for secondary analyses
- Report cohort sizes at each step; be cautious with small subgroups
- Report missingness; consider imputation vs complete case; perform sensitivity analyses

### Visualizations

Use plots liberally — a chart often reveals what a table hides.

**Distributions → plots, not key-value cards.** Categorical variables (race, gender, admission type) → horizontal bar chart. Continuous variables (age, LOS, SOFA) → histogram. Never `show(dict)` for a distribution with 5+ categories — use `show(fig)` instead. Reserve key-value cards for small summary stats (n, median, IQR).

Other plots: Kaplan-Meier curves for survival, forest plots for effect sizes, covariate balance after matching, CONSORT flow diagrams. If you're staring at numbers and deciding what they mean, make a plot instead.

### Reproducibility

- **Save every analysis script** as a numbered file in `output_dir`: `01_cohort_definition.py`, `02_baseline_characteristics.py`, etc. The script should be the complete, runnable Python code for that step — not a fragment. This is non-negotiable; without scripts the research is not reproducible.
- Use `show()` for decisions and findings; `section()` for phase transitions
- Use `set_status()` during long operations
- Export the complete study at the end

---

## Phase 4: M4 Skills Reference

### Severity Scores
| Skill | When to Use |
|-------|-------------|
| `sofa-score` | Organ dysfunction, Sepsis-3 criteria |
| `apsiii-score` | Comprehensive severity with mortality prediction |
| `sapsii-score` | Alternative to APACHE, international benchmarking |
| `oasis-score` | When labs unavailable (vitals only) |
| `sirs-criteria` | Historical sepsis definition, comparison studies |

### Cohort Definitions
| Skill | When to Use |
|-------|-------------|
| `sepsis-3-cohort` | Sepsis studies (SOFA >= 2 + suspected infection) |
| `first-icu-stay` | Avoid correlated observations |
| `suspicion-of-infection` | Infection timing (antibiotics + cultures) |

### Clinical Concepts
| Skill | When to Use |
|-------|-------------|
| `kdigo-aki-staging` | AKI as outcome or covariate |
| `vasopressor-equivalents` | Standardize vasopressor doses |
| `baseline-creatinine` | AKI baseline reference |
| `gcs-calculation` | Neurological status |

### Data & Methodology
| Skill | When to Use |
|-------|-------------|
| `m4-api` | Multi-step analysis, statistical tests |
| `clinical-research-pitfalls` | Review for common errors |
| `mimic-table-relationships` | Understanding joins |
| `mimic-eicu-mapping` | Cross-dataset queries |

---

## Example Flow

**User:** "I want to study if early vasopressor use affects mortality in sepsis"

**What you already know:** comparative design, sepsis population, vasopressor exposure, mortality-related. Skip those questions.

**Form:** Ask only what's missing — outcome definition, "early" window, exclusion criteria, dataset. Narrate in terminal: "I've posted a form in vitrine for the details I couldn't infer — outcome, time window, exclusions, and dataset."

**After response, refine in terminal:**
- Anchor the time window to suspected infection onset (suspicion-of-infection skill), not ICU admission
- Recommend excluding death within the exposure window to avoid immortal time bias
- For treatment comparison, suggest propensity score matching over simple regression
- Show a follow-up form only if needed (e.g., matching method preference)

**Protocol → approval → execute:**
- Save protocol to `output_dir / "PROTOCOL.md"`, show with `wait=True`
- Use `section()` to mark phases: Cohort Definition → Matching → Analysis → Conclusions
- Save scripts, data, and figures to `output_dir`; show key results as cards
- Block for approval at decision points
- Export at the end: `export("output/report.html", study=STUDY)`

---

## Red Flags

Stop and reconsider if you see:
- **"Patients who survived to receive..."** → Immortal time bias
- **"Using ICD codes to identify patients at admission"** → Information leakage
- **"Complete cases only (N drops from X to Y)"** → Selection bias
- **"Treatment group had higher mortality"** → Confounding by indication
- **"47 significant associations"** → Multiple comparisons
- **"Small sample size but p < 0.05"** → Likely false positive

---

## After Completion

1. Save `RESULTS.md` to `output_dir` with findings, effect sizes, and confidence intervals
2. Show a summary card with key findings
3. Acknowledge limitations explicitly — show as a card for the record
4. Suggest validation on independent data (e.g., eICU if used MIMIC)
5. Export: `export("output/study-report.html", study=STUDY)`
