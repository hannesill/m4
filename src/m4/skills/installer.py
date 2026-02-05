"""Install M4 skills to AI coding tool directories."""

import shutil
from dataclasses import dataclass
from pathlib import Path

from m4.config import logger

VALID_TIERS = {"validated", "expert", "community"}
VALID_CATEGORIES = {"clinical", "system"}


@dataclass
class AITool:
    """Configuration for an AI coding tool."""

    name: str
    display_name: str
    skills_dir: str  # e.g., ".claude/skills"


@dataclass
class SkillInfo:
    """Metadata for a bundled skill parsed from SKILL.md frontmatter."""

    name: str
    description: str
    tier: str  # validated | expert | community
    category: str  # clinical | system
    path: Path


# Supported AI coding tools that use the .TOOL_NAME/skills/ convention
AI_TOOLS: dict[str, AITool] = {
    "claude": AITool("claude", "Claude Code", ".claude/skills"),
    "cursor": AITool("cursor", "Cursor", ".cursor/skills"),
    "cline": AITool("cline", "Cline", ".cline/skills"),
    "codex": AITool("codex", "Codex CLI", ".codex/skills"),
    "gemini": AITool("gemini", "Gemini CLI", ".gemini/skills"),
    "copilot": AITool("copilot", "GitHub Copilot", ".copilot/skills"),
}


def get_skills_source() -> Path:
    """Get path to bundled skills in the package.

    Returns:
        Path to the skills directory within the installed package.
    """
    # Get the directory where this module is located (skills/)
    return Path(__file__).parent


def get_available_tools() -> list[AITool]:
    """Get list of all supported AI tools.

    Returns:
        List of AITool configurations.
    """
    return list(AI_TOOLS.values())


def _parse_skill_metadata(skill_dir: Path) -> SkillInfo | None:
    """Parse YAML frontmatter from a skill's SKILL.md file.

    Expects a simple ``---`` delimited block with ``key: value`` lines
    for ``name``, ``description``, ``tier``, and ``category``.

    Args:
        skill_dir: Directory containing SKILL.md.

    Returns:
        SkillInfo if parsing succeeds, None otherwise.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    text = skill_md.read_text(encoding="utf-8")

    # Frontmatter is between the first two "---" lines
    if not text.startswith("---"):
        logger.debug(f"No frontmatter in {skill_md}")
        return None

    end = text.find("---", 3)
    if end == -1:
        logger.debug(f"Unclosed frontmatter in {skill_md}")
        return None

    frontmatter = text[3:end].strip()
    fields: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    required = {"name", "description", "tier", "category"}
    missing = required - fields.keys()
    if missing:
        logger.debug(f"Missing frontmatter fields {missing} in {skill_md}")
        return None

    return SkillInfo(
        name=fields["name"],
        description=fields["description"],
        tier=fields["tier"],
        category=fields["category"],
        path=skill_dir,
    )


def get_available_skills(
    tier: list[str] | None = None,
    category: list[str] | None = None,
    names: list[str] | None = None,
) -> list[SkillInfo]:
    """List all bundled skills, optionally filtered.

    Filters combine with AND logic: ``tier=["validated"]`` and
    ``category=["clinical"]`` returns only validated clinical skills.

    Args:
        tier: Keep skills whose tier is in this list.
        category: Keep skills whose category is in this list.
        names: Keep skills whose name is in this list.

    Returns:
        Sorted list of matching SkillInfo objects.
    """
    source = get_skills_source()
    all_skills: list[SkillInfo] = []

    for skill_dir in _discover_skills(source):
        info = _parse_skill_metadata(skill_dir)
        if info is not None:
            all_skills.append(info)

    # Apply filters (AND logic)
    if names is not None:
        name_set = {n.lower() for n in names}
        all_skills = [s for s in all_skills if s.name.lower() in name_set]
    if tier is not None:
        tier_set = {t.lower() for t in tier}
        all_skills = [s for s in all_skills if s.tier.lower() in tier_set]
    if category is not None:
        cat_set = {c.lower() for c in category}
        all_skills = [s for s in all_skills if s.category.lower() in cat_set]

    return sorted(all_skills, key=lambda s: s.name)


def install_skills(
    tools: list[str] | None = None,
    target_dir: Path | None = None,
    project_root: Path | None = None,
    skills: list[str] | None = None,
    tier: list[str] | None = None,
    category: list[str] | None = None,
) -> dict[str, list[Path]]:
    """Install M4 skills to AI coding tool directories.

    Copies skills from the package to each tool's skills directory.
    For example, with tools=["claude", "cursor"]:
    - .claude/skills/m4-api/SKILL.md
    - .cursor/skills/m4-api/SKILL.md

    When filters (skills, tier, category) are provided, only matching
    skills are installed. Existing non-matching skills are left untouched
    (additive install). Filters combine with AND logic.

    Args:
        tools: List of tool names to install for. If None, installs to claude only
               (backwards compatible). Use ["claude", "cursor", ...] for multiple.
        target_dir: Override target directory (ignores tools parameter).
                    For backwards compatibility with direct directory specification.
        project_root: Project root directory. Defaults to current working directory.
        skills: Filter by skill name (install only these skills).
        tier: Filter by tier (validated, expert, community).
        category: Filter by category (clinical, system).

    Returns:
        Dict mapping tool names to lists of installed skill paths.
        If target_dir was specified directly, key is "custom".

    Raises:
        FileNotFoundError: If bundled skills directory doesn't exist.
        PermissionError: If unable to write to target directory.
        ValueError: If an unknown tool name is provided.
    """
    if project_root is None:
        project_root = Path.cwd()

    source = get_skills_source()

    if not source.exists():
        raise FileNotFoundError(
            f"Skills source directory not found: {source}. "
            "This may indicate a packaging issue."
        )

    # Resolve which skills to install
    has_filters = skills is not None or tier is not None or category is not None
    if has_filters:
        selected = get_available_skills(tier=tier, category=category, names=skills)
    else:
        selected = get_available_skills()

    # Handle backwards compatibility: direct target_dir specification
    if target_dir is not None:
        installed = _install_skills_to_dir(selected, target_dir)
        return {"custom": installed}

    # Default to claude only for backwards compatibility
    if tools is None:
        tools = ["claude"]

    # Validate tool names
    unknown_tools = set(tools) - set(AI_TOOLS.keys())
    if unknown_tools:
        raise ValueError(
            f"Unknown AI tools: {unknown_tools}. "
            f"Supported tools: {list(AI_TOOLS.keys())}"
        )

    results: dict[str, list[Path]] = {}

    for tool_name in tools:
        tool = AI_TOOLS[tool_name]
        target = project_root / tool.skills_dir
        installed = _install_skills_to_dir(selected, target)
        results[tool_name] = installed

    return results


def _discover_skills(source: Path) -> list[Path]:
    """Find all skill directories recursively under source.

    Skills are identified by the presence of a SKILL.md file. The source
    directory is organized into category subdirectories (e.g., clinical/,
    system/) but skills are discovered at any depth.

    Args:
        source: Root directory to search for skills.

    Returns:
        Sorted list of skill directory paths.
    """
    return sorted(p.parent for p in source.rglob("SKILL.md"))


def _install_skills_to_dir(skills: list[SkillInfo], target_dir: Path) -> list[Path]:
    """Install selected skills into a target directory.

    Installs skills flat into the target directory regardless of their
    source category subdirectory structure.

    Args:
        skills: List of SkillInfo objects to install.
        target_dir: Target directory to install skills into.

    Returns:
        List of paths where skills were installed.
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    installed = []

    for skill in skills:
        # Flatten: use only the skill directory name, not the full subpath
        target_skill_dir = target_dir / skill.path.name

        # Remove existing installation of this skill
        if target_skill_dir.exists():
            logger.debug(f"Removing existing skill at {target_skill_dir}")
            shutil.rmtree(target_skill_dir)

        logger.debug(f"Copying skill from {skill.path} to {target_skill_dir}")
        shutil.copytree(skill.path, target_skill_dir)
        installed.append(target_skill_dir)

    return installed


def get_installed_skills(
    project_root: Path | None = None,
    tool: str = "claude",
) -> list[str]:
    """List installed M4 skills for a specific AI tool.

    Args:
        project_root: Project root directory. Defaults to current working directory.
        tool: AI tool to check. Defaults to "claude".

    Returns:
        List of skill names found in the tool's skills directory.
    """
    if project_root is None:
        project_root = Path.cwd()

    if tool not in AI_TOOLS:
        raise ValueError(f"Unknown AI tool: {tool}. Supported: {list(AI_TOOLS.keys())}")

    skills_dir = project_root / AI_TOOLS[tool].skills_dir

    if not skills_dir.exists():
        return []

    return [
        d.name for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()
    ]


def get_all_installed_skills(
    project_root: Path | None = None,
) -> dict[str, list[str]]:
    """List installed M4 skills across all AI tools.

    Args:
        project_root: Project root directory. Defaults to current working directory.

    Returns:
        Dict mapping tool names to lists of installed skill names.
        Only includes tools that have skills installed.
    """
    if project_root is None:
        project_root = Path.cwd()

    results = {}

    for tool_name in AI_TOOLS:
        skills = get_installed_skills(project_root, tool_name)
        if skills:
            results[tool_name] = skills

    return results
