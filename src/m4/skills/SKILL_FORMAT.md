# Skill Format Reference

This document defines how M4 skills should be structured, including metadata, provenance tracking, the tier system for trust levels, and the category system for skill types.

## Design Principles

**Dataset-agnostic by default.** Skills should document concepts, not dataset-specific implementations. A SOFA score is a SOFA score regardless of whether it's computed from MIMIC-IV or eICU. The SKILL.md body describes the clinical logic (thresholds, components, edge cases) in a dataset-agnostic way. Dataset-specific SQL goes in separate script files.

**Context-efficient.** SKILL.md is loaded into AI context. Every line should earn its place. Provenance, licensing, and authorship belong in PROVENANCE.yaml, not in the frontmatter. The body should only include information the AI can't already infer.

**Minimal frontmatter.** Four fields. Everything else belongs in the body or in PROVENANCE.yaml.

## Skill Directory Structure

Skills are organized by category under `src/m4/skills/`:

```
src/m4/skills/
├── clinical/           # Clinical domain knowledge
│   ├── sofa-score/
│   │   ├── SKILL.md
│   │   ├── PROVENANCE.yaml
│   │   └── scripts/
│   │       └── mimic-iv.sql
│   ├── sepsis-3-cohort/
│   │   └── ...
│   └── ...
├── system/             # M4 framework and data structure knowledge
│   ├── m4-api/
│   │   └── SKILL.md
│   └── ...
├── installer.py
├── SKILL_FORMAT.md
└── SKILLS_INDEX.md
```

Each skill directory follows this structure:

```
skill-name/
├── SKILL.md            # Metadata + content (loaded into AI context)
├── PROVENANCE.yaml     # Provenance and audit trail (not loaded into AI context)
└── scripts/            # SQL implementations (optional)
    ├── mimic-iv.sql    # Dataset-specific scripts in separate files
    └── eicu.sql
```

When installed to agent tool directories (e.g., `.claude/skills/`), skills are flattened — the category subdirectories are not preserved. This ensures compatibility with all agent tools regardless of their skill discovery mechanism.

## SKILL.md

The skill file has two parts: a YAML frontmatter header and a markdown body.

### Frontmatter

```yaml
---
name: sofa-score
description: Calculate SOFA (Sequential Organ Failure Assessment) score for ICU patients. Use for sepsis severity assessment, organ dysfunction quantification, mortality prediction, or Sepsis-3 criteria evaluation.
tier: validated
category: clinical
---
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Kebab-case identifier matching the directory name. |
| `description` | Yes | One-sentence description. Should state what the skill does and when to use it. This is what AI assistants match against to decide when to activate the skill. |
| `tier` | Yes | Trust level: `validated`, `expert`, or `community`. See [Tier System](#tier-system) below. |
| `category` | Yes | Skill type: `clinical` or `system`. See [Category System](#category-system) below. |

Keep the frontmatter to these four fields. Licensing, authorship, version, source URLs, and validation status belong in `PROVENANCE.yaml`.

### Body

The body is the content that gets loaded into AI context. Structure it as follows:

```markdown
# Skill Title

Brief introduction (1-2 sentences).

## When to Use This Skill

- Bullet list of scenarios that should trigger this skill

## [Core Content Sections]

For clinical skills: scoring tables, thresholds, required tables,
clinical edge cases, implementation details.

For system skills: API reference, workflow steps, code examples,
configuration details.

## Critical Implementation Notes

Gotchas, edge cases, common mistakes to avoid.

## Example Queries

SQL or code examples with comments explaining the logic.

## References

- Author et al. "Title." Journal. Year;Volume:Pages.
```

**Guidelines for the body:**

- Write for an AI assistant that needs to generate correct queries or follow correct workflows. Be precise about edge cases, units, and thresholds.
- Be aware of context constraints. Only include information that is not trivial to the model and keep the skill focused in scope.
- Include working examples — these are the most valuable part for the AI.
- Keep "Critical Implementation Notes" sections for gotchas that would otherwise lead to wrong results (e.g., "FiO2 can come from blood gas OR charted values", "ICD codes are assigned at discharge, not admission").
- **Keep SQL examples dataset-agnostic where possible.** If dataset-specific SQL is needed, put it in the `scripts/` directory with one file per dataset (e.g., `scripts/mimic-iv.sql`, `scripts/eicu.sql`) rather than embedding multiple versions in the body.
- End with a brief references section citing key publications or documentation. 2-3 citations is typical.

## PROVENANCE.yaml

This file tracks who created the skill, who reviewed it, and where the content comes from. It is never loaded into AI context — it exists for human audit and scientific accountability.

```yaml
sources:
  - url: https://github.com/MIT-LCP/mimic-code/tree/main/mimic-iv/concepts/score
    description: MIT-LCP mimic-code SOFA implementation
    license: Apache-2.0

created:
  by: Jane Smith, MD
  role: clinical-extraction
  date: 2025-01-15

reviews:
  - by: John Doe, MD
    date: 2025-01-20
    scope: clinical-accuracy
    notes: Verified scoring thresholds against Vincent 1996. Confirmed respiratory score ventilation handling.

references:
  - Vincent JL et al. "The SOFA score..." Intensive Care Medicine. 1996;24(7):707-710.
  - Singer M et al. "Sepsis-3." JAMA. 2016;315(8):801-810.

changelog:
  - version: "1.0"
    date: 2025-01-15
    summary: Initial extraction from mimic-code
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `sources` | If applicable | Where the skill content originates. Include URL, short description, and license of each source. Omit for original work with no external source. |
| `sources[].url` | Yes | URL to the source repository or publication. |
| `sources[].description` | Yes | What this source provides. |
| `sources[].license` | Yes | License of the source material. |
| `created.by` | Yes | Name and credentials of the creator. |
| `created.role` | Yes | One of: `authoring` (original work), `clinical-extraction` (extracted from source), `adaptation` (adapted from existing skill). |
| `created.date` | Yes | ISO date (YYYY-MM-DD). |
| `reviews` | Yes for `validated` and `expert` tiers | List of reviews the skill has undergone. |
| `reviews[].by` | Yes | Name and credentials of the reviewer. |
| `reviews[].date` | Yes | ISO date of review completion. |
| `reviews[].scope` | Yes | What was reviewed: `clinical-accuracy`, `sql-correctness`, `technical-accuracy`, `completeness`, or a combination. |
| `reviews[].notes` | No | Specific observations or verification notes. |
| `references` | No | Full citations for key publications. Duplicates the brief references in the SKILL.md body — this is intentional so the provenance file is self-contained. |
| `changelog` | Yes | Version history with dates and summaries. |

## Category System

Skills fall into one of two categories based on what they encode:

### `clinical`

The skill encodes clinical domain knowledge — scoring systems, cohort definitions, lab interpretation, organ failure criteria, medication calculations, or research methodology with clinical content.

**Examples:** sofa-score, sepsis-3-cohort, kdigo-aki-staging, clinical-research-pitfalls

### `system`

The skill encodes M4 framework knowledge, data structure guidance, workflow patterns, or meta-skills for contributing to M4.

**Examples:** m4-api, m4-research, mimic-table-relationships, create-m4-skill

Category is orthogonal to tier — a system skill can be `validated` (well-reviewed) just as a clinical skill can be `community` (contributed without clinical review).

## Tier System

Skills are assigned one of three tiers based on their origin and review process. Tier requirements differ slightly between clinical and system skills:

### `validated`

The skill derives from a published, externally validated source and has been reviewed.

**Requirements for clinical skills:**

- Published source with URL in `PROVENANCE.yaml`
- SQL scripts verified against source implementation
- At least one clinician review on record with `scope: clinical-accuracy`

**Requirements for system skills:**

- Based on documented, stable APIs or established patterns
- At least one technical review on record with `scope: technical-accuracy`

**Example:** SOFA score skill extracted from mimic-code, reviewed by an intensivist who verified the scoring thresholds match Vincent 1996.

### `expert`

The skill is original work created by a domain expert and reviewed by at least one other expert. No published source code is required.

**Requirements for clinical skills:**

- Creator has clinical domain expertise (indicated by credentials in `created.by`)
- At least one independent clinician review on record
- Review must cover `clinical-accuracy`

**Requirements for system skills:**

- Creator has relevant technical expertise
- At least one independent technical review on record
- Review must cover `technical-accuracy`

**Example:** A skill describing best practices for defining sepsis cohorts, written by a critical care physician and reviewed by another.

### `community`

A community contribution reviewed for correctness but not necessarily by a domain expert.

**Requirements:**

- Technical review for correctness and format compliance
- Domain-specific review encouraged but not required
- `PROVENANCE.yaml` must still document creator and any reviews

**Example:** A skill for calculating BMI from charted height/weight, contributed by a data scientist and reviewed for SQL correctness.

## Complete Example

### `example-score/SKILL.md`

```markdown
---
name: example-score
description: Calculate Example Score for ICU patients. Use for severity assessment or risk stratification.
tier: expert
category: clinical
---

# Example Score Calculation

The Example Score estimates severity using 3 components, each scored 0-4.

## When to Use This Skill

- User asks about Example Score
- Severity stratification in surgical ICU patients
- Risk adjustment in comparative studies

## Components and Scoring

| Component | 0 | 1 | 2 | 3 | 4 |
|-----------|---|---|---|---|---|
| Heart Rate | 60-100 | 101-120 | 121-140 | 141-160 | >160 |
| Systolic BP | 100-140 | 85-99 | 70-84 | 55-69 | <55 |
| Temperature | 36-37.5 | 37.6-38.5 | 38.6-39.5 | 39.6-40.5 | >40.5 |

## Critical Implementation Notes

1. **Time window**: Use worst value in the first 24 hours after ICU admission.
2. **Missing components**: Document which components are missing. Do not impute as 0.

## Example: Score at 24 Hours

​```sql
SELECT
    stay_id,
    hr_score + sbp_score + temp_score AS example_score
FROM mimiciv_derived.example_score
WHERE hr = 24;
​```

## References

- Author A et al. "Example Score validation." Journal. 2023;1(1):1-10.
```

### `example-score/PROVENANCE.yaml`

```yaml
sources:
  - url: https://doi.org/10.xxxx/example
    description: Original Example Score publication
    license: CC-BY-4.0

created:
  by: Alice Chen, MD
  role: authoring
  date: 2025-06-01

reviews:
  - by: Bob Martinez, MD
    date: 2025-06-15
    scope: clinical-accuracy
    notes: Verified thresholds against original publication Table 2.

references:
  - Author A et al. "Example Score validation." Journal. 2023;1(1):1-10.

changelog:
  - version: "1.0"
    date: 2025-06-01
    summary: Initial skill creation
```
