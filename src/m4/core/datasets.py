"""Dataset definitions with modality-based filtering.

This module provides:
- Modality enum: Data types available in a dataset (TABULAR, NOTES, etc.)
- DatasetDefinition: Dataset metadata with modalities
- DatasetRegistry: Registry for managing dataset definitions
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Maximum file size for custom dataset JSON files (1MB)
# Prevents memory exhaustion from malicious/oversized files
MAX_DATASET_FILE_SIZE = 1024 * 1024


class Modality(Enum):
    """Data modalities available in a dataset.

    Modalities describe what kinds of data a dataset contains. Tools declare
    which modalities they require, and only datasets with those modalities
    will have the tool available.

    This is intentionally high-level. Fine-grained data discovery (which tables
    exist, what columns they have) is handled by schema introspection tools
    and the LLM's ability to write adaptive SQL.
    """

    TABULAR = auto()  # Structured tables (labs, demographics, vitals, etc.)
    NOTES = auto()  # Clinical notes and discharge summaries


@dataclass
class DatasetDefinition:
    """Dataset definition with modality declarations.

    Attributes:
        name: Unique identifier for the dataset
        description: Human-readable description
        version: Dataset version string
        file_listing_url: URL for downloading dataset files
        subdirectories_to_scan: Directories to scan for data files
        default_duckdb_filename: Default filename for local DuckDB database
        primary_verification_table: Table to check for dataset verification
        bigquery_project_id: Google Cloud project ID for BigQuery access
        bigquery_dataset_ids: BigQuery dataset IDs containing the tables
        requires_authentication: Whether dataset requires auth (e.g., credentialed access)
        modalities: Immutable set of data modalities (TABULAR, NOTES, etc.)
        related_datasets: Cross-references to related datasets with linkage info
    """

    name: str
    description: str = ""
    version: str = "1.0"
    file_listing_url: str | None = None
    subdirectories_to_scan: list[str] = field(default_factory=list)
    default_duckdb_filename: str | None = None
    primary_verification_table: str | None = None

    # BigQuery Configuration
    bigquery_project_id: str | None = "physionet-data"
    bigquery_dataset_ids: list[str] = field(default_factory=list)

    # Authentication
    requires_authentication: bool = False

    # Modality declarations (immutable)
    modalities: frozenset[Modality] = field(default_factory=frozenset)

    # Related datasets (for cross-referencing, e.g., notes linked via subject_id)
    # Format: {"dataset-name": "Description of how to link"}
    related_datasets: dict[str, str] = field(default_factory=dict)

    # Filesystem directory -> canonical schema name
    # e.g. {"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"}
    # Root-level files use empty string key: {"": "eicu_crd"}
    schema_mapping: dict[str, str] = field(default_factory=dict)

    # Canonical schema -> BigQuery dataset ID
    # e.g. {"mimiciv_hosp": "mimiciv_3_1_hosp"}
    bigquery_schema_mapping: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize computed fields."""
        if not self.default_duckdb_filename:
            self.default_duckdb_filename = f"{self.name.replace('-', '_')}.duckdb"


class DatasetRegistry:
    """Registry for managing dataset definitions.

    This class maintains a global registry of available datasets with
    enhanced capability metadata.
    """

    _registry: ClassVar[dict[str, DatasetDefinition]] = {}

    @classmethod
    def register(cls, dataset: DatasetDefinition):
        """Register a dataset in the registry.

        Args:
            dataset: DatasetDefinition to register
        """
        cls._registry[dataset.name.lower()] = dataset

    @classmethod
    def get(cls, name: str) -> DatasetDefinition | None:
        """Get a dataset by name.

        Args:
            name: Dataset name (case-insensitive)

        Returns:
            DatasetDefinition if found, None otherwise
        """
        return cls._registry.get(name.lower())

    @classmethod
    def list_all(cls) -> list[DatasetDefinition]:
        """Get all registered datasets.

        Returns:
            List of all DatasetDefinition objects
        """
        return list(cls._registry.values())

    @classmethod
    def get_active(cls) -> DatasetDefinition:
        """Get the currently active dataset definition.

        This method retrieves the active dataset from config and returns
        its definition. Raises an error if no active dataset is configured.

        Returns:
            DatasetDefinition for the active dataset

        Raises:
            ValueError: If no active dataset is configured or dataset not found
        """
        # Import here to avoid circular dependency
        from m4.config import get_active_dataset

        active_ds_name = get_active_dataset()
        if not active_ds_name:
            raise ValueError(
                "No active dataset configured. "
                "Use `set_dataset('dataset-name')` to select a dataset."
            )

        ds_def = cls.get(active_ds_name)
        if not ds_def:
            raise ValueError(
                f"Active dataset '{active_ds_name}' not found in registry. "
                f"Available datasets: {', '.join(d.name for d in cls.list_all())}"
            )

        return ds_def

    @classmethod
    def reset(cls):
        """Clear registry and re-register built-in datasets."""
        cls._registry.clear()
        cls._register_builtins()

    @classmethod
    def load_custom_datasets(cls, custom_dir: Path) -> None:
        """Load custom dataset definitions from JSON files.

        JSON files can specify modalities as string arrays:
            "modalities": ["TABULAR", "NOTES"]

        If not specified, defaults to TABULAR modality.

        Args:
            custom_dir: Directory containing custom dataset JSON files
        """
        if not custom_dir.exists():
            logger.debug(f"Custom datasets directory does not exist: {custom_dir}")
            return

        for f in custom_dir.glob("*.json"):
            try:
                # Check file size to prevent DoS via large files
                if f.stat().st_size > MAX_DATASET_FILE_SIZE:
                    logger.warning(
                        f"Dataset file too large (>{MAX_DATASET_FILE_SIZE} bytes), "
                        f"skipping: {f}"
                    )
                    continue

                data = json.loads(f.read_text())

                # Convert string arrays to enum frozensets
                if "modalities" in data:
                    data["modalities"] = frozenset(
                        Modality[m] for m in data["modalities"]
                    )
                else:
                    # Default: tabular data
                    data["modalities"] = frozenset({Modality.TABULAR})

                # Default empty dicts for schema mapping fields
                data.setdefault("schema_mapping", {})
                data.setdefault("bigquery_schema_mapping", {})

                ds = DatasetDefinition(**data)
                cls.register(ds)
                logger.debug(f"Loaded custom dataset: {ds.name}")
            except KeyError as e:
                logger.warning(
                    f"Failed to load custom dataset from {f}: "
                    f"Invalid modality name: {e}"
                )
            except Exception as e:
                logger.warning(f"Failed to load custom dataset from {f}: {e}")

    @classmethod
    def _register_builtins(cls):
        """Register built-in datasets."""
        mimic_iv_demo = DatasetDefinition(
            name="mimic-iv-demo",
            description="MIMIC-IV Clinical Database Demo",
            file_listing_url="https://physionet.org/files/mimic-iv-demo/2.2/",
            subdirectories_to_scan=["hosp", "icu"],
            primary_verification_table="mimiciv_hosp.admissions",
            bigquery_project_id=None,
            bigquery_dataset_ids=[],
            modalities=frozenset({Modality.TABULAR}),
            schema_mapping={"hosp": "mimiciv_hosp", "icu": "mimiciv_icu"},
        )

        mimic_iv = DatasetDefinition(
            name="mimic-iv",
            description="MIMIC-IV Clinical Database",
            file_listing_url="https://physionet.org/files/mimiciv/3.1/",
            subdirectories_to_scan=["hosp", "icu"],
            primary_verification_table="mimiciv_hosp.admissions",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["mimiciv_3_1_hosp", "mimiciv_3_1_icu"],
            requires_authentication=True,
            modalities=frozenset({Modality.TABULAR}),
            related_datasets={
                "mimic-iv-note": (
                    "Clinical notes (discharge summaries, radiology reports). "
                    "Link via subject_id."
                ),
            },
            schema_mapping={
                "hosp": "mimiciv_hosp",
                "icu": "mimiciv_icu",
                "derived": "mimiciv_derived",
            },
            bigquery_schema_mapping={
                "mimiciv_hosp": "mimiciv_3_1_hosp",
                "mimiciv_icu": "mimiciv_3_1_icu",
                "mimiciv_derived": "mimiciv_derived",
            },
        )

        mimic_iv_note = DatasetDefinition(
            name="mimic-iv-note",
            description="MIMIC-IV Clinical Notes (discharge summaries, radiology reports)",
            file_listing_url="https://physionet.org/files/mimic-iv-note/2.2/",
            subdirectories_to_scan=["note"],
            primary_verification_table="mimiciv_note.discharge",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["mimiciv_note"],
            requires_authentication=True,
            modalities=frozenset({Modality.NOTES}),
            related_datasets={
                "mimic-iv": (
                    "Structured clinical data (labs, vitals, admissions). "
                    "Link via subject_id."
                ),
            },
            schema_mapping={"note": "mimiciv_note"},
            bigquery_schema_mapping={"mimiciv_note": "mimiciv_note"},
        )

        eicu = DatasetDefinition(
            name="eicu",
            description="eICU Collaborative Research Database",
            file_listing_url="https://physionet.org/files/eicu-crd/2.0/",
            subdirectories_to_scan=[],
            primary_verification_table="eicu_crd.patient",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["eicu_crd"],
            requires_authentication=True,
            modalities=frozenset({Modality.TABULAR}),
            schema_mapping={"": "eicu_crd"},
            bigquery_schema_mapping={"eicu_crd": "eicu_crd"},
        )

        cls.register(mimic_iv_demo)
        cls.register(mimic_iv)
        cls.register(mimic_iv_note)
        cls.register(eicu)


# Initialize registry
DatasetRegistry._register_builtins()
