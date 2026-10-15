"""The API skills name only functions and commands that exist.

The vitrine-api, m4-api, and m4-setup skills are what agents read instead of
the source, so a renamed function or CLI command there sends every agent down
a dead end. These tests read the names out of the skills and look them up in
the installed packages.
"""

import re

import typer.main
import vitrine
import vitrine.cli

import m4
import m4.cli
from m4 import M4Client
from m4.skills.installer import get_skills_source


def _skill(name: str) -> str:
    return (get_skills_source() / "system" / name / "SKILL.md").read_text(
        encoding="utf-8"
    )


def _cli_commands(app) -> set[str]:
    return set(typer.main.get_command(app).commands)


def _imported(text: str, module: str) -> set[str]:
    names: set[str] = set()
    for line in re.findall(rf"^from {module} import ([^\n]+)$", text, re.MULTILINE):
        names.update(name.strip() for name in line.split(","))
    return names


def _cli_used(text: str, program: str) -> set[str]:
    # `m4 query ...` in prose and `m4 query ...` at the start of a code line.
    return set(re.findall(rf"(?:^|`){program} ([a-z][a-z-]*)", text, re.MULTILINE))


def test_vitrine_api_skill_names_exist():
    text = _skill("vitrine-api")
    names = _imported(text, "vitrine") | set(
        re.findall(r"\bvitrine\.([a-z_]+)\(", text)
    )
    assert names
    assert sorted(n for n in names if not hasattr(vitrine, n)) == []
    assert sorted(_cli_used(text, "vitrine") - _cli_commands(vitrine.cli.app)) == []


def test_m4_api_skill_names_exist():
    text = _skill("m4-api")
    assert sorted(n for n in _imported(text, "m4") if not hasattr(m4, n)) == []
    methods = set(re.findall(r"\b(?:db|notes)\.([a-z_]+)\(", text))
    assert methods
    assert sorted(n for n in methods if not hasattr(M4Client, n)) == []
    assert sorted(_cli_used(text, "m4") - _cli_commands(m4.cli.app)) == []


def test_m4_setup_skill_commands_exist():
    text = _skill("m4-setup")
    m4_commands = _cli_used(text, "m4")
    assert m4_commands
    assert sorted(m4_commands - _cli_commands(m4.cli.app)) == []
    assert sorted(_cli_used(text, "vitrine") - _cli_commands(vitrine.cli.app)) == []
