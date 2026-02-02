import re
from pathlib import Path


def _skills_dir() -> Path:
    from m4.skills.installer import get_skills_source

    return get_skills_source()


def _skills_on_disk() -> list[str]:
    skills_dir = _skills_dir()
    return sorted(
        d.name
        for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


def _skills_index_path() -> Path:
    return _skills_dir() / "SKILLS_INDEX.md"


def _parse_indexed_skill_names(index_text: str) -> set[str]:
    # Skill links are written like: [sofa-score](sofa-score/SKILL.md)
    names: set[str] = set()
    for m in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", index_text):
        target = m.group(1).strip()
        if target.endswith("/SKILL.md") and "://" not in target:
            names.add(target.split("/", 1)[0])
    return names


def test_skills_index_matches_skills_on_disk():
    disk = _skills_on_disk()
    index_path = _skills_index_path()
    assert index_path.exists(), f"Missing skills index file: {index_path}"
    index_text = index_path.read_text(encoding="utf-8")

    indexed = _parse_indexed_skill_names(index_text)
    assert indexed, "SKILLS_INDEX.md contains no skill links like (skill-name/SKILL.md)"

    missing = sorted(set(disk) - indexed)
    extra = sorted(indexed - set(disk))

    assert len(indexed) == len(disk) and not missing and not extra, (
        f"SKILLS_INDEX.md is out of sync with bundled skills. "
        f"On disk: {len(disk)} skills; in SKILLS_INDEX.md: {len(indexed)} skills. "
        f"Missing from index: {missing}. Extra in index: {extra}. "
        "Please (1) add/remove the corresponding skill rows/links in SKILLS_INDEX.md "
        "and (2) update any 'Skill Statistics' / 'Category Distribution' counts "
        "to match the new set of skills."
    )

