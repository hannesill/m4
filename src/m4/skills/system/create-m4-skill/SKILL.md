---
name: create-m4-skill
description: Write a new M4 skill with a contributor - interview, SKILL.md, PROVENANCE.yaml, and an example tested on real data. Use when the user wants to create, write or contribute an M4 skill, or turn a clinical score, cohort definition, research method or M4 workflow into one.
tier: community
category: system
kind: authoring
---

# Create an M4 Skill

The contributor supplies the knowledge; you write it in M4's skill format and test it. Read
the format first: `src/m4/skills/SKILL_FORMAT.md` in an M4 checkout, otherwise the copy that
`python -c "import m4.skills, pathlib; print(pathlib.Path(m4.skills.__file__).with_name('SKILL_FORMAT.md'))"`
prints. It defines the frontmatter (including the optional `kind`), the body, PROVENANCE.yaml
and the tiers.

## Steps

1. **Location.** In an M4 checkout (`src/m4/skills/` exists), write to
   `src/m4/skills/<clinical|system>/<name>/`. Otherwise write to the user's skill folder
   (`.claude/skills/<name>/`, `.agents/skills/<name>/`, or wherever their agent reads skills)
   and tell them the skill is local only; contributing it takes a pull request to M4.
2. **Interview.** Ask in one message for what you cannot infer: the concept and the questions
   it answers (they become the triggers), clinical or system, the source (published code,
   paper, or the contributor's own expertise) with URL and license, components and
   thresholds, the mistakes people make, 2-3 references, and the contributor's name and
   credentials. Every clinical fact must come from the contributor or a cited source; ask
   about gaps instead of filling them. Done when you can fill every required field of
   SKILL_FORMAT.md.
3. **SKILL.md.** The description is the trigger: what the skill does first, then the words a
   user would say, one trigger per distinct case. In the body, put what every use needs first,
   then the gotchas that would otherwise give wrong results, then references; leave out what
   a capable model already knows. Keep the body dataset-agnostic. Dataset SQL goes in
   `scripts/`, one file per table it builds, named after it (`sofa.sql`, `kdigo_stages.sql`),
   with a folder per dataset when there are several (`scripts/mimic-iv/charlson.sql`).
4. **Test the example.** Write the example query or code yourself and run it on a usable
   dataset (`"prepared": true` in `m4 list-datasets --json`) with
   `m4 query --dataset <name> --sql "..."` or `execute_query`. Show the contributor the output
   and fix the example until it runs and they confirm the result. `mimiciv_derived` exists
   only on full MIMIC-IV after `m4 init-derived`. If no dataset is usable, tell the
   contributor the example is untested; never download or initialise data yourself.
5. **PROVENANCE.yaml.** `created` holds the contributor's name and credentials, the role
   (`authoring`, `clinical-extraction` or `adaptation`) and today's date; `sources` lists URL,
   description and license of anything extracted or adapted; `changelog` starts at `"1.0"`.
   A new skill is tier `community` with no `reviews`. Add a review only once it has happened,
   with reviewer, date and scope, and raise the tier only when the reviews meet
   SKILL_FORMAT.md's requirements for it.
6. **Register.** In an M4 checkout, add the skill to the matching table in
   `src/m4/skills/SKILLS_INDEX.md` and run
   `uv run pytest tests/test_skills_index.py tests/test_skills_catalog.py`. Finish by showing
   the contributor both files and where they were written.
