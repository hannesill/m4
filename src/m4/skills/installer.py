"""Install M4 Claude Code skills to the project's .claude/skills directory."""

import shutil
from pathlib import Path

from m4.config import logger

# M4 skill names (used for tracking which skills we manage)
M4_SKILLS = ["m4-api"]


def get_skills_source() -> Path:
    """Get path to bundled skills in the package.

    Returns:
        Path to the skills directory within the installed package.
    """
    # Get the directory where this module is located (skills/)
    return Path(__file__).parent


def install_skills(target_dir: Path | None = None) -> list[Path]:
    """Install M4 skills to project's Claude Code skills directory.

    Copies skills from the package to .claude/skills/ in the current
    working directory. Each skill is placed directly as a subdirectory
    (e.g., .claude/skills/m4-api/SKILL.md).

    Args:
        target_dir: Target skills directory. Defaults to ./.claude/skills/

    Returns:
        List of paths where skills were installed.

    Raises:
        FileNotFoundError: If bundled skills directory doesn't exist.
        PermissionError: If unable to write to target directory.
    """
    if target_dir is None:
        target_dir = Path.cwd() / ".claude" / "skills"

    source = get_skills_source()

    if not source.exists():
        raise FileNotFoundError(
            f"Skills source directory not found: {source}. "
            "This may indicate a packaging issue."
        )

    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    installed = []

    # Copy each skill directly to .claude/skills/<skill-name>/
    for skill_dir in source.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            target_skill_dir = target_dir / skill_dir.name

            # Remove existing installation of this skill
            if target_skill_dir.exists():
                logger.debug(f"Removing existing skill at {target_skill_dir}")
                shutil.rmtree(target_skill_dir)

            logger.debug(f"Copying skill from {skill_dir} to {target_skill_dir}")
            shutil.copytree(skill_dir, target_skill_dir)
            installed.append(target_skill_dir)

    return installed


def get_installed_skills(project_root: Path | None = None) -> list[str]:
    """List installed M4 skills in a project.

    Args:
        project_root: Project root directory. Defaults to current working directory.

    Returns:
        List of M4 skill names found in .claude/skills/
    """
    if project_root is None:
        project_root = Path.cwd()

    skills_dir = project_root / ".claude" / "skills"

    if not skills_dir.exists():
        return []

    # Only return skills that are M4 skills
    return [
        d.name
        for d in skills_dir.iterdir()
        if d.is_dir() and d.name in M4_SKILLS and (d / "SKILL.md").exists()
    ]
