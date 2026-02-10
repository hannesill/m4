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

**Collect study parameters through a vitrine form.** This captures the researcher's intent in the study journal from the start.

Tell the researcher what you've posted before the blocking call:

> "I've posted the study parameters form in vitrine. Please fill in your research question, study design, and key parameters — I'll review everything and discuss refinements before we proceed."

```python
from m4.vitrine import Form, TextInput, RadioGroup, Dropdown

response = show(
    Form([
        TextInput("question", label="Research Question",
                  placeholder="e.g., Is day-1 SOFA independently associated with 30-day mortality in sepsis?"),
        RadioGroup("design", ["Descriptive", "Comparative", "Predictive", "Exploratory"],
                   label="Study Design"),
        TextInput("outcome", label="Primary Outcome",
                  placeholder="e.g., 30-day mortality, in-hospital mortality, ICU LOS"),
        TextInput("exposure", label="Exposure / Intervention",
                  placeholder="e.g., Vasopressor within 6h of sepsis onset (blank for descriptive studies)"),
        TextInput("population", label="Population & Exclusions",
                  placeholder="e.g., Adult, first ICU stay, Sepsis-3, exclude death <6h"),
        TextInput("confounders", label="Key Confounders",
                  placeholder="e.g., Age, SOFA, admission source, comorbidities"),
        Dropdown("dataset", ["mimic-iv", "mimic-iv-demo", "eicu", "mimic-iv-note"],
                 label="Dataset"),
    ]),
    title="Study Parameters",
    prompt="Define your research study",
    study=STUDY,
)

params = response.values
```

### Reviewing the Response

After the researcher submits the form, review each parameter in the terminal and discuss refinements before proceeding to the protocol.

**Research Question** — Should be specific and answerable with available data. Help refine vague questions:
- "Are sicker patients dying more?" → "Is day-1 SOFA score independently associated with 30-day mortality in sepsis patients?"

**Outcome** — Common outcomes and how to define them:
- **In-hospital mortality**: `hospital_expire_flag` in admissions table
- **30-day mortality**: Compare `dod` to discharge time + 30 days
- **ICU length of stay**: `los` in icustays, be wary of survivor bias
- **Readmission**: Subsequent `hadm_id` for same `subject_id`

**Exposure** — For treatment comparisons, check:
- How is treatment defined? (any use vs duration vs dose)
- When is exposure status determined? (admission, 24h, 48h)
- What's the comparator? (no treatment, alternative treatment)

**Population** — Standard considerations:
- First ICU stay only? (avoid correlated observations)
- Age restrictions? (pediatric exclusion common)
- Minimum ICU stay? (be careful of immortal time bias)
- Specific diagnoses? (ICD codes are assigned at discharge — information leakage risk)

**Confounders** — Common in ICU research:
- Age, sex, comorbidities
- Illness severity (SOFA, APACHE, SAPS)
- Admission type (medical vs surgical vs trauma)
- Hospital/unit effects

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

**Agent creates the study and shows the interview form:**

```python
STUDY = "early-vasopressors-sepsis-v1"
output_dir = register_output_dir(study=STUDY)
```

> "I've posted the study parameters form in vitrine. Please fill in your research question and key study parameters — I'll review everything and we can refine before proceeding."

```python
response = show(
    Form([
        TextInput("question", label="Research Question",
                  placeholder="e.g., Is early vasopressor use associated with lower mortality in sepsis?"),
        RadioGroup("design", ["Descriptive", "Comparative", "Predictive", "Exploratory"],
                   label="Study Design"),
        TextInput("outcome", label="Primary Outcome",
                  placeholder="e.g., 28-day mortality"),
        TextInput("exposure", label="Exposure / Intervention",
                  placeholder="e.g., Vasopressor within 6h of sepsis onset"),
        TextInput("population", label="Population & Exclusions",
                  placeholder="e.g., Adult, first ICU stay, Sepsis-3"),
        TextInput("confounders", label="Key Confounders",
                  placeholder="e.g., Age, SOFA, admission source, comorbidities"),
        Dropdown("dataset", ["mimic-iv", "mimic-iv-demo", "eicu", "mimic-iv-note"],
                 label="Dataset"),
    ]),
    title="Study Parameters",
    prompt="Define your research study",
    study=STUDY,
)
params = response.values
```

**Agent reviews the form response and refines in the terminal:**

> "Good parameters. A few refinements I'd suggest:
>
> Your question says 'early vasopressor use' — I'd recommend defining 'early' as within 6 hours of suspected infection onset, using the suspicion-of-infection skill. The comparator would be vasopressor >6h or never.
>
> For population, we should also exclude patients who died within 6 hours (immortal time bias) and those already on vasopressors at admission.
>
> For confounders, given this is a treatment comparison, I'd recommend propensity score matching rather than just regression adjustment."

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
