"""Enhanced dataset definitions with semantic capabilities.

This module provides:
- Modality enum: High-level data types (TABULAR, NOTES, IMAGING, WAVEFORM)
- Capability enum: Specific operations that can be performed
- DatasetDefinition: Enhanced dataset metadata with capabilities
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
    """Data types a dataset can contain."""

    TABULAR = auto()  # Structured tables (labs, demographics, vitals)


class Capability(Enum):
    """Specific operations that can be performed on a dataset."""

    # Core query capabilities
    COHORT_QUERY = auto()  # Build patient cohorts with SQL
    SCHEMA_INTROSPECTION = auto()  # List tables/columns

    # Tabular data capabilities
    ICU_STAYS = auto()  # ICU admission data
    LAB_RESULTS = auto()  # Laboratory test results
    DEMOGRAPHIC_STATS = auto()  # Patient demographics


@dataclass
class DatasetDefinition:
    """Dataset definition with semantic capabilities.

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
        capabilities: Immutable set of supported operations
        table_mappings: Logical to physical table name mappings
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

    # Semantic capability declarations (immutable)
    modalities: frozenset[Modality] = field(default_factory=frozenset)
    capabilities: frozenset[Capability] = field(default_factory=frozenset)

    # Table name mappings (dataset-specific)
    table_mappings: dict[str, str] = field(default_factory=dict)

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

        JSON files can specify modalities and capabilities as string arrays:
            "modalities": ["TABULAR"],
            "capabilities": ["COHORT_QUERY", "SCHEMA_INTROSPECTION"]

        If not specified, sensible defaults are applied (TABULAR modality with
        COHORT_QUERY and SCHEMA_INTROSPECTION capabilities).

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
                    # Default: TABULAR modality for basic functionality
                    data["modalities"] = frozenset({Modality.TABULAR})

                if "capabilities" in data:
                    data["capabilities"] = frozenset(
                        Capability[c] for c in data["capabilities"]
                    )
                else:
                    # Default: basic query capabilities
                    data["capabilities"] = frozenset(
                        {Capability.COHORT_QUERY, Capability.SCHEMA_INTROSPECTION}
                    )

                ds = DatasetDefinition(**data)
                cls.register(ds)
                logger.debug(f"Loaded custom dataset: {ds.name}")
            except KeyError as e:
                logger.warning(
                    f"Failed to load custom dataset from {f}: "
                    f"Invalid modality or capability name: {e}"
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
            primary_verification_table="hosp_admissions",
            bigquery_project_id=None,
            bigquery_dataset_ids=[],
            modalities=frozenset({Modality.TABULAR}),
            capabilities=frozenset(
                {
                    Capability.COHORT_QUERY,
                    Capability.SCHEMA_INTROSPECTION,
                    Capability.ICU_STAYS,
                    Capability.LAB_RESULTS,
                    Capability.DEMOGRAPHIC_STATS,
                }
            ),
            table_mappings={
                "icustays": "icu_icustays",
                "labevents": "hosp_labevents",
                "admissions": "hosp_admissions",
                "patients": "hosp_patients",
            },
        )

        mimic_iv = DatasetDefinition(
            name="mimic-iv",
            description="MIMIC-IV Clinical Database",
            file_listing_url="https://physionet.org/files/mimiciv/3.1/",
            subdirectories_to_scan=["hosp", "icu"],
            primary_verification_table="hosp_admissions",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["mimiciv_3_1_hosp", "mimiciv_3_1_icu"],
            requires_authentication=True,
            modalities=frozenset({Modality.TABULAR}),
            capabilities=frozenset(
                {
                    Capability.COHORT_QUERY,
                    Capability.SCHEMA_INTROSPECTION,
                    Capability.ICU_STAYS,
                    Capability.LAB_RESULTS,
                    Capability.DEMOGRAPHIC_STATS,
                }
            ),
            table_mappings={
                "icustays": "icustays",
                "labevents": "labevents",
                "admissions": "admissions",
                "patients": "patients",
            },
        )

        eicu = DatasetDefinition(
            name="eicu",
            description="eICU Collaborative Research Database",
            file_listing_url="https://physionet.org/files/eicu-crd/2.0/",
            subdirectories_to_scan=[],
            primary_verification_table="patient",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["eicu_crd"],
            requires_authentication=True,
            modalities=frozenset({Modality.TABULAR}),
            capabilities=frozenset(
                {
                    Capability.COHORT_QUERY,
                    Capability.SCHEMA_INTROSPECTION,
                    Capability.ICU_STAYS,
                    Capability.LAB_RESULTS,
                    Capability.DEMOGRAPHIC_STATS,
                }
            ),
            table_mappings={
                "icustays": "patient",
                "labevents": "lab",
                "admissions": "patient",
                "patients": "patient",
            },
        )

        cls.register(mimic_iv_demo)
        cls.register(mimic_iv)
        cls.register(eicu)


# Initialize registry
DatasetRegistry._register_builtins()
