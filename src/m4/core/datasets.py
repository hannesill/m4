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
    """Enhanced dataset definition with semantic capabilities.

    This class extends the original DatasetDefinition with:
    - Explicit modality declarations (what kind of data exists)
    - Capability declarations (what operations can be performed)
    - Table name mappings (logical -> physical table names)
    """

    # Original fields (unchanged)
    name: str
    description: str = ""
    version: str = "1.0"
    file_listing_url: str | None = None
    subdirectories_to_scan: list[str] = field(default_factory=list)
    default_duckdb_filename: str | None = None
    primary_verification_table: str | None = None
    tags: list[str] = field(default_factory=list)  # Keep for backward compat

    # BigQuery Configuration (unchanged)
    bigquery_project_id: str | None = "physionet-data"
    bigquery_dataset_ids: list[str] = field(default_factory=list)

    # Authentication (unchanged)
    requires_authentication: bool = False

    # NEW: Semantic capability declarations
    modalities: set[Modality] = field(default_factory=set)
    capabilities: set[Capability] = field(default_factory=set)

    # NEW: Table name mappings (dataset-specific)
    table_mappings: dict[str, str] = field(default_factory=dict)
    """Maps logical table names to physical table names.

    Example for DuckDB:
        {"icustays": "icu_icustays", "labevents": "hosp_labevents"}

    Example for BigQuery (backend will add project/dataset prefix):
        {"icustays": "icustays", "labevents": "labevents"}
    """

    def __post_init__(self):
        """Initialize computed fields and handle backward compatibility."""
        if not self.default_duckdb_filename:
            self.default_duckdb_filename = f"{self.name.replace('-', '_')}.duckdb"

        # Auto-populate capabilities from tags for backward compatibility
        if not self.capabilities and "mimic" in self.tags:
            self._auto_populate_mimic_capabilities()

    def _auto_populate_mimic_capabilities(self):
        """Backward compatibility: infer capabilities from MIMIC tags."""
        self.modalities.add(Modality.TABULAR)
        self.capabilities.update(
            {
                Capability.COHORT_QUERY,
                Capability.SCHEMA_INTROSPECTION,
                Capability.ICU_STAYS,
                Capability.LAB_RESULTS,
                Capability.DEMOGRAPHIC_STATS,
                Capability.MEDICATIONS,
                Capability.PROCEDURES,
                Capability.DIAGNOSES,
            }
        )

        # MIMIC-IV 3.1+ has notes
        if "full" in self.tags or "notes" in self.tags:
            self.modalities.add(Modality.NOTES)
            self.capabilities.add(Capability.CLINICAL_NOTES)


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
        """Register built-in datasets with enhanced capabilities."""
        mimic_iv_demo = DatasetDefinition(
            name="mimic-iv-demo",
            description="MIMIC-IV Clinical Database Demo",
            file_listing_url="https://physionet.org/files/mimic-iv-demo/2.2/",
            subdirectories_to_scan=["hosp", "icu"],
            primary_verification_table="hosp_admissions",
            tags=["mimic", "clinical", "demo"],
            bigquery_project_id=None,
            bigquery_dataset_ids=[],
            # NEW: Explicit capabilities
            modalities={Modality.TABULAR},
            capabilities={
                Capability.COHORT_QUERY,
                Capability.SCHEMA_INTROSPECTION,
                Capability.ICU_STAYS,
                Capability.LAB_RESULTS,
                Capability.DEMOGRAPHIC_STATS,
            },
            # NEW: Table mappings for DuckDB
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
            tags=["mimic", "clinical", "full"],
            bigquery_project_id="physionet-data",
            bigquery_dataset_ids=["mimiciv_3_1_hosp", "mimiciv_3_1_icu"],
            requires_authentication=True,
            # NEW: Explicit capabilities
            modalities={Modality.TABULAR, Modality.NOTES},
            capabilities={
                Capability.COHORT_QUERY,
                Capability.SCHEMA_INTROSPECTION,
                Capability.ICU_STAYS,
                Capability.LAB_RESULTS,
                Capability.DEMOGRAPHIC_STATS,
                Capability.MEDICATIONS,
                Capability.PROCEDURES,
                Capability.DIAGNOSES,
                Capability.CLINICAL_NOTES,
            },
            # NEW: Table mappings (backend-agnostic logical names)
            table_mappings={
                # DuckDB uses these directly
                # BigQuery will prefix with dataset IDs via backend
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
