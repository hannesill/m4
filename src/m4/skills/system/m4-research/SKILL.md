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

## Phase 1: Research Interview

**Before writing any queries, interview the user to establish:**

### 1. Research Question
Ask: "What specific clinical question are you trying to answer?"

Good questions are:
- Specific and answerable with available data
- Clinically meaningful
- Novel or confirmatory of existing findings

Help refine vague questions:
- "Are sicker patients dying more?" → "Is day-1 SOFA score independently associated with 30-day mortality in sepsis patients?"

### 2. Study Design
Ask: "What type of study is this?"

- **Descriptive**: Characterize a population (demographics, distributions)
- **Comparative**: Compare groups (exposed vs unexposed, treatment A vs B)
- **Predictive**: Build or validate a prediction model
- **Exploratory**: Hypothesis-generating analysis

### 3. Outcome Variable
Ask: "What is your primary outcome?"

Common outcomes and how to define them:
- **In-hospital mortality**: `hospital_expire_flag` in admissions table
- **30-day mortality**: Compare `dod` to discharge time + 30 days
- **ICU length of stay**: `los` in icustays, be wary of survivor bias
- **Ventilation duration**: Requires careful definition (see m4 skills)
- **Readmission**: Subsequent `hadm_id` for same `subject_id`

### 4. Exposure/Intervention
Ask: "What exposure or intervention are you studying?"

For treatment comparisons:
- How is treatment defined? (any use vs duration vs dose)
- When is exposure status determined? (admission, 24h, 48h)
- What's the comparator? (no treatment, alternative treatment)

### 5. Population (Inclusion/Exclusion)
Ask: "Who should be included in this study?"

Standard considerations:
- First ICU stay only? (avoid correlated observations)
- Age restrictions? (pediatric exclusion common)
- Minimum ICU stay? (be careful of immortal time bias)
- Specific diagnoses? (how defined - ICD codes have limitations)

### 6. Confounders
Ask: "What factors might confound your results?"

Common confounders in ICU research:
- Age, sex, comorbidities
- Illness severity (SOFA, APACHE, SAPS)
- Admission type (medical vs surgical vs trauma)
- Hospital/unit effects

### 7. Dataset Selection
Ask: "Which dataset should we use?"

- **mimic-iv**: Full MIMIC-IV (requires access)
- **mimic-iv-demo**: 100 patients, good for testing queries
- **mimic-iv-note**: MIMIC-IV with clinical notes
- **eicu**: Multi-center ICU data (different schema)

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

**Agent creates the study and interviews:**

```python
STUDY = "early-vasopressors-sepsis-v1"
output_dir = register_output_dir(study=STUDY)
```

1. **Research Question**: "Let me help refine this. By 'early', do you mean within 1 hour, 6 hours, or 24 hours of sepsis onset? And by 'mortality', do you mean in-hospital, 28-day, or 90-day?"

2. **Study Design**: "This is a comparative study - you're comparing early vs. late/no vasopressor use. We'll need to carefully define the comparison groups to avoid immortal time bias."

3. **Outcome**: "Let's use 28-day mortality so we capture both in-hospital and post-discharge deaths."

4. **Exposure**: "I recommend defining 'early' as vasopressor initiation within 6 hours of suspected infection onset (using the suspicion-of-infection skill). The comparison group would be those who received vasopressors >6h or never."

5. **Population**: "I suggest: adult patients (>=18), first ICU stay, meeting Sepsis-3 criteria. Exclude patients who died within 6 hours (immortal time) and those on vasopressors at admission."

6. **Confounders**: "We should adjust for: age, SOFA score at sepsis onset, admission source, comorbidities. I recommend using propensity score matching given this is an observational treatment comparison."

7. **Dataset**: "Let's use mimic-iv. The demo dataset is too small for treatment effect studies."

**Agent drafts protocol, saves it, and asks for approval:**

```python
(output_dir / "PROTOCOL.md").write_text(protocol_md)
response = show(protocol_md, title="Research Protocol", wait=True, prompt="Approve?", study=STUDY)
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
