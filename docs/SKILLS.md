# Claude Code Skills

Skills are contextual prompts that teach Claude Code how to accomplish specific tasks. M4 ships with skills that give Claude deep knowledge of the Python API—so when you ask about clinical data analysis, Claude knows exactly how to use M4 effectively.

## What Skills Do

Without a skill, Claude might guess at APIs or make assumptions about how M4 works. With the M4 skill installed, Claude:

- Knows to call `set_dataset()` before any queries
- Understands the difference between MCP tools and the Python API
- Returns proper DataFrames and uses pandas for analysis
- Handles errors correctly with M4's exception hierarchy
- Chooses the right approach based on your task complexity

Skills activate automatically when relevant. Ask Claude to "analyze patient outcomes in MIMIC" and it will use the M4 API without you needing to explain how.


## Installing Skills

During initial setup:

```bash
m4 config claude --skills
```

Or install to an existing project:

```bash
# Navigate to your project
cd my-research

# Install skills to .claude/skills/
python -c "from m4.skills import install_skills; install_skills()"
```

Skills are installed to `.claude/skills/` in your project directory. Claude Code automatically discovers skills in this location.


## Available Skills

### m4-api

**Triggers on:** "M4 API", "query MIMIC with Python", "clinical data analysis", "EHR data", "execute SQL on MIMIC"

This skill teaches Claude the complete M4 Python API:

- **Required workflow**: Always `set_dataset()` first
- **Return types**: DataFrames from queries, dicts from schema functions
- **Error handling**: Using `DatasetError`, `QueryError`, `ModalityError`
- **Best practices**: When to use API vs MCP tools, handling large results

Example interaction with the skill active:

> **You:** Analyze the relationship between age and ICU length of stay in MIMIC-IV
>
> **Claude:** *Uses the M4 API to query icustays joined with patients, computes statistics, and creates visualizations—all using proper M4 patterns*


## Skill Structure

Each skill is a directory containing a `SKILL.md` file:

```
.claude/skills/
└── m4-api/
    └── SKILL.md
```

The `SKILL.md` contains:

```markdown
---
name: m4-api
description: Use the M4 Python API to query clinical datasets...
---

# M4 Python API

[Detailed instructions for Claude...]
```

The frontmatter defines when the skill activates. The body teaches Claude how to use the capability.


## Creating Custom Skills

You can extend M4 with project-specific skills. Create a skill for your research domain:

```markdown
---
name: sepsis-analysis
description: Analyze sepsis cohorts using M4. Triggers on "sepsis", "SOFA score", "infection"
---

# Sepsis Analysis Patterns

When analyzing sepsis in M4:

1. Use Sepsis-3 criteria (SOFA >= 2 with suspected infection)
2. Query the `diagnoses_icd` table for infection codes
3. Join with `chartevents` for SOFA components
4. Consider using `mimic-iv-note` for clinical context

## Standard Cohort Query

\`\`\`python
from m4 import set_dataset, execute_query

set_dataset("mimic-iv")
sepsis_cohort = execute_query("""
    SELECT DISTINCT subject_id
    FROM diagnoses_icd
    WHERE icd_code LIKE 'A41%'  -- Sepsis ICD-10 codes
""")
\`\`\`
```

Place in `.claude/skills/sepsis-analysis/SKILL.md` and Claude will use it when discussing sepsis research.


## Tips for Effective Skills

**Be specific about triggers.** The description should clearly indicate when the skill applies. Too broad and it activates unnecessarily; too narrow and it won't help.

**Include working code examples.** Claude learns patterns from examples. Show the exact imports, function calls, and expected outputs.

**Document edge cases.** What errors might occur? What datasets are required? What modalities are needed?

**Keep skills focused.** One skill per domain or workflow. Combine related but distinct capabilities in separate skills.


## Verifying Installation

Check which M4 skills are installed:

```python
from m4.skills import get_installed_skills

print(get_installed_skills())  # ['m4-api']
```

Or look in your project:

```bash
ls .claude/skills/
# m4-api/
```
