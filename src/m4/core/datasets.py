"""Enhanced dataset definitions with semantic capabilities.

This module provides:
- Modality enum: High-level data types (TABULAR, NOTES, IMAGING, WAVEFORM)
- Capability enum: Specific operations that can be performed
- DatasetDefinition: Enhanced dataset metadata with capabilities
- DatasetRegistry: Registry for managing dataset definitions
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import ClassVar


class Modality(Enum):
    """Data types a dataset can contain."""

    TABULAR = auto()  # Structured tables (labs, demographics, vitals)
    NOTES = auto()  # Clinical free-text notes
    IMAGING = auto()  # Medical images (X-rays, CT, MRI)
    WAVEFORM = auto()  # Time-series (ECG, EEG, blood pressure)


class Capability(Enum):
    """Specific operations that can be performed on a dataset."""

    # Core query capabilities
    COHORT_QUERY = auto()  # Build patient cohorts with SQL
    SCHEMA_INTROSPECTION = auto()  # List tables/columns

    # Tabular data capabilities
    ICU_STAYS = auto()  # ICU admission data
    LAB_RESULTS = auto()  # Laboratory test results
    DEMOGRAPHIC_STATS = auto()  # Patient demographics
    MEDICATIONS = auto()  # Prescription data
    PROCEDURES = auto()  # Medical procedures
    DIAGNOSES = auto()  # ICD codes

    # Future capabilities
    CLINICAL_NOTES = auto()  # Free-text note search/analysis
    IMAGE_RETRIEVAL = auto()  # Fetch medical images
    WAVEFORM_QUERY = auto()  # Time-series data access


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
    def reset(cls):
        """Clear registry and re-register built-in datasets."""
        cls._registry.clear()
        cls._register_builtins()

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

        mimic_iv_full = DatasetDefinition(
            name="mimic-iv-full",
            description="MIMIC-IV Clinical Database (Full)",
            file_listing_url="https://physionet.org/files/mimiciv/3.1/",
            subdirectories_to_scan=["hosp", "icu"],
            primary_verification_table="hosp_admissions",
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["mimiciv_3_1_hosp", "mimiciv_3_1_icu"],
            requires_authentication=True,
            modalities=frozenset({Modality.TABULAR, Modality.NOTES}),
            capabilities=frozenset(
                {
                    Capability.COHORT_QUERY,
                    Capability.SCHEMA_INTROSPECTION,
                    Capability.ICU_STAYS,
                    Capability.LAB_RESULTS,
                    Capability.DEMOGRAPHIC_STATS,
                    Capability.MEDICATIONS,
                    Capability.PROCEDURES,
                    Capability.DIAGNOSES,
                    Capability.CLINICAL_NOTES,
                }
            ),
            table_mappings={
                "icustays": "icustays",
                "labevents": "labevents",
                "admissions": "admissions",
                "patients": "patients",
            },
        )

        cls.register(mimic_iv_demo)
        cls.register(mimic_iv_full)


# Initialize registry
DatasetRegistry._register_builtins()
