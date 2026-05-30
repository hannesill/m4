import json
import logging
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from m4.core.datasets import DatasetRegistry
from m4.core.exceptions import DatasetError

APP_NAME = "m4"

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(APP_NAME)


# -------------------------------------------------------------------
# Runtime context and data directory resolution
# -------------------------------------------------------------------
@dataclass(frozen=True)
class M4Context:
    """Resolved runtime context for agent and human interfaces."""

    home: Path
    data_dir: Path
    dataset: str | None
    backend: str
    study_id: str | None
    session_id: str | None
    actor: str | None
    project_id: str | None
    telemetry_dir: Path
    path_disclosure: bool = False

    def public_context(self) -> dict[str, str | None]:
        """Return non-path attribution fields suitable for JSON envelopes."""
        return {
            "dataset": self.dataset,
            "backend": self.backend,
            "study_id": self.study_id,
            "session_id": self.session_id,
            "actor": self.actor,
            "project_id": self.project_id,
        }


def _find_project_root_from_cwd() -> Path:
    """
    Search upwards from CWD for a valid 'm4_data' directory.
    If found (and looks like an m4 data dir), return its parent.
    Otherwise return CWD.
    """
    cwd = Path.cwd()
    for path in [cwd, *cwd.parents]:
        data_dir = path / "m4_data"
        if data_dir.exists() and data_dir.is_dir():
            # Check for characteristic m4 data artifacts to avoid false positives
            if (
                (data_dir / "config.json").exists()
                or (data_dir / "databases").exists()
                or (data_dir / "parquet").exists()
                or (data_dir / "datasets").exists()
                or (data_dir / "raw_files").exists()
            ):
                return path
    return cwd


def _get_legacy_project_root() -> Path:
    """
    Determine the legacy project root used when no explicit data/home path is set.

    - If cloned repo: use repository root (two levels up from this file)
    - If pip installed: Search upwards from CWD for existing 'm4_data' directory,
      or use CWD.
    """
    package_root = Path(__file__).resolve().parents[2]

    # Check if we're in a cloned repository (has pyproject.toml at root)
    if (package_root / "pyproject.toml").exists():
        return package_root

    # Pip installed: Search for project root
    return _find_project_root_from_cwd()


def _looks_like_legacy_data_parent(path: Path) -> bool:
    """Return True when M4_DATA_DIR appears to be an old parent/root hint."""
    direct_markers = (
        "config.json",
        "databases",
        "parquet",
        "datasets",
        "raw_files",
    )
    if any((path / marker).exists() for marker in direct_markers):
        return False
    nested = path / "m4_data"
    return nested.exists() and any(
        (nested / marker).exists() for marker in direct_markers
    )


def _get_project_root() -> Path:
    """Compatibility root for callers that still reason in project-root terms."""
    env_data_dir = os.getenv("M4_DATA_DIR")
    if env_data_dir:
        data_path = Path(env_data_dir).expanduser().resolve()
        if _looks_like_legacy_data_parent(data_path):
            return data_path
        return data_path.parent

    env_home = os.getenv("M4_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    return _get_legacy_project_root()


def _get_project_data_dir() -> Path:
    """Resolve the exact M4 data directory.

    M4_DATA_DIR now means the data directory itself.  For a compatibility
    window, values that clearly point at a parent containing m4_data are mapped
    to that nested directory with a deprecation warning.
    """
    env_data_dir = os.getenv("M4_DATA_DIR")
    if env_data_dir:
        data_path = Path(env_data_dir).expanduser().resolve()
        if _looks_like_legacy_data_parent(data_path):
            warnings.warn(
                "M4_DATA_DIR should point directly to the M4 data directory. "
                "Using the nested m4_data directory for compatibility.",
                DeprecationWarning,
                stacklevel=2,
            )
            return data_path / "m4_data"
        return data_path

    return _get_project_root() / "m4_data"


_PROJECT_ROOT = _get_project_root()
_PROJECT_DATA_DIR = _get_project_data_dir()
_M4_HOME = (
    Path(os.environ["M4_HOME"]).expanduser().resolve()
    if os.getenv("M4_HOME")
    else _PROJECT_DATA_DIR
)

_DEFAULT_DATABASES_DIR = _PROJECT_DATA_DIR / "databases"
_DEFAULT_PARQUET_DIR = _PROJECT_DATA_DIR / "parquet"
_RUNTIME_CONFIG_PATH = _M4_HOME / "config.json"
_CUSTOM_DATASETS_DIR = _PROJECT_DATA_DIR / "datasets"


# --------------------------------------------------
# Helper functions
# --------------------------------------------------


def _ensure_custom_datasets_loaded():
    """Ensure custom datasets are loaded from the custom datasets directory."""
    DatasetRegistry.load_custom_datasets(_CUSTOM_DATASETS_DIR)


def resolve_runtime_context(
    *,
    dataset: str | None = None,
    backend: str | None = None,
    path_disclosure: bool | None = None,
) -> M4Context:
    """Resolve runtime context with CLI flag > env > config/default precedence."""
    resolved_dataset = dataset
    if resolved_dataset is None:
        try:
            resolved_dataset = get_active_dataset()
        except DatasetError:
            resolved_dataset = None

    resolved_backend = (backend or get_active_backend()).lower()
    env_home = os.getenv("M4_HOME")
    home = Path(env_home).expanduser().resolve() if env_home else _M4_HOME

    if path_disclosure is None:
        path_disclosure = os.getenv("M4_PATH_DISCLOSURE", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
            "paths",
        }

    return M4Context(
        home=home,
        data_dir=_PROJECT_DATA_DIR,
        dataset=resolved_dataset,
        backend=resolved_backend,
        study_id=os.getenv("M4_STUDY_ID"),
        session_id=os.getenv("M4_SESSION_ID"),
        actor=os.getenv("M4_ACTOR"),
        project_id=get_bigquery_project_id(),
        telemetry_dir=get_telemetry_dir(),
        path_disclosure=bool(path_disclosure),
    )


def get_default_database_path(dataset_name: str) -> Path | None:
    """
    Return the default local DuckDB path for a given dataset,
    under <project_root>/m4_data/databases/.
    """
    _ensure_custom_datasets_loaded()
    ds = DatasetRegistry.get(dataset_name.lower())
    if not ds:
        logger.warning(
            f"Unknown dataset, cannot determine default DB path: {dataset_name}"
        )
        return None

    _DEFAULT_DATABASES_DIR.mkdir(parents=True, exist_ok=True)
    if not ds.default_duckdb_filename:
        logger.warning(f"Missing default DuckDB filename for dataset: {dataset_name}")
        return None
    return _DEFAULT_DATABASES_DIR / ds.default_duckdb_filename


def get_dataset_parquet_root(dataset_name: str) -> Path | None:
    """
    Return the Parquet root for a dataset under
    <project_root>/m4_data/parquet/<dataset_name>/.
    """
    _ensure_custom_datasets_loaded()
    ds = DatasetRegistry.get(dataset_name.lower())
    if not ds:
        logger.warning(
            f"Unknown dataset, cannot determine Parquet root: {dataset_name}"
        )
        return None
    path = _DEFAULT_PARQUET_DIR / dataset_name.lower()
    path.mkdir(parents=True, exist_ok=True)
    return path


# -----------------------------
# Runtime config (active dataset)
# -----------------------------
def _ensure_data_dirs():
    _DEFAULT_DATABASES_DIR.mkdir(parents=True, exist_ok=True)
    _DEFAULT_PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    _PROJECT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_DATASETS_DIR.mkdir(parents=True, exist_ok=True)


def _get_default_runtime_config() -> dict:
    # We initialize with empty overrides.
    # Paths are derived dynamically from registry unless overridden here.
    return {
        "active_dataset": None,
        "duckdb_paths": {},  # Map dataset_name -> path
        "parquet_roots": {},  # Map dataset_name -> path
        "bigquery_project_id": None,
    }


def load_runtime_config() -> dict:
    """Load runtime configuration from <project_root>/m4_data/config.json or use default"""
    _ensure_data_dirs()
    if _RUNTIME_CONFIG_PATH.exists():
        try:
            return json.loads(_RUNTIME_CONFIG_PATH.read_text())
        except Exception:
            logger.warning("Could not parse runtime config; using defaults")
    # defaults
    return _get_default_runtime_config()


def save_runtime_config(cfg: dict) -> None:
    _ensure_data_dirs()
    _RUNTIME_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _has_parquet_files(path: Path | None) -> bool:
    return bool(path and path.exists() and any(path.rglob("*.parquet")))


def _has_raw_files(path: Path | None) -> bool:
    return bool(path and path.exists() and any(path.rglob("*.csv.gz")))


def detect_available_local_datasets() -> dict[str, dict[str, Any]]:
    """Return presence flags for all registered datasets."""
    _ensure_custom_datasets_loaded()
    cfg = load_runtime_config()

    results = {}

    # Check all registered datasets
    for ds in DatasetRegistry.list_all():
        name = ds.name

        # Determine paths (check config overrides first)
        parquet_root_str = cfg.get("parquet_roots", {}).get(name)
        parquet_root = (
            Path(parquet_root_str)
            if parquet_root_str
            else get_dataset_parquet_root(name)
        )

        db_path_str = cfg.get("duckdb_paths", {}).get(name)
        db_path = Path(db_path_str) if db_path_str else get_default_database_path(name)
        raw_root = _PROJECT_DATA_DIR / "raw_files" / name

        results[name] = {
            "raw_present": _has_raw_files(raw_root),
            "parquet_present": _has_parquet_files(parquet_root),
            "db_present": bool(db_path and db_path.exists()),
            "raw_root": str(raw_root),
            "parquet_root": str(parquet_root) if parquet_root else "",
            "db_path": str(db_path) if db_path else "",
        }

    return results


def get_active_dataset() -> str:
    """Get the active dataset name.

    Raises:
        DatasetError: If no dataset is configured and none can be auto-detected.
    """
    # Ensure custom datasets are loaded so they can be found in the registry
    _ensure_custom_datasets_loaded()

    # Priority 1: Environment variable
    env_dataset = os.getenv("M4_DATASET")
    if env_dataset:
        return env_dataset

    # Priority 2: Config file
    cfg = load_runtime_config()
    active = cfg.get("active_dataset")

    # Else, raise an error that no active dataset is configured.
    if not active:
        raise DatasetError(
            "No active dataset configured. Please rerun 'm4 init' to configure a dataset."
        )

    return active


def set_active_dataset(choice: str) -> None:
    """Set the active dataset.

    Args:
        choice: Dataset name to set as active

    Raises:
        ValueError: If the dataset is not registered
    """
    _ensure_custom_datasets_loaded()
    valid_names = {ds.name for ds in DatasetRegistry.list_all()}

    if choice not in valid_names:
        raise ValueError(f"active_dataset must be a registered dataset. Got: {choice}")

    cfg = load_runtime_config()
    cfg["active_dataset"] = choice
    save_runtime_config(cfg)


VALID_BACKENDS = {"duckdb", "bigquery"}


def get_active_backend() -> str:
    """Get the active backend.

    Priority:
    1. M4_BACKEND environment variable
    2. Config file setting
    3. Default to 'duckdb'

    Returns:
        Backend name ('duckdb' or 'bigquery')
    """
    # Priority 1: Environment variable
    env_backend = os.getenv("M4_BACKEND")
    if env_backend:
        return env_backend.lower()

    # Priority 2: Config file
    cfg = load_runtime_config()
    backend = cfg.get("backend")
    if backend:
        return backend.lower()

    # Default
    return "duckdb"


def set_active_backend(choice: str) -> None:
    """Set the active backend.

    Args:
        choice: Backend name ('duckdb' or 'bigquery')

    Raises:
        ValueError: If the backend is not valid
    """
    choice = choice.lower()
    if choice not in VALID_BACKENDS:
        raise ValueError(f"backend must be one of {VALID_BACKENDS}. Got: {choice}")

    cfg = load_runtime_config()
    cfg["backend"] = choice
    save_runtime_config(cfg)


def get_bigquery_project_id() -> str | None:
    """Get the BigQuery billing project ID.

    Priority:
    1. M4_PROJECT_ID environment variable
    2. Config file setting
    3. None (let BigQuery client use ambient credentials)

    Returns:
        Project ID string, or None if not configured
    """
    # Priority 1: Environment variable
    env_project_id = os.getenv("M4_PROJECT_ID")
    if env_project_id:
        return env_project_id

    # Priority 2: Config file
    cfg = load_runtime_config()
    project_id = cfg.get("bigquery_project_id")
    if project_id:
        return project_id

    return None


def set_bigquery_project_id(project_id: str | None) -> None:
    """Set or clear the BigQuery billing project ID.

    Args:
        project_id: Project ID string, or None to clear
    """
    cfg = load_runtime_config()
    cfg["bigquery_project_id"] = project_id
    save_runtime_config(cfg)


def get_telemetry_dir() -> Path:
    """Return the telemetry directory, creating it if needed."""
    env_telemetry_dir = os.getenv("M4_TELEMETRY_DIR")
    path = (
        Path(env_telemetry_dir).expanduser().resolve()
        if env_telemetry_dir
        else _M4_HOME / "telemetry"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_duckdb_path_for(choice: str) -> Path | None:
    return get_default_database_path(choice)


def get_parquet_root_for(choice: str) -> Path | None:
    return get_dataset_parquet_root(choice)
