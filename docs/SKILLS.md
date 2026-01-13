# Agent Skills

Skills are contextual prompts that teach AI coding assistants how to accomplish specific tasks. M4 ships with 17 skills: one for the Python API, and 16 clinical research skills extracted from MIT-LCP validated code repositories.

## What Skills Do

Without skills, an AI assistant might guess at APIs or make assumptions about clinical concepts. With M4 skills installed:

- **m4-api**: Claude knows to call `set_dataset()` before queries, returns proper DataFrames, handles errors correctly
- **Clinical skills**: Claude understands SOFA scoring, Sepsis-3 criteria, KDIGO AKI staging, and other validated clinical concepts

Skills activate automatically when relevant. Ask Claude to "calculate SOFA scores for my cohort" and it will use the validated SQL from MIT-LCP without you needing to look up the implementation.


## Installing Skills

During initial setup:

```bash
m4 config claude --skills
```

Or install to an existing project:

```bash
# Interactive tool selection
m4 skills

# Install for specific tools
m4 skills --tools claude,cursor

# List installed skills
m4 skills --list
```

Skills are installed to `.claude/skills/` (or equivalent for other tools). AI assistants automatically discover skills in these locations.


## Available Skills

### M4 Framework

| Skill | Triggers On | Description |
|-------|-------------|-------------|
| **m4-api** | "M4 API", "query MIMIC with Python", "clinical data analysis" | Complete Python API usage including `set_dataset()`, DataFrame handling, error handling |

### Severity Scores

| Skill | Triggers On | Description |
|-------|-------------|-------------|
| **sofa-score** | "SOFA", "organ failure", "sepsis severity" | Sequential Organ Failure Assessment - 6 organ systems, 0-24 points |
| **apsiii-score** | "APACHE III", "APACHE 3", "mortality prediction" | Acute Physiology Score III with mortality prediction |
| **sapsii-score** | "SAPS-II", "SAPS 2", "ICU severity" | Simplified Acute Physiology Score II |
| **oasis-score** | "OASIS", "severity score without labs" | Oxford Acute Severity of Illness Score (no lab values required) |
| **lods-score** | "LODS", "logistic organ dysfunction" | Logistic Organ Dysfunction Score - 6 systems with weighted scoring |
| **sirs-criteria** | "SIRS", "inflammatory response", "SIRS vs sepsis" | Systemic Inflammatory Response Syndrome criteria |

### Sepsis and Infection

| Skill | Triggers On | Description |
|-------|-------------|-------------|
| **sepsis-3-cohort** | "Sepsis-3", "sepsis cohort", "SOFA infection" | Sepsis-3 identification: SOFA >= 2 with suspected infection |
| **suspicion-of-infection** | "suspected infection", "antibiotic culture" | Suspected infection events using antibiotic + culture timing |

### Organ Failure

| Skill | Triggers On | Description |
|-------|-------------|-------------|
| **kdigo-aki-staging** | "KDIGO", "AKI staging", "acute kidney injury" | KDIGO AKI staging using creatinine and urine output criteria |

### Medications and Treatments

| Skill | Triggers On | Description |
|-------|-------------|-------------|
| **vasopressor-equivalents** | "vasopressor", "norepinephrine equivalent", "NEE" | Norepinephrine-equivalent dose calculation for vasopressor comparison |

### Laboratory and Measurements

| Skill | Triggers On | Description |
|-------|-------------|-------------|
| **baseline-creatinine** | "baseline creatinine", "pre-admission creatinine" | Baseline creatinine estimation for AKI assessment |
| **gcs-calculation** | "GCS", "Glasgow Coma Scale", "consciousness" | Glasgow Coma Scale extraction with intubation handling |

### Cohort Definitions

| Skill | Triggers On | Description |
|-------|-------------|-------------|
| **first-icu-stay** | "first ICU stay", "exclude readmissions", "independent observations" | First ICU stay selection for cohort construction |

### Data Quality and Structure

| Skill | Triggers On | Description |
|-------|-------------|-------------|
| **mimic-table-relationships** | "table relationships", "join tables", "MIMIC structure" | MIMIC-IV table relationships, join patterns, identifier hierarchy |
| **mimic-eicu-mapping** | "MIMIC to eICU", "cross-database", "external validation" | Mapping equivalent concepts between MIMIC-IV and eICU |
| **clinical-research-pitfalls** | "immortal time bias", "information leakage", "selection bias" | Common methodological mistakes and how to avoid them |


## Skill Structure

Each skill is a directory containing a `SKILL.md` file:

```
.claude/skills/
├── m4-api/
│   └── SKILL.md
├── sofa-score/
│   └── SKILL.md
│   └── scripts/
│       └── sofa.sql
├── sepsis-3-cohort/
│   └── SKILL.md
│   └── scripts/
│       └── sepsis3.sql
...
```

The `SKILL.md` contains:

```markdown
---
name: sofa-score
description: Calculate SOFA score for ICU patients...
---

# SOFA Score Calculation

[Detailed instructions, SQL examples, clinical context...]
```

Clinical skills include validated SQL scripts in their `scripts/` subdirectory.


## Creating Custom Skills

You can extend M4 with project-specific skills. Create a skill for your research domain:

```markdown
---
name: cardiac-surgery-cohort
description: Identify cardiac surgery patients. Triggers on "CABG", "valve replacement", "cardiac surgery"
---

# Cardiac Surgery Cohort Selection

When identifying cardiac surgery patients in MIMIC-IV:

1. Use procedure codes from `procedures_icd` table
2. Filter by ICD-10-PCS codes starting with '02' (heart and great vessels)
3. Consider combining with `d_icd_procedures` for code descriptions

## Standard Query

\`\`\`python
from m4 import set_dataset, execute_query

set_dataset("mimic-iv")
cardiac_cohort = execute_query("""
    SELECT DISTINCT p.subject_id, p.hadm_id
    FROM procedures_icd p
    WHERE p.icd_code LIKE '02%'
      AND p.icd_version = 10
""")
\`\`\`
```

Place in `.claude/skills/cardiac-surgery-cohort/SKILL.md` and Claude will use it when discussing cardiac surgery research.


## Tips for Effective Skills

**Be specific about triggers.** The description should clearly indicate when the skill applies. Too broad and it activates unnecessarily; too narrow and it won't help.

**Include working code examples.** Claude learns patterns from examples. Show exact imports, function calls, and expected outputs.

**Document edge cases.** What errors might occur? What datasets are required? What modalities are needed?

**Keep skills focused.** One skill per domain or workflow. Combine related but distinct capabilities in separate skills.

**Reference validated sources.** Clinical skills should cite their sources (e.g., "based on MIT-LCP mimic-code repository").


## Verifying Installation

Check which M4 skills are installed:

```bash
m4 skills --list
```

Or look in your project:

```bash
ls .claude/skills/
# m4-api/  sofa-score/  sepsis-3-cohort/  ...
```


## Clinical Skill Sources

All clinical research skills are extracted from MIT-LCP validated repositories:

- **mimic-code**: https://github.com/MIT-LCP/mimic-code
- **eicu-code**: https://github.com/MIT-LCP/eicu-code

These repositories contain peer-reviewed implementations used in hundreds of published studies.
