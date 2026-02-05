import re
from pathlib import Path


def _skills_dir() -> Path:
    from m4.skills.installer import get_skills_source

    return get_skills_source()


def _skills_on_disk() -> list[str]:
    skills_dir = _skills_dir()
    return sorted(p.parent.name for p in skills_dir.rglob("SKILL.md"))


def _skills_index_path() -> Path:
    return _skills_dir() / "SKILLS_INDEX.md"


def _parse_indexed_skill_names(index_text: str) -> set[str]:
    # Skill links like: [sofa-score](clinical/sofa-score/SKILL.md)
    names: set[str] = set()
    for m in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", index_text):
        target = m.group(1).strip()
        if target.endswith("/SKILL.md") and "://" not in target:
            # Extract skill name: the directory immediately before SKILL.md
            parts = target.removesuffix("/SKILL.md").split("/")
            names.add(parts[-1])
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


# ── Metadata parsing tests ──────────────────────────────────────────


def test_parse_skill_metadata_returns_correct_fields():
    from m4.skills.installer import _parse_skill_metadata

    skills_dir = _skills_dir()
    sofa_dir = skills_dir / "clinical" / "sofa-score"
    assert sofa_dir.exists(), f"Expected skill dir not found: {sofa_dir}"

    info = _parse_skill_metadata(sofa_dir)
    assert info is not None
    assert info.name == "sofa-score"
    assert info.tier == "validated"
    assert info.category == "clinical"
    assert info.path == sofa_dir
    assert len(info.description) > 0


def test_parse_skill_metadata_returns_none_for_missing_dir(tmp_path: Path):
    from m4.skills.installer import _parse_skill_metadata

    result = _parse_skill_metadata(tmp_path / "nonexistent")
    assert result is None


def test_parse_skill_metadata_returns_none_for_no_frontmatter(tmp_path: Path):
    from m4.skills.installer import _parse_skill_metadata

    skill_dir = tmp_path / "bad-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# No frontmatter here\n")
    assert _parse_skill_metadata(skill_dir) is None


# ── get_available_skills tests ───────────────────────────────────────


def test_get_available_skills_returns_all():
    from m4.skills.installer import get_available_skills

    all_skills = get_available_skills()
    disk = _skills_on_disk()
    assert len(all_skills) == len(disk)
    assert {s.name for s in all_skills} == set(disk)


def test_get_available_skills_filter_by_category():
    from m4.skills.installer import get_available_skills

    clinical = get_available_skills(category=["clinical"])
    assert len(clinical) > 0
    assert all(s.category == "clinical" for s in clinical)

    system = get_available_skills(category=["system"])
    assert len(system) > 0
    assert all(s.category == "system" for s in system)

    # Together they should cover all skills
    all_skills = get_available_skills()
    assert len(clinical) + len(system) == len(all_skills)


def test_get_available_skills_filter_by_tier():
    from m4.skills.installer import get_available_skills

    validated = get_available_skills(tier=["validated"])
    assert len(validated) > 0
    assert all(s.tier == "validated" for s in validated)


def test_get_available_skills_filter_by_name():
    from m4.skills.installer import get_available_skills

    result = get_available_skills(names=["sofa-score"])
    assert len(result) == 1
    assert result[0].name == "sofa-score"


def test_get_available_skills_combined_filters():
    from m4.skills.installer import get_available_skills

    result = get_available_skills(tier=["validated"], category=["clinical"])
    assert len(result) > 0
    assert all(s.tier == "validated" and s.category == "clinical" for s in result)

    # Should be a subset of either filter alone
    by_tier = get_available_skills(tier=["validated"])
    by_cat = get_available_skills(category=["clinical"])
    assert len(result) <= len(by_tier)
    assert len(result) <= len(by_cat)


def test_get_available_skills_invalid_name_returns_empty():
    from m4.skills.installer import get_available_skills

    result = get_available_skills(names=["nonexistent-skill-xyz"])
    assert result == []


def test_get_available_skills_results_are_sorted():
    from m4.skills.installer import get_available_skills

    all_skills = get_available_skills()
    names = [s.name for s in all_skills]
    assert names == sorted(names)
