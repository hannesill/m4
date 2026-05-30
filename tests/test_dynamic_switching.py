"""Tests for the removed global dataset switching compatibility shims."""

import pytest

from m4.config import get_active_dataset, set_active_dataset
from m4.core.datasets import DatasetRegistry
from m4.core.exceptions import DatasetError


def test_global_dataset_accessors_raise_migration_errors():
    """Global dataset state has been removed in favor of explicit selection."""
    with pytest.raises(DatasetError, match="Global active dataset state"):
        get_active_dataset()

    with pytest.raises(DatasetError, match="Cannot set active dataset"):
        set_active_dataset("mimic-iv")


def test_dataset_registry_get_active_raises_migration_error():
    """DatasetRegistry.get_active is retained only for migration guidance."""
    with pytest.raises(DatasetError, match=r"DatasetRegistry\.get_active"):
        DatasetRegistry.get_active()


def test_dataset_registry_explicit_get_still_returns_definitions():
    """Explicit dataset lookup remains the supported registry API."""
    full_ds = DatasetRegistry.get("mimic-iv")
    assert full_ds is not None
    assert full_ds.requires_authentication is True

    demo_ds = DatasetRegistry.get("mimic-iv-demo")
    assert demo_ds is not None
    assert demo_ds.requires_authentication is False
