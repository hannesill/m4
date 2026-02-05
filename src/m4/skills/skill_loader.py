"""Skill loading and management for M4 MCP Server.

This module provides functionality to:
1. Discover skill directories with SKILL.md files
2. Parse skill metadata and content
3. Register skills as MCP tools
"""

import os
import re
from pathlib import Path


class SkillMetadata:
    """Metadata extracted from skill YAML front matter."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description


class Skill:
    """Represents a loaded skill with metadata and content."""

    def __init__(self, metadata: SkillMetadata, content: str, file_path: Path):
        self.metadata = metadata
        self.content = content
        self.file_path = file_path

    def get_full_documentation(self) -> str:
        """Get the complete skill documentation."""
        return f"# {self.metadata.name}\n\n{self.content}"


class SkillLoader:
    """Loads and manages skills from the filesystem."""

    def __init__(self, skills_path: str | None = None):
        """Initialize skill loader.

        Args:
            skills_path: Path to skills directory. If None, uses M4_SKILLS_PATH env var.
        """
        self.skills_path = skills_path or os.getenv("M4_SKILLS_PATH")
        self.skills: dict[str, Skill] = {}

        if self.skills_path:
            self._load_skills()

    def _load_skills(self) -> None:
        """Discover and load all skills from the skills directory."""
        if not self.skills_path:
            return

        skills_dir = Path(self.skills_path)
        if not skills_dir.exists():
            print(f"Warning: Skills directory not found: {self.skills_path}")
            return

        # Find all SKILL.md files
        skill_files = list(skills_dir.glob("*/SKILL.md"))

        for skill_file in skill_files:
            try:
                skill = self._parse_skill_file(skill_file)
                if skill:
                    self.skills[skill.metadata.name] = skill
                    print(f"✓ Loaded skill: {skill.metadata.name}")
            except Exception as e:
                print(f"✗ Failed to load skill from {skill_file}: {e}")

    def _parse_skill_file(self, file_path: Path) -> Skill | None:
        """Parse a SKILL.md file and extract metadata and content.

        Args:
            file_path: Path to SKILL.md file

        Returns:
            Skill object or None if parsing fails
        """
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # Parse YAML front matter
        metadata = self._parse_yaml_frontmatter(content)
        if not metadata:
            return None

        # Extract content (everything after front matter)
        content_match = re.search(r"^---\n.*?\n---\n\n(.+)", content, re.DOTALL)
        if content_match:
            skill_content = content_match.group(1).strip()
        else:
            skill_content = content

        return Skill(metadata, skill_content, file_path)

    def _parse_yaml_frontmatter(self, content: str) -> SkillMetadata | None:
        """Parse YAML front matter from skill file.

        Args:
            content: Full file content

        Returns:
            SkillMetadata or None if parsing fails
        """
        # Extract YAML front matter between --- delimiters
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return None

        yaml_content = match.group(1)

        # Simple YAML parsing (assumes name: value format)
        name = None
        description = None

        for line in yaml_content.split("\n"):
            line = line.strip()
            if line.startswith("name:"):
                name = line.split("name:", 1)[1].strip()
            elif line.startswith("description:"):
                description = line.split("description:", 1)[1].strip()

        if not name or not description:
            return None

        return SkillMetadata(name, description)

    def get_skill(self, skill_name: str) -> Skill | None:
        """Get a skill by name.

        Args:
            skill_name: Name of the skill

        Returns:
            Skill object or None if not found
        """
        return self.skills.get(skill_name)

    def list_skills(self) -> list[str]:
        """List all available skill names.

        Returns:
            List of skill names
        """
        return list(self.skills.keys())

    def get_all_skills(self) -> dict[str, Skill]:
        """Get all loaded skills.

        Returns:
            Dictionary mapping skill names to Skill objects
        """
        return self.skills


# Global skill loader instance
_skill_loader: SkillLoader | None = None


def init_skills() -> None:
    """Initialize the global skill loader."""
    global _skill_loader
    _skill_loader = SkillLoader()


def get_skill_loader() -> SkillLoader | None:
    """Get the global skill loader instance.

    Returns:
        SkillLoader instance or None if not initialized
    """
    return _skill_loader
