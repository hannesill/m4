---
name: create-m4-skill
description: Guide users through creating M4 skills with proper structure, provenance tracking, and tier assignment. Use when users want to create a new M4 skill, document a clinical concept, or contribute a skill to the M4 skills library.
tier: community
category: system
---

# M4 Skill Creator

This skill guides you through creating properly formatted M4 skills with complete provenance tracking and appropriate tier and category assignment.

## When to Use This Skill

- User asks to create a new M4 skill
- User wants to document a clinical scoring system, cohort definition, or research pattern
- User wants to document an M4 framework feature or workflow
- User mentions "new skill", "create skill", "document [concept]"
- User wants to contribute to the M4 skills library

## Interactive Creation Process

Follow these steps in order. At each step, gather information from the contributor and validate completeness before proceeding.

### Step 1: Understanding the Skill

**Interview the contributor with these questions:**

1. What concept does this skill address?
2. Is this a **clinical** skill (scoring system, cohort definition, lab interpretation, medication calculation) or a **system** skill (M4 framework feature, data structure, workflow pattern)?
3. When should an AI assistant activate this skill? (Specific triggers)
4. Is this based on:
   - Published source code (e.g., MIT-LCP mimic-code)?
   - Original domain expertise?
   - Community contribution?
5. What are the key references? (Publications for clinical, documentation/repos for system)

**Do NOT auto-generate answers.** Wait for contributor input at each question.

### Step 2: Determine Category and Tier

Based on their answers, assign category and guide tier selection:

**Category** (from question 2):
- `clinical` — Encodes clinical domain knowledge
- `system` — Encodes M4 framework knowledge, data structure guidance, or meta-skills

**Tier selection for clinical skills:**

- **`validated`** — Derives from published, validated source (mimic-code, peer-reviewed paper). Has URL to source. Will be reviewed by at least one clinician for clinical accuracy.
- **`expert`** — Original work by a clinician or domain expert. Will be reviewed by at least one independent clinician. Creator has clinical expertise.
- **`community`** — Contribution without required clinical reviews. Technical review for correctness.

**Tier selection for system skills:**

- **`validated`** — Based on documented, stable APIs or established patterns. Will be reviewed for technical accuracy.
- **`expert`** — Original work by someone with relevant technical expertise. Will be reviewed by at least one independent technical reviewer.
- **`community`** — Contribution with technical review for correctness.

**Ask:** "Based on your answers, this appears to be a [category] skill at [tier] tier. Does that sound right? Who will review it?"

### Step 3: Create Frontmatter

Construct the YAML header using exactly these four fields:

```yaml
---
name: kebab-case-name
description: One-sentence description stating what the skill does and when to use it.
tier: [validated|expert|community]
category: [clinical|system]
---
```

**Guidelines:**
- `name`: Match directory name, use kebab-case
- `description`: Should trigger skill activation. Include "Use for..." or "Use when..." context.
- `tier`: From Step 2
- `category`: From Step 2
- No other fields in the frontmatter. Licensing, authorship, and source URLs go in PROVENANCE.yaml.

### Step 4: Structure the Body

Guide them through these required sections:

```markdown
# [Skill Title]

Brief introduction (1-2 sentences).

## When to Use This Skill

- [Bullet list of activation scenarios]
- [Be specific about contexts]

## [Core Content Sections]

[Tables, thresholds, scoring criteria, API reference,
workflow steps — whatever is needed]

## Critical Implementation Notes

[Gotchas, edge cases, common mistakes to avoid]

## Example Queries

[Working SQL or code examples with logic explained in comments]

## References

- [Author et al. "Title." Journal. Year;Volume:Pages.]
```

**Interview questions for clinical skills:**
- "What are the core components or criteria?"
- "What mistakes do people commonly make?"
- "Can you provide a working SQL example?"
- "What are the 2-3 key publications?"

**Interview questions for system skills:**
- "What is the primary workflow or API surface?"
- "What are the common pitfalls or misuse patterns?"
- "Can you provide a working code example?"
- "What documentation or repos should be referenced?"

**Dataset-agnostic design:** Keep the body focused on the concept, not dataset-specific implementations. If dataset-specific SQL is needed, put it in separate script files (`scripts/mimic-iv.sql`, `scripts/eicu.sql`) rather than embedding multiple versions in the body.

**Important:** Don't add content the contributor hasn't provided. Ask questions to fill gaps.

### Step 5: Create PROVENANCE.yaml

Build provenance file with contributor input:

```yaml
sources:
  - url: [Ask: "What's the source URL?"]
    description: [Ask: "What does this source provide?"]
    license: [Ask: "What license?" Common: Apache-2.0, CC-BY-4.0, MIT]

created:
  by: [Ask: "Your name and credentials?" Format: "Jane Smith, MD"]
  role: [authoring|clinical-extraction|adaptation]
  date: [Use today's date: YYYY-MM-DD]

reviews:
  - by: [Ask: "Who will review this?" Format: "John Doe, MD"]
    date: [Leave TBD or set future date]
    scope: [clinical-accuracy for clinical skills, technical-accuracy for system skills]
    notes: [Optional - ask if they want to add notes]

references:
  - [Same as SKILL.md references - ask them to confirm]

changelog:
  - version: "1.0"
    date: [Today's date]
    summary: Initial skill creation
```

**Special cases:**
- No `sources` section if original work with no external source
- `reviews` required for `validated` and `expert` tiers
- `reviews` can be TBD with future dates if review is pending

### Step 6: Validation Checklist

Before finalizing, verify with the contributor:

**SKILL.md:**
- [ ] Valid YAML frontmatter with exactly four fields: name, description, tier, category
- [ ] Name matches directory name (kebab-case)
- [ ] Description includes "Use for..." or "Use when..." triggers
- [ ] "When to Use This Skill" section present
- [ ] At least one working example (SQL or code)
- [ ] References section with key publications or documentation
- [ ] Body is dataset-agnostic (dataset-specific SQL in scripts/ if needed)
- [ ] No over-engineering (only what's needed for the AI to use the skill correctly)

**PROVENANCE.yaml:**
- [ ] Creator name and credentials included
- [ ] Role matches skill origin
- [ ] Reviews listed (with at least one for validated/expert)
- [ ] Sources documented (if applicable)
- [ ] Changelog has initial entry

**Ask:** "I've checked the structure. Would you like me to create the files now, or would you like to review the content first?"

## Implementation Notes

1. **Create directory structure:**
   ```bash
   mkdir -p src/m4/skills/[skill-name]
   ```

2. **Write files:**
   - Write `SKILL.md` with frontmatter and body
   - Write `PROVENANCE.yaml` with complete provenance

3. **If SQL scripts exist:**
   ```bash
   mkdir -p src/m4/skills/[skill-name]/scripts
   ```
   Use separate files per dataset: `mimic-iv.sql`, `eicu.sql`.

4. **Verify files are created:**
   Read back both files to confirm they exist and are well-formed.

5. **Update SKILLS_INDEX.md:**
   Add the new skill to the appropriate category table.

## Quality Guidelines

**Context efficiency:**
- Only include information the AI doesn't already know
- Be precise about edge cases
- Keep skills focused and scoped

**Dataset-agnostic design:**
- Document the concept, not the dataset
- SQL in the body should work across datasets or use generic table references
- Dataset-specific implementations go in `scripts/`

**Maintainability:**
- Clear provenance enables future updates
- Examples serve as regression tests
- References enable verification

## Anti-Patterns to Avoid

- **Don't auto-generate content:** Wait for contributor input at every step
- **Don't skip provenance:** Required for scientific accountability
- **Don't add boilerplate:** Only include what's needed for the AI
- **Don't guess tier or category:** Interview to determine proper assignment
- **Don't skip reviews:** Validated/expert tiers require reviews
- **Don't embed dataset-specific SQL in the body:** Use the scripts/ directory
- **Don't add extra frontmatter fields:** Only name, description, tier, category

## Reference

For the canonical format specification, see `src/m4/skills/SKILL_FORMAT.md`.
