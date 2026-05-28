from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1

WARNING_LOCAL_PARQUET_MISSING = "local_parquet_missing"
WARNING_LOCAL_DB_MISSING = "local_db_missing"
WARNING_PARQUET_PATH_MISMATCH = "parquet_path_mismatch"
LOCAL_PARQUET_MISSING = WARNING_LOCAL_PARQUET_MISSING
LOCAL_DB_MISSING = WARNING_LOCAL_DB_MISSING
PARQUET_PATH_MISMATCH = WARNING_PARQUET_PATH_MISMATCH

ERROR_DATASET_NOT_FOUND = "dataset_not_found"
ERROR_BACKEND_INCOMPATIBLE = "backend_incompatible"
ERROR_INVALID_BACKEND = "invalid_backend"
ERROR_INVALID_OPTION = "invalid_option"
ERROR_PROJECT_ID_REQUIRED = "project_id_required"
ERROR_DATASET_INCOMPATIBLE = "dataset_incompatible"
DATASET_NOT_FOUND = ERROR_DATASET_NOT_FOUND
BACKEND_INCOMPATIBLE = ERROR_BACKEND_INCOMPATIBLE
INVALID_BACKEND = ERROR_INVALID_BACKEND
INVALID_OPTION = ERROR_INVALID_OPTION
PROJECT_ID_REQUIRED = ERROR_PROJECT_ID_REQUIRED
DATASET_INCOMPATIBLE = ERROR_DATASET_INCOMPATIBLE


@dataclass(frozen=True)
class CommandResult:
    command: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    version: int = SCHEMA_VERSION
    ok: bool = True

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "ok": self.ok,
            "command": self.command,
            **self.data,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class CommandError:
    command: str
    code: str
    message: str
    hint: str | None = None
    version: int = SCHEMA_VERSION
    ok: bool = False

    def to_json_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.hint:
            error["hint"] = self.hint

        return {
            "version": self.version,
            "ok": self.ok,
            "command": self.command,
            "error": error,
        }
