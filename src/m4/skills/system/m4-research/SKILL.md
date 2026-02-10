---
name: m4-research
description: Start a structured clinical research session. Use when users describe research goals, want to analyze cohorts, investigate hypotheses, or need a rigorous research plan. Interviews the user, then produces a research protocol.
tier: validated
category: system
---

# M4 Clinical Research Workflow

This skill guides you through a structured clinical research session. It ensures scientific rigor from hypothesis formation through analysis execution. All work is tracked in a **vitrine study** — a persistent, browsable research journal with an integrated file panel.

## When This Skill Activates

- User invokes `/research` command
- User describes research intent: "I want to study...", "Can we analyze...", "What's the mortality rate for..."
- User mentions cohort analysis, hypothesis testing, or comparative studies

## Study Setup

Every research session is organized as a **study** — one study per research question, spanning one or more agent conversations.

### Starting a new study

```python
from m4.vitrine import show, section, register_output_dir, study_context, list_studies, export, set_status

# Choose a descriptive, versioned study name
STUDY = "early-vasopressors-sepsis-v1"

# Register the output directory for file artifacts
output_dir = register_output_dir(study=STUDY)
# Returns: .vitrine/studies/{timestamp}_{study}/output/

# All show() calls use the study label
show("## Study: Early vasopressor use in sepsis\n...", title="Study Overview", study=STUDY)
```

### Continuing an existing study

At the start of each new conversation, check for existing studies:

```python
from m4.vitrine import list_studies, study_context

# List recent studies and ask the researcher which to continue
studies = list_studies()

# Re-orient by reading study context
ctx = study_context("early-vasopressors-sepsis-v1")
# Returns: card_count, cards, decisions_made, pending_responses
```

Use `section()` to mark the start of a new conversation within an ongoing study — not a new study.

### Branching a study

When the researcher wants a different approach to the same question, create a new study referencing the original:

```python
STUDY = "early-vasopressors-sepsis-v2"  # new version
output_dir = register_output_dir(study=STUDY)
show("Branched from v1. Changed exposure window from 6h to 3h.", title="Branch Note", study=STUDY)
```

### File artifacts

Save all reproducible outputs (scripts, data, figures, protocol) to the output directory:

```python
# Protocol
(output_dir / "PROTOCOL.md").write_text(protocol_md)

# Numbered analysis scripts
(output_dir / "01_data_extraction.py").write_text(extraction_code)

# Data files
(output_dir / "data").mkdir(exist_ok=True)
cohort_df.to_parquet(output_dir / "data" / "cohort.parquet")

# Figures
(output_dir / "figures").mkdir(exist_ok=True)
fig.write_image(str(output_dir / "figures" / "km_curves.png"))
```

These files appear in the vitrine Files panel alongside the card journal — the researcher sees everything in the browser.

## Terminal and Vitrine

The researcher has the terminal and vitrine open side by side. Vitrine is where structured interaction happens — the interview form, data review, approvals. The terminal is where you discuss, explain reasoning, and refine what the researcher entered.

**When blocking for input (`wait=True`), always narrate the handoff in the terminal.** Tell the researcher what you've posted and what you need from them before the `show()` call:

> "I've posted the study parameters form in vitrine — please fill in your research question, outcome, and population criteria."

The `show()` function prints a waiting message automatically, but your narration gives the researcher context for *what* to provide and *why* it matters.

---

## Phase 1: Research Interview

**Collect study parameters through one or more vitrine forms.** This captures the researcher's intent in the study journal from the start.

The interview is **adaptive, not fixed**. Compose forms from the question library below based on what you already know from the user's initial description. If the user said "I want to study mortality in septic shock patients," you already know the population and can skip that question. If the study design is ambiguous, add a follow-up form. You may use a single form or several rounds — just like the old AskUserQuestion flow, but rendered in vitrine.

**Guidelines for composing forms:**
- **`Question`** is the only field type. It gives premade options with an "Other" freeform fallback. Use it for everything.
- **Skip questions** the user already answered in their prompt. Don't re-ask what you already know.
- **Add questions** not in the library if the research question demands it (e.g., specific time windows, subgroup definitions, clustering method preferences).
- **Split into multiple forms** when it makes sense — e.g., a quick first form for the basics, then a targeted follow-up after you've processed the answers.

Tell the researcher what you've posted before each blocking call.

### Question Library

Use `from m4.vitrine import Form, Question` and compose from these:

**Research question** — Use `Question` with `allow_other=True` so the researcher can refine freely:
```python
Question("question", question="Research Question",
         options=[
             ("Association study", "Is variable X associated with outcome Y?"),
             ("Prediction model", "Can we predict outcome Y from variables X?"),
             ("Cohort characterization", "What are the characteristics of population P?"),
         ],
         allow_other=True)
```

**Study design:**
```python
Question("design", question="Study Design",
         options=[
             ("Descriptive", "Characterize a cohort — demographics, severity, outcomes"),
             ("Comparative", "Compare groups — treatment vs control, exposed vs unexposed"),
             ("Predictive", "Build or validate a prediction model"),
             ("Exploratory", "Hypothesis-generating — clustering, pattern discovery, subgroup search"),
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
             ("Organ-failure-free days", "28 minus days with SOFA sub-score >= 3"),
             ("ICU readmission", "Subsequent ICU stay within same hospitalization"),
             ("AKI incidence", "KDIGO stage 2+ after exposure window"),
             ("Delirium incidence", "CAM-ICU positive or antipsychotic use"),
             ("Composite endpoint", "Combine multiple outcomes — specify in notes"),
         ])
```

**Exposure / intervention:**
```python
Question("exposure", question="Exposure / Intervention",
         options=[
             ("Treatment timing", "Early vs late initiation of a therapy"),
             ("Treatment dose / intensity", "High vs low dose, or dose trajectory over time"),
             ("Treatment received vs not", "Binary: any use within a defined window"),
             ("Severity score / biomarker", "Continuous or categorical exposure variable"),
             ("Trajectory / pattern", "Time-series clustering or phenotyping of a variable"),
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
             ("Cardiac arrest / post-resuscitation", "In- or out-of-hospital cardiac arrest"),
             ("Heart failure / cardiogenic shock", "Acute decompensated HF or cardiogenic shock"),
             ("Acute kidney injury", "KDIGO criteria — creatinine and/or urine output"),
             ("Traumatic brain injury", "GCS-based or ICD-based TBI identification"),
             ("Stroke", "Ischemic or hemorrhagic — ICD-based"),
             ("Post-cardiac surgery", "CABG, valve replacement, or other cardiac procedures"),
             ("Post-major surgery (non-cardiac)", "Major abdominal, thoracic, vascular, etc."),
             ("Liver failure / cirrhosis", "Acute liver failure or decompensated cirrhosis"),
             ("General ICU", "All ICU admissions, no disease-specific filter"),
         ])
```

**Exclusion criteria:**
```python
Question("exclusions", question="Exclusion Criteria (select all that apply)",
         multi_select=True,
         options=[
             ("First ICU stay only", "Exclude readmissions — one observation per patient"),
             ("Age < 18", "Exclude pediatric patients"),
             ("ICU stay < 24h", "Minimum observation window — watch for immortal time bias"),
             ("ICU stay < 48h", "Longer minimum window for trajectory studies"),
             ("Early death", "Exclude death within N hours of admission — specify N"),
             ("DNR / comfort care on admission", "Exclude patients with treatment limitations"),
             ("Chronic dialysis / ESRD", "Exclude pre-existing end-stage renal disease"),
             ("Chronic ventilator dependence", "Exclude long-term ventilator patients"),
             ("Transferred from another hospital", "Unclear illness onset and prior treatment"),
             ("Missing key variables", "Exclude if critical data points are absent"),
         ])
```

**Confounders:**
```python
Question("confounders", question="Key Confounders to Adjust For (select all that apply)",
         multi_select=True,
         options=[
             ("Age, sex", "Basic demographics"),
             ("BMI / weight", "Body habitus — available in chartevents"),
             ("Race / ethnicity", "Use with caution — document rationale for inclusion"),
             ("Illness severity (SOFA)", "Organ dysfunction at baseline"),
             ("Illness severity (APACHE III / SAPS-II)", "Composite severity scores"),
             ("Charlson / Elixhauser comorbidities", "Pre-existing chronic conditions"),
             ("Admission type", "Medical vs surgical vs trauma"),
             ("Admission source", "ED, floor, OR, outside transfer"),
             ("Baseline labs", "Lactate, creatinine, bilirubin, platelets, etc."),
             ("Fluid balance / resuscitation volume", "Cumulative input minus output"),
             ("Mechanical ventilation status", "On/off MV at baseline"),
             ("Vasopressor use at baseline", "Already on vasopressors at time zero"),
             ("Prior hospitalizations", "Number or recency of prior admissions"),
         ])
```

**Dataset:**
```python
Question("dataset", question="Primary Dataset",
         options=[
             ("mimic-iv", "Full MIMIC-IV (requires access)"),
             ("mimic-iv-demo", "100 patients, good for testing queries"),
             ("eicu", "Multi-center ICU database"),
             ("mimic-iv-note", "Clinical notes from MIMIC-IV"),
         ],
         allow_other=False)
```

### Composing the Form

Pick the questions you need and assemble them. Example for a study where the user already specified the population:

```python
response = show(
    Form([
        Question("question", question="Research Question", options=[...], allow_other=True),
        Question("design", question="Study Design", options=[...]),
        Question("outcome", question="Primary Outcome", options=[...]),
        Question("exposure", question="Exposure / Intervention", options=[...]),
        # population already known — skip it
        Question("exclusions", question="Exclusion Criteria", multi_select=True, options=[...]),
        Question("dataset", question="Primary Dataset",
                 options=[("mimic-iv", "Full"), ("mimic-iv-demo", "Demo"), ("eicu", "Multi-center")],
                 allow_other=False),
    ]),
    title="Study Parameters",
    prompt="Define your research study",
    study=STUDY,
)
params = response.values
```

If you need follow-up details after the first form (e.g., specific time windows, method preferences), show a second form:

```python
response2 = show(
    Form([
        Question("time_window", question="Exposure time window",
                 options=[
                     ("First 6 hours", "From ICU admission or vasopressor start"),
                     ("First 24 hours", "Full first day"),
                     ("First 48 hours", "Two-day window"),
                 ]),
        Question("method", question="Preferred analysis method",
                 options=[...]),
    ]),
    title="Follow-up — Study Details",
    prompt="A few more details to finalize the protocol",
    study=STUDY,
)
```

### Reviewing the Response

After each form submission, review the answers in the terminal and discuss refinements before proceeding to the protocol. Pay attention to "Other" entries — these need the most help getting precise.

**Research Question** — Should be specific and answerable with available data. Help refine vague questions:
- "Are sicker patients dying more?" → "Is day-1 SOFA score independently associated with 30-day mortality in sepsis patients?"

**Outcome** — Confirm operationalization. Key considerations:
- **In-hospital mortality**: `hospital_expire_flag` in admissions table
- **28/90-day mortality**: Compare `dod` to admission/discharge + N days — requires `dod` availability
- **ICU/hospital LOS**: Beware survivor bias — sicker patients who die early have shorter LOS
- **Ventilator/vasopressor/organ-failure-free days**: Require 28-day follow-up window definition
- **Composite endpoints**: Specify components and how they combine
- Custom outcomes via "Other" need precise operationalization

**Exposure** — Nail down specifics:
- What's the exact time window? (admission, 6h, 24h, 48h)
- What's the comparator? (no treatment, late treatment, alternative treatment)
- Is immortal time bias a concern with this exposure definition?
- For trajectory/pattern studies: what variable, what time resolution, what clustering approach?

**Population & Exclusions** — Review whether:
- Selected exclusions are appropriate (e.g., "ICU stay < 24h" introduces immortal time bias for some designs)
- Additional exclusions are needed based on the research question
- ICD-based diagnoses risk information leakage (codes assigned at discharge)

**Confounders** — Check whether:
- Selected confounders are sufficient for the study design
- For treatment comparisons, consider propensity scores over simple regression adjustment
- Any selected confounder is actually a mediator (on the causal path — should NOT be adjusted for)
- Race/ethnicity inclusion is justified and documented

**Dataset**:
- **mimic-iv**: Full MIMIC-IV (requires access)
- **mimic-iv-demo**: 100 patients, good for testing queries
- **eicu**: Multi-center ICU data (different schema)
- **mimic-iv-note**: MIMIC-IV with clinical notes

---

## Phase 2: Draft Research Protocol

After the interview, produce a structured research plan. **Save the protocol as a file and show it as a card for researcher approval:**

```python
protocol_md = """## Research Protocol: [Title]

### Research Question
[Specific, answerable question]

### Hypothesis
[If applicable - null and alternative]

### Study Design
[Descriptive/Comparative/Predictive/Exploratory]

### Dataset
[Selected dataset with justification]

### Population
**Inclusion Criteria:**
- [Criterion 1]
- [Criterion 2]

**Exclusion Criteria:**
- [Criterion 1]
- [Criterion 2]

### Variables
**Primary Outcome:** [Definition and how measured]
**Exposure:** [Definition and timing]
**Covariates:** [List with definitions]

### Analysis Plan
1. [Step 1]
2. [Step 2]
...

### Potential Biases & Limitations
- [Known limitation 1]
- [Known limitation 2]

### M4 Skills to Use
- [Relevant skill 1]: [Why]
- [Relevant skill 2]: [Why]
"""

# Save to output directory (reproducibility)
(output_dir / "PROTOCOL.md").write_text(protocol_md)

# Show for researcher review and approval (journal + communication)
response = show(protocol_md, title="Research Protocol", wait=True, prompt="Approve this protocol?", study=STUDY)
```

---

## Phase 3: Scientific Integrity Guardrails

**Apply these checks throughout the analysis:**

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
- ICD codes are assigned at DISCHARGE - don't use for admission predictions
- Length of stay is only known at discharge
- Labs/vitals must be timestamped appropriately

**Confounding by Indication**
- Treatments are given to sicker patients
- Always adjust for severity (SOFA, APACHE, SAPS)
- Consider propensity scores for treatment comparisons

### Statistical Rigor

**Multiple Comparisons**
- Pre-specify primary outcome
- Apply Bonferroni/FDR correction for secondary analyses
- Report all analyses performed, not just significant ones

**Sample Size**
- Report cohort sizes at each step
- Be cautious with small subgroups
- Consider power for planned comparisons

**Missing Data**
- Report missingness rates for all variables
- Consider imputation vs complete case analysis
- Perform sensitivity analyses

### Reproducibility

**Query Documentation**
- Save all SQL queries as numbered scripts in `output_dir` (e.g., `01_data_extraction.py`)
- Document data versions used
- Note any manual data cleaning steps

**Analysis Trail**
- Number analyses sequentially — save scripts, show key results as cards
- Distinguish exploratory from confirmatory
- Record decision points and rationale using `show()` with `wait=True`

**Vitrine Journal**
- Use `show()` for key decisions, findings, and rationale (the journal)
- Use `section()` to mark phase transitions within the study
- Save files to `output_dir` for reproducibility (scripts, data, figures)
- Use `set_status()` to keep the researcher informed during long operations

---

## Phase 4: Using M4 Skills

**Match skills to research needs:**

### Severity Scores
Use when adjusting for baseline illness severity:

| Skill | When to Use |
|-------|-------------|
| `sofa-score` | Organ dysfunction assessment, Sepsis-3 criteria |
| `apsiii-score` | Comprehensive severity with mortality prediction |
| `sapsii-score` | Alternative to APACHE, mortality prediction |
| `oasis-score` | When labs unavailable (uses vitals only) |
| `sirs-criteria` | Historical sepsis definition, comparison studies |

### Cohort Definitions
Use when defining study populations:

| Skill | When to Use |
|-------|-------------|
| `sepsis-3-cohort` | Sepsis studies (SOFA >= 2 + suspected infection) |
| `first-icu-stay` | Avoid correlated observations |
| `suspicion-of-infection` | Infection timing (antibiotics + cultures) |

### Clinical Concepts
Use when defining exposures or outcomes:

| Skill | When to Use |
|-------|-------------|
| `kdigo-aki-staging` | AKI as outcome or covariate |
| `vasopressor-equivalents` | Standardize vasopressor doses |
| `baseline-creatinine` | AKI baseline reference |
| `gcs-calculation` | Neurological status |

### Data Quality
Use when building queries:

| Skill | When to Use |
|-------|-------------|
| `clinical-research-pitfalls` | Review for common errors |
| `mimic-table-relationships` | Understanding joins |
| `mimic-eicu-mapping` | Cross-dataset queries |

### Code Execution
Use for complex analyses:

| Skill | When to Use |
|-------|-------------|
| `m4-api` | Multi-step analysis, large results, statistical tests |

---

## Example Research Flow

**User**: "I want to study if early vasopressor use affects mortality in sepsis"

**Agent creates the study.** The user already told us: comparative design, sepsis population, vasopressor exposure, mortality-related. So the agent skips questions it can infer and asks only what's missing:

```python
STUDY = "early-vasopressors-sepsis-v1"
output_dir = register_output_dir(study=STUDY)
```

> "I've posted a few questions in vitrine to pin down the details — outcome definition, exclusion criteria, and dataset. I already know this is a comparative study in sepsis looking at vasopressor timing."

```python
from m4.vitrine import Form, Question

response = show(
    Form([
        Question("outcome", question="Primary Outcome",
                 options=[
                     ("In-hospital mortality", "hospital_expire_flag in admissions"),
                     ("28-day mortality", "dod relative to admission or ICU entry"),
                     ("90-day mortality", "dod relative to admission or ICU entry"),
                 ]),
        Question("early_window", question="How do you define 'early' vasopressor use?",
                 options=[
                     ("Within 1 hour of sepsis onset", "Aggressive early resuscitation"),
                     ("Within 3 hours", "Per Surviving Sepsis Campaign bundles"),
                     ("Within 6 hours", "Broader early window"),
                 ]),
        Question("exclusions", question="Exclusion Criteria (select all that apply)",
                 multi_select=True,
                 options=[
                     ("First ICU stay only", "Exclude readmissions"),
                     ("Age < 18", "Adults only"),
                     ("Early death", "Exclude death within N hours — avoids immortal time bias"),
                     ("DNR / comfort care on admission", "Exclude treatment limitations"),
                     ("Already on vasopressors at admission", "Unclear time-zero"),
                 ]),
        Question("dataset", question="Primary Dataset",
                 options=[
                     ("mimic-iv", "Full MIMIC-IV (requires access)"),
                     ("mimic-iv-demo", "100 patients, good for testing queries"),
                     ("eicu", "Multi-center ICU database"),
                 ],
                 allow_other=False),
    ]),
    title="Study Parameters — Early Vasopressors in Sepsis",
    prompt="Confirm these details so I can draft the protocol",
    study=STUDY,
)
params = response.values
```

**Agent reviews the form response and refines in the terminal:**

> "Good choices. A few refinements:
>
> You selected 'within 6 hours' — I'd anchor that to suspected infection onset using the suspicion-of-infection skill, not ICU admission. The comparator would be vasopressor started >6h after infection onset, or never.
>
> For the 'early death' exclusion — I'd recommend excluding death within the same window (6 hours) to avoid immortal time bias.
>
> For confounders, given this is a treatment comparison, I'd recommend propensity score matching on age, SOFA, admission source, comorbidities, and lactate rather than just regression adjustment. Does that sound right?"

**Agent may show a short follow-up form if needed:**

```python
response2 = show(
    Form([
        Question("matching", question="Adjustment method for confounding",
                 options=[
                     ("Propensity score matching", "1:1 or 1:N nearest-neighbor matching"),
                     ("Inverse probability weighting", "Weight by propensity score"),
                     ("Multivariable regression", "Covariate adjustment in outcome model"),
                     ("All of the above as sensitivity analyses", "Primary + sensitivity"),
                 ]),
    ]),
    title="Analysis Method",
    prompt="How should we handle confounding?",
    study=STUDY,
)
```

**Agent drafts protocol and asks for approval:**

> "I've posted the full research protocol in vitrine incorporating these refinements. Please review and approve."

```python
(output_dir / "PROTOCOL.md").write_text(protocol_md)
response = show(protocol_md, title="Research Protocol", wait=True, prompt="Approve this protocol?", study=STUDY)
```

**Agent executes analysis with journal + files:**

```python
section("Phase 1: Cohort Definition", study=STUDY)
# ... extract cohort ...
cohort_df.to_parquet(output_dir / "data" / "cohort.parquet")
(output_dir / "01_cohort_definition.py").write_text(script)
show(cohort_df, title="Sepsis Cohort", description="N=4,238 after exclusions", study=STUDY)

section("Phase 2: Propensity Matching", study=STUDY)
# ... match groups ...
show(balance_table, title="Covariate Balance", study=STUDY)

section("Phase 3: Outcome Analysis", study=STUDY)
# ... survival analysis ...
show(km_fig, title="Kaplan-Meier Curves", study=STUDY)
```

**Agent wraps up:**

```python
section("Conclusions", study=STUDY)
(output_dir / "RESULTS.md").write_text(results_md)
show(results_md, title="Study Results", study=STUDY)
export("output/early-vasopressors-report.html", study=STUDY)
```

---

## Common Research Patterns

### Pattern: Mortality Risk Factors
```
1. section("Phase 1: Cohort Definition", study=STUDY)
2. Define cohort (first-icu-stay) → save script, show cohort table
3. Extract baseline characteristics → save to data/
4. section("Phase 2: Analysis", study=STUDY)
5. Calculate severity (sofa-score or apsiii-score)
6. Define mortality outcome
7. Multivariable regression → save script, show results
8. section("Phase 3: Results", study=STUDY)
9. Summary card with effect sizes and CIs
```

### Pattern: Treatment Effect
```
1. section("Phase 1: Cohort & Exposure", study=STUDY)
2. Define cohort and time zero → show for approval
3. Define exposure window (fixed time)
4. section("Phase 2: Matching & Analysis", study=STUDY)
5. Extract confounders at baseline
6. Propensity score matching → show balance table
7. Compare outcomes → save scripts, show results
```

### Pattern: Cohort Description
```
1. section("Phase 1: Population", study=STUDY)
2. Define cohort → show CONSORT-style flow
3. section("Phase 2: Characterization", study=STUDY)
4. Demographics, comorbidities → show Table 1
5. Severity scores, treatments received
6. section("Phase 3: Outcomes", study=STUDY)
7. Outcomes (mortality, LOS, complications)
```

---

## Red Flags to Watch For

Stop and reconsider if you see:

- **"Patients who survived to receive..."** → Immortal time bias
- **"Using ICD codes to identify patients at admission"** → Information leakage
- **"Complete cases only (N drops from X to Y)"** → Selection bias
- **"Treatment group had higher mortality"** → Confounding by indication
- **"We found 47 significant associations"** → Multiple comparisons
- **"Small sample size but p < 0.05"** → Underpowered, likely false positive

---

## After Analysis Completion

1. **Write RESULTS.md** to the output directory with findings, effect sizes, and confidence intervals
2. **Show a summary card** with key findings for the researcher:
   ```python
   section("Conclusions", study=STUDY)
   results_md = "## Key Findings\n..."
   (output_dir / "RESULTS.md").write_text(results_md)
   show(results_md, title="Study Results", study=STUDY)
   ```
3. **Acknowledge limitations** explicitly — show as a card for the record
4. **Suggest validation** on independent data (e.g., eICU if used MIMIC)
5. **Export the complete study** — journal cards + file artifacts in one package:
   ```python
   export("output/study-report.html", study=STUDY)
   ```
