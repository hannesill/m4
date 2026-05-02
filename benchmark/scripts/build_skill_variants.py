#!/usr/bin/env python3
"""Generate alternate skill packagings used by the v1.1 rerun campaign.

For each task that has a `skills/<name>/` directory we materialize:

  skills-nosql/<name>/SKILL.md
      The same SKILL.md with all fenced ```sql ... ``` blocks removed.
      Other content (prose, item-id tables, formula descriptions) is preserved.

  skills-decoy/<assigned-skill>/SKILL.md
      A clinically-related but task-mismatched skill, taken from
      `decoy_mapping.json` (see _DECOY_MAPPING below). Used by the
      with-skill-decoy condition to test whether *any* task-relevant
      clinical text helps equally.

  skills-rawsql/<task-name>/SKILL.md
      The public reference SQL for this task wrapped in a minimal SKILL.md
      shell. This is the strongest matched-content control: same
      task-relevant material as WITH-SKILL but stripped of procedural prose.
      Skipped for tasks whose ground-truth SQL is not present.

The decoy assignment is deterministic and recorded in
`benchmark/scripts/decoy_mapping.json` for release auditability.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = BENCHMARK_ROOT / "tasks"
GROUND_TRUTH_DIR = BENCHMARK_ROOT / "ground_truth"
DECOY_MAPPING_PATH = Path(__file__).resolve().parent / "decoy_mapping.json"

RAWSQL_SHELL = """# Reference SQL (matched-content control)

The following block is the public reference SQL used to construct the
ground truth for this task. It is provided verbatim, without procedural
prose, to test whether matched task-relevant content alone explains the
WITH-SKILL gain.

```sql
{sql_body}
```
"""

SQL_FENCE_RE = re.compile(r"```sql\b.*?```", re.DOTALL | re.IGNORECASE)
EMPTY_SECTION_RE = re.compile(r"\n\n\n+")

# Decoy assignment is by clinical-family proximity but with a mismatched target.
# Each task is paired with a skill from a different organ system or scoring
# tradition; never the task's own skill family.
_DECOY_MAPPING: dict[str, str] = {
    # Renal/temporal -> respiratory/temporal interval skill
    "mimic-urine-output-rate": "ventilation-classification",
    "mimic-urine-output-rate-raw": "ventilation-classification",
    # Renal staging -> hepatic single-value
    "mimic-kdigo-48h": "meld-score",
    "mimic-kdigo-48h-raw": "meld-score",
    "mimic-creatinine-baseline": "comorbidity-score",
    "mimic-creatinine-baseline-raw": "comorbidity-score",
    # Hepatic -> renal staging
    "mimic-meld-24h": "kdigo-aki-staging",
    "mimic-meld-24h-raw": "kdigo-aki-staging",
    # Severity score families -> different severity score family
    "mimic-sofa-24h": "sapsii-score",
    "mimic-sofa-24h-raw": "sapsii-score",
    "mimic-sapsii-24h": "oasis-score",
    "mimic-sapsii-24h-raw": "oasis-score",
    "mimic-apsiii-24h": "sofa-score",
    "mimic-apsiii-24h-raw": "sofa-score",
    "mimic-oasis-24h": "apsiii-score",
    "mimic-oasis-24h-raw": "apsiii-score",
    "eicu-oasis": "apsiii-score",
    # Neuro -> hepatic
    "eicu-gcs": "meld-score",
    "mimic-gcs-24h-raw": "meld-score",
    # Inflammatory -> coagulation/hepatic
    "mimic-sirs-24h-raw": "meld-score",
    # Infection -> ventilation
    "mimic-suspicion-infection": "ventilation-classification",
    "mimic-suspicion-infection-raw": "ventilation-classification",
    # Sepsis composite -> renal staging
    "mimic-sepsis3-raw": "kdigo-aki-staging",
    # Comorbidity -> severity score
    "mimic-charlson-raw": "sofa-score",
    # Vasopressor -> renal staging
    "mimic-vasopressor-equivalents": "kdigo-aki-staging",
    "mimic-vasopressor-equivalents-raw": "kdigo-aki-staging",
    # Ventilation -> infection
    "mimic-ventilation": "suspicion-of-infection",
    "mimic-ventilation-raw": "suspicion-of-infection",
}


def strip_sql_fences(text: str) -> str:
    cleaned = SQL_FENCE_RE.sub("[SQL fragment removed by NO-SQL ablation]", text)
    cleaned = EMPTY_SECTION_RE.sub("\n\n", cleaned)
    return cleaned


def _find_canonical_skill(skill_name: str) -> Path | None:
    """Locate a canonical SKILL.md for the named skill anywhere in the benchmark."""
    for path in TASKS_DIR.glob(f"*/*/skills/{skill_name}/SKILL.md"):
        return path
    return None


def _resolve_ground_truth_sql(task_name: str) -> Path | None:
    """Best-effort lookup for the reference SQL used to build ground truth."""
    import tomllib

    toml_path = TASKS_DIR / _family_dir(task_name) / task_name / "task.toml"
    if not toml_path.exists():
        return None
    try:
        config = tomllib.loads(toml_path.read_text())
    except Exception:
        return None
    alias = config.get("ground_truth", {}).get("alias")
    candidates = []
    for stem in (alias, task_name.replace("mimic-", "").replace("eicu-", "")):
        if stem:
            candidates.append(GROUND_TRUTH_DIR / f"{stem}.sql")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _family_dir(task_name: str) -> str:
    """Recover the family directory by scanning tasks/."""
    for path in TASKS_DIR.glob(f"*/{task_name}"):
        return path.parent.name
    return task_name.split("-")[1] if "-" in task_name else task_name


def build_for_task(task_dir: Path) -> dict:
    task_name = task_dir.name
    skills_root = task_dir / "skills"
    if not skills_root.exists():
        return {"task": task_name, "skipped": True, "reason": "no skills dir"}

    nosql_dir = task_dir / "skills-nosql"
    decoy_dir = task_dir / "skills-decoy"
    rawsql_dir = task_dir / "skills-rawsql"

    # Reset to keep this script idempotent.
    for target in (nosql_dir, decoy_dir, rawsql_dir):
        if target.exists():
            shutil.rmtree(target)

    # NO-SQL: copy each skill, strip SQL fences from SKILL.md.
    nosql_dir.mkdir(parents=True)
    for skill_dir in skills_root.iterdir():
        if not skill_dir.is_dir():
            continue
        target = nosql_dir / skill_dir.name
        shutil.copytree(skill_dir, target)
        skill_md = target / "SKILL.md"
        if skill_md.exists():
            original = skill_md.read_text()
            skill_md.write_text(strip_sql_fences(original))

    # DECOY: copy the assigned mismatched skill into skills-decoy/<decoy_name>/.
    decoy_name = _DECOY_MAPPING.get(task_name)
    if decoy_name:
        canonical = _find_canonical_skill(decoy_name)
        if canonical is None:
            raise RuntimeError(
                f"Decoy mapping for {task_name} → {decoy_name} not found in tasks/*/*/skills"
            )
        decoy_target = decoy_dir / decoy_name
        decoy_target.mkdir(parents=True)
        shutil.copy2(canonical, decoy_target / "SKILL.md")
        # Copy any sibling files (scripts, etc.) for parity with normal skills.
        for sibling in canonical.parent.iterdir():
            if sibling.name == "SKILL.md":
                continue
            destination = decoy_target / sibling.name
            if sibling.is_dir():
                shutil.copytree(sibling, destination)
            else:
                shutil.copy2(sibling, destination)

    # RAW-SQL: matched-content control. Only built when a ground-truth SQL
    # file can be located. The skill name uses the task slug so the agent
    # sees a single SKILL.md aligned with the task.
    sql_path = _resolve_ground_truth_sql(task_name)
    rawsql_built = False
    if sql_path is not None:
        rawsql_dir.mkdir(parents=True)
        skill_pkg = rawsql_dir / task_name
        skill_pkg.mkdir()
        body = sql_path.read_text().rstrip()
        (skill_pkg / "SKILL.md").write_text(RAWSQL_SHELL.format(sql_body=body))
        rawsql_built = True

    return {
        "task": task_name,
        "skipped": False,
        "decoy": decoy_name,
        "rawsql_built": rawsql_built,
        "nosql_skills": [p.name for p in (nosql_dir).iterdir() if p.is_dir()],
    }


def main() -> None:
    summary: list[dict] = []
    for task_dir in sorted(TASKS_DIR.glob("*/*/")):
        if not (task_dir / "task.toml").exists():
            continue
        summary.append(build_for_task(task_dir))

    DECOY_MAPPING_PATH.write_text(
        json.dumps({"decoy_mapping": _DECOY_MAPPING, "summary": summary}, indent=2)
    )
    print(f"Wrote {DECOY_MAPPING_PATH}")
    built = sum(1 for entry in summary if not entry.get("skipped"))
    skipped = len(summary) - built
    print(f"Built variants for {built} tasks ({skipped} skipped)")


if __name__ == "__main__":
    main()
