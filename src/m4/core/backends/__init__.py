"""M4 Core Backends - Database backend implementations.

This package provides the backend abstraction layer for M4:
- Backend protocol: Interface for all database backends
- DuckDBBackend: Local DuckDB database queries
- BigQueryBackend: Google BigQuery cloud queries
- get_backend(): Factory function for backend selection
"""

import os
import threading

from m4.core.backends.base import (
    Backend,
    BackendError,
    ConnectionError,
    QueryExecutionError,
    QueryResult,
    TableNotFoundError,
)
from m4.core.backends.bigquery import BigQueryBackend
from m4.core.backends.duckdb import DuckDBBackend

# Cache for backend instances with thread safety
_backend_lock = threading.Lock()
_backend_cache: dict[str, Backend] = {}


def get_backend(backend_type: str | None = None) -> Backend:
    """Get a backend instance based on type.

    This factory function returns the appropriate backend implementation
    based on the requested type. Backends are cached for reuse. Thread-safe.

    Args:
        backend_type: Type of backend ('duckdb' or 'bigquery').
                     If None, uses M4_BACKEND environment variable,
                     defaulting to 'duckdb'.

    Returns:
        Backend instance

    Raises:
        ValueError: If an unsupported backend type is requested

    Example:
        # Get default backend
        backend = get_backend()

        # Get specific backend
        bq_backend = get_backend("bigquery")
    """
    if backend_type is None:
        backend_type = os.getenv("M4_BACKEND", "duckdb")

    backend_type = backend_type.lower()

    with _backend_lock:
        # Check cache
        if backend_type in _backend_cache:
            return _backend_cache[backend_type]

        # Create new backend
        if backend_type == "duckdb":
            backend = DuckDBBackend()
        elif backend_type == "bigquery":
            backend = BigQueryBackend()
        else:
            raise ValueError(
                f"Unsupported backend: {backend_type}. "
                "Supported backends: duckdb, bigquery"
            )

        _backend_cache[backend_type] = backend
        return backend


def reset_backend_cache() -> None:
    """Clear the backend cache.

    Useful for testing or when backend configuration changes. Thread-safe.
    """
    with _backend_lock:
        _backend_cache.clear()


__all__ = [
    "Backend",
    "BackendError",
    "BigQueryBackend",
    "ConnectionError",
    "DuckDBBackend",
    "QueryExecutionError",
    "QueryResult",
    "TableNotFoundError",
    "get_backend",
    "reset_backend_cache",
]
