"""M4 skills package for AI coding tools."""

from m4.skills.catalog import (
    CATALOG_SCHEMA_VERSION,
    MANIFEST_FILE_NAME,
    build_catalog,
    materialize_catalog,
    verify_materialized_bundle,
)
from m4.skills.installer import (
    AI_TOOLS,
    AITool,
    SkillInfo,
    get_all_installed_skills,
    get_available_skills,
    get_available_tools,
    get_installed_skills,
    get_skills_source,
    install_skills,
)

__all__ = [
    "AI_TOOLS",
    "CATALOG_SCHEMA_VERSION",
    "MANIFEST_FILE_NAME",
    "AITool",
    "SkillInfo",
    "build_catalog",
    "get_all_installed_skills",
    "get_available_skills",
    "get_available_tools",
    "get_installed_skills",
    "get_skills_source",
    "install_skills",
    "materialize_catalog",
    "verify_materialized_bundle",
]
