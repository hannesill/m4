"""Disk-backed artifact store for the display pipeline.

Persists large objects (DataFrames, chart specs) to disk so the WebSocket
stays lightweight. The artifact store uses a session directory layout:

    {m4_data}/display/{session_id}/
    ├── index.json              # Card descriptors in insertion order
    ├── artifacts/
    │   ├── {card_id}.parquet   # DataFrame artifacts
    │   ├── {card_id}.json      # Plotly specs, key-value data
    │   └── {card_id}.svg       # Rendered matplotlib figures
    └── meta.json               # Session metadata
"""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from m4.display._types import CardDescriptor, CardProvenance, CardType

logger = logging.getLogger(__name__)


def _serialize_card(card: CardDescriptor) -> dict[str, Any]:
    """Serialize a CardDescriptor to a JSON-compatible dict."""
    d: dict[str, Any] = {
        "card_id": card.card_id,
        "card_type": card.card_type.value,
        "title": card.title,
        "description": card.description,
        "timestamp": card.timestamp,
        "run_id": card.run_id,
        "pinned": card.pinned,
        "artifact_id": card.artifact_id,
        "artifact_type": card.artifact_type,
        "preview": card.preview,
        "response_requested": card.response_requested,
        "prompt": card.prompt,
        "on_send": card.on_send,
        "timeout": card.timeout,
    }
    if card.provenance:
        d["provenance"] = {
            "source": card.provenance.source,
            "query": card.provenance.query,
            "code_hash": card.provenance.code_hash,
            "dataset": card.provenance.dataset,
            "timestamp": card.provenance.timestamp,
        }
    else:
        d["provenance"] = None
    return d


def _deserialize_card(d: dict[str, Any]) -> CardDescriptor:
    """Deserialize a dict back into a CardDescriptor."""
    provenance = None
    if d.get("provenance"):
        p = d["provenance"]
        provenance = CardProvenance(
            source=p.get("source"),
            query=p.get("query"),
            code_hash=p.get("code_hash"),
            dataset=p.get("dataset"),
            timestamp=p.get("timestamp"),
        )
    return CardDescriptor(
        card_id=d["card_id"],
        card_type=CardType(d["card_type"]),
        title=d.get("title"),
        description=d.get("description"),
        timestamp=d.get("timestamp", ""),
        run_id=d.get("run_id"),
        pinned=d.get("pinned", False),
        artifact_id=d.get("artifact_id"),
        artifact_type=d.get("artifact_type"),
        preview=d.get("preview", {}),
        provenance=provenance,
        response_requested=d.get("response_requested", False),
        prompt=d.get("prompt"),
        on_send=d.get("on_send"),
        timeout=d.get("timeout"),
    )


class ArtifactStore:
    """Disk-backed store for display artifacts.

    Each session gets its own directory. Card descriptors are maintained
    in an index.json file. Large artifacts (DataFrames, chart specs) are
    stored as separate files in an artifacts/ subdirectory.

    Args:
        session_dir: Path to the session directory. Created if it doesn't exist.
        session_id: Unique identifier for this session.
    """

    def __init__(self, session_dir: Path, session_id: str) -> None:
        self.session_dir = session_dir
        self.session_id = session_id
        self._artifacts_dir = session_dir / "artifacts"
        self._index_path = session_dir / "index.json"
        self._meta_path = session_dir / "meta.json"

        # Ensure directories exist
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Initialize index if it doesn't exist
        if not self._index_path.exists():
            self._write_index([])

        # Write session metadata
        if not self._meta_path.exists():
            meta = {
                "session_id": session_id,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "run_ids": [],
            }
            self._meta_path.write_text(json.dumps(meta, indent=2))

    def _read_index(self) -> list[dict[str, Any]]:
        """Read the card index from disk."""
        try:
            return json.loads(self._index_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_index(self, cards: list[dict[str, Any]]) -> None:
        """Write the card index to disk."""
        self._index_path.write_text(json.dumps(cards, indent=2))

    def _append_to_index(self, card_dict: dict[str, Any]) -> None:
        """Append a card to the index."""
        cards = self._read_index()
        cards.append(card_dict)
        self._write_index(cards)

    def _track_run_id(self, run_id: str | None) -> None:
        """Track a run_id in session metadata."""
        if not run_id:
            return
        try:
            meta = json.loads(self._meta_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            meta = {"session_id": self.session_id, "run_ids": []}
        if run_id not in meta.get("run_ids", []):
            meta.setdefault("run_ids", []).append(run_id)
            self._meta_path.write_text(json.dumps(meta, indent=2))

    def store_card(self, card: CardDescriptor) -> None:
        """Store a card descriptor in the index.

        Args:
            card: The card descriptor to store.
        """
        self._append_to_index(_serialize_card(card))
        self._track_run_id(card.run_id)

    def store_dataframe(self, card_id: str, df: pd.DataFrame) -> Path:
        """Store a DataFrame as a Parquet artifact.

        Args:
            card_id: Unique card identifier used as the filename.
            df: DataFrame to store.

        Returns:
            Path to the stored Parquet file.
        """
        path = self._artifacts_dir / f"{card_id}.parquet"
        df.to_parquet(path, index=False)
        logger.debug(f"Stored DataFrame artifact: {path} ({len(df)} rows)")
        return path

    def store_json(self, card_id: str, data: dict[str, Any]) -> Path:
        """Store a JSON artifact (e.g., Plotly spec, key-value data).

        Args:
            card_id: Unique card identifier used as the filename.
            data: Dictionary to store as JSON.

        Returns:
            Path to the stored JSON file.
        """
        path = self._artifacts_dir / f"{card_id}.json"
        path.write_text(json.dumps(data, indent=2, default=str))
        logger.debug(f"Stored JSON artifact: {path}")
        return path

    def store_image(self, card_id: str, data: bytes, fmt: str) -> Path:
        """Store an image artifact (SVG, PNG).

        Args:
            card_id: Unique card identifier used as the filename.
            data: Raw image bytes.
            fmt: Image format extension (e.g., 'svg', 'png').

        Returns:
            Path to the stored image file.
        """
        path = self._artifacts_dir / f"{card_id}.{fmt}"
        path.write_bytes(data)
        logger.debug(f"Stored image artifact: {path} ({len(data)} bytes)")
        return path

    @staticmethod
    def _sanitize_search(search: str) -> str | None:
        """Sanitize a search string, returning None if invalid."""
        if not search or not search.strip():
            return None
        s = search.strip()
        # Reject SQL keywords to prevent injection
        sql_keywords = re.compile(
            r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|EXEC|UNION|--|;)\b",
            re.IGNORECASE,
        )
        if sql_keywords.search(s):
            return None
        # Only allow alphanumeric, spaces, basic punctuation
        if not re.match(r"^[\w\s.,\-:/'\"()]+$", s):
            return None
        return s

    def _parquet_columns(
        self, path: Path, con: duckdb.DuckDBPyConnection
    ) -> list[tuple[str, str]]:
        """Return list of (column_name, column_type) for a Parquet file."""
        rows = con.execute(
            f"SELECT name, type FROM parquet_schema('{path}') WHERE name != 'duckdb_schema'"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def _build_search_where(
        self,
        search: str,
        col_info: list[tuple[str, str]],
    ) -> str:
        """Build a WHERE clause that searches across all columns."""
        escaped = search.replace("'", "''")
        clauses = []
        for col_name, col_type in col_info:
            upper = col_type.upper()
            if any(t in upper for t in ("VARCHAR", "UTF8", "STRING", "TEXT")):
                clauses.append(f"\"{col_name}\" ILIKE '%{escaped}%'")
            else:
                # Cast non-text columns to VARCHAR for general search
                clauses.append(f"CAST(\"{col_name}\" AS VARCHAR) ILIKE '%{escaped}%'")
        if not clauses:
            return ""
        return " WHERE " + " OR ".join(clauses)

    def read_table_page(
        self,
        card_id: str,
        offset: int = 0,
        limit: int = 50,
        sort_col: str | None = None,
        sort_asc: bool = True,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Read a page of rows from a stored Parquet artifact using DuckDB.

        Args:
            card_id: Card ID whose Parquet artifact to read.
            offset: Row offset for paging.
            limit: Maximum rows to return.
            sort_col: Column to sort by (None for insertion order).
            sort_asc: Sort ascending if True, descending if False.
            search: Free-text search string (ILIKE across all columns).

        Returns:
            Dict with 'columns', 'rows', 'total_rows', 'offset', 'limit'.

        Raises:
            FileNotFoundError: If no Parquet artifact exists for this card_id.
        """
        path = self._artifacts_dir / f"{card_id}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"No Parquet artifact for card {card_id}")

        con = duckdb.connect(":memory:")
        try:
            col_info = self._parquet_columns(path, con)
            col_names = [c[0] for c in col_info]

            # Build WHERE clause for search
            where = ""
            sanitized = self._sanitize_search(search) if search else None
            if sanitized:
                where = self._build_search_where(sanitized, col_info)

            # Get total row count (filtered if searching)
            total = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{path}'){where}"
            ).fetchone()[0]

            # Build query
            query = f"SELECT * FROM read_parquet('{path}'){where}"

            if sort_col and sort_col in col_names:
                direction = "ASC" if sort_asc else "DESC"
                query += f' ORDER BY "{sort_col}" {direction}'

            query += f" LIMIT {int(limit)} OFFSET {int(offset)}"

            result = con.execute(query)
            columns = [desc[0] for desc in result.description]
            rows = [list(row) for row in result.fetchall()]

            return {
                "columns": columns,
                "rows": rows,
                "total_rows": total,
                "offset": offset,
                "limit": limit,
            }
        finally:
            con.close()

    def table_stats(self, card_id: str) -> dict[str, dict[str, Any]]:
        """Compute per-column statistics for a stored Parquet artifact.

        Args:
            card_id: Card ID whose Parquet artifact to analyze.

        Returns:
            Dict mapping column name → stats dict with keys like
            min, max, mean, null_count, approx_unique.

        Raises:
            FileNotFoundError: If no Parquet artifact exists for this card_id.
        """
        path = self._artifacts_dir / f"{card_id}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"No Parquet artifact for card {card_id}")

        con = duckdb.connect(":memory:")
        try:
            col_info = self._parquet_columns(path, con)
            stats: dict[str, dict[str, Any]] = {}

            for col_name, col_type in col_info:
                upper = col_type.upper()
                is_numeric = any(
                    t in upper
                    for t in (
                        "INT",
                        "FLOAT",
                        "DOUBLE",
                        "DECIMAL",
                        "NUMERIC",
                        "BIGINT",
                        "SMALLINT",
                        "TINYINT",
                    )
                )

                aggs = [
                    f'COUNT(*) - COUNT("{col_name}") AS null_count',
                    f'APPROX_COUNT_DISTINCT("{col_name}") AS approx_unique',
                    f'MIN("{col_name}") AS min_val',
                    f'MAX("{col_name}") AS max_val',
                ]
                if is_numeric:
                    aggs.append(f'AVG("{col_name}") AS mean_val')

                row = con.execute(
                    f"SELECT {', '.join(aggs)} FROM read_parquet('{path}')"
                ).fetchone()

                col_stats: dict[str, Any] = {
                    "null_count": row[0],
                    "approx_unique": row[1],
                    "min": self._serialize_value(row[2]),
                    "max": self._serialize_value(row[3]),
                }
                if is_numeric:
                    col_stats["mean"] = round(row[4], 4) if row[4] is not None else None

                stats[col_name] = col_stats

            return stats
        finally:
            con.close()

    @staticmethod
    def _serialize_value(val: Any) -> Any:
        """Convert DuckDB values to JSON-serializable types."""
        if val is None:
            return None
        if hasattr(val, "isoformat"):
            return val.isoformat()
        try:
            json.dumps(val)
            return val
        except (TypeError, ValueError):
            return str(val)

    def export_table_csv(
        self,
        card_id: str,
        sort_col: str | None = None,
        sort_asc: bool = True,
        search: str | None = None,
    ) -> str:
        """Export a full table as CSV (with optional sort/search but no pagination).

        Args:
            card_id: Card ID whose Parquet artifact to export.
            sort_col: Column to sort by.
            sort_asc: Sort ascending if True.
            search: Free-text search filter.

        Returns:
            CSV string of the full (optionally filtered/sorted) table.

        Raises:
            FileNotFoundError: If no Parquet artifact exists for this card_id.
        """
        path = self._artifacts_dir / f"{card_id}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"No Parquet artifact for card {card_id}")

        con = duckdb.connect(":memory:")
        try:
            col_info = self._parquet_columns(path, con)
            col_names = [c[0] for c in col_info]

            where = ""
            sanitized = self._sanitize_search(search) if search else None
            if sanitized:
                where = self._build_search_where(sanitized, col_info)

            query = f"SELECT * FROM read_parquet('{path}'){where}"

            if sort_col and sort_col in col_names:
                direction = "ASC" if sort_asc else "DESC"
                query += f' ORDER BY "{sort_col}" {direction}'

            df = con.execute(query).fetchdf()
            buf = io.StringIO()
            df.to_csv(buf, index=False)
            return buf.getvalue()
        finally:
            con.close()

    def get_artifact(self, card_id: str) -> bytes | dict[str, Any]:
        """Retrieve a raw artifact by card ID.

        Checks for Parquet, JSON, SVG, and PNG files in order.

        Args:
            card_id: Card ID to look up.

        Returns:
            Raw bytes for binary artifacts, or dict for JSON artifacts.

        Raises:
            FileNotFoundError: If no artifact exists for this card_id.
        """
        for ext in ("parquet", "json", "svg", "png"):
            path = self._artifacts_dir / f"{card_id}.{ext}"
            if path.exists():
                if ext == "json":
                    return json.loads(path.read_text())
                return path.read_bytes()
        raise FileNotFoundError(f"No artifact found for card {card_id}")

    def list_cards(self, run_id: str | None = None) -> list[CardDescriptor]:
        """List all card descriptors in insertion order.

        Args:
            run_id: If provided, filter to cards with this run_id.

        Returns:
            List of CardDescriptors in the order they were added.
        """
        cards = [_deserialize_card(d) for d in self._read_index()]
        if run_id is not None:
            cards = [c for c in cards if c.run_id == run_id]
        return cards

    def update_card(self, card_id: str, **changes: Any) -> CardDescriptor | None:
        """Update fields on an existing card.

        Args:
            card_id: ID of the card to update.
            **changes: Field names and new values.

        Returns:
            Updated CardDescriptor, or None if card not found.
        """
        index = self._read_index()
        for i, d in enumerate(index):
            if d["card_id"] == card_id:
                for key, value in changes.items():
                    if key == "card_type" and isinstance(value, CardType):
                        d[key] = value.value
                    else:
                        d[key] = value
                self._write_index(index)
                return _deserialize_card(d)
        return None

    def clear(self, keep_pinned: bool = True) -> None:
        """Clear all cards and artifacts from the session.

        Args:
            keep_pinned: If True, preserve cards with pinned=True.
        """
        index = self._read_index()

        if keep_pinned:
            pinned = [d for d in index if d.get("pinned", False)]
            removed = [d for d in index if not d.get("pinned", False)]
        else:
            pinned = []
            removed = index

        # Delete artifact files for removed cards
        for card_dict in removed:
            card_id = card_dict["card_id"]
            for ext in ("parquet", "json", "svg", "png"):
                path = self._artifacts_dir / f"{card_id}.{ext}"
                if path.exists():
                    path.unlink()

        self._write_index(pinned)
        logger.debug(f"Cleared {len(removed)} cards, kept {len(pinned)} pinned")

    def store_selection(self, selection_id: str, rows: list, columns: list) -> Path:
        """Store a selection of rows as a Parquet artifact.

        Args:
            selection_id: Unique ID for this selection.
            rows: List of row data (each row is a list of values).
            columns: Column names corresponding to row values.

        Returns:
            Path to the stored Parquet file.
        """
        df = pd.DataFrame(rows, columns=columns)
        return self.store_dataframe(selection_id, df)

    def store_selection_json(self, selection_id: str, data: dict) -> Path:
        """Store a chart point selection as a JSON artifact.

        Args:
            selection_id: Unique ID for this selection.
            data: Dict with selection data (e.g., {"points": [...]}).

        Returns:
            Path to the stored JSON file.
        """
        return self.store_json(selection_id, data)

    @property
    def _requests_path(self) -> Path:
        """Path to the requests queue file."""
        return self.session_dir / "requests.json"

    def store_request(self, request: dict[str, Any]) -> None:
        """Append a request to the request queue.

        Args:
            request: Request dict with request_id, card_id, prompt, etc.
        """
        requests = self._read_requests()
        request.setdefault("acknowledged", False)
        requests.append(request)
        self._requests_path.write_text(json.dumps(requests, indent=2))

    def _read_requests(self) -> list[dict[str, Any]]:
        """Read the request queue from disk."""
        if not self._requests_path.exists():
            return []
        try:
            return json.loads(self._requests_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def list_requests(self, pending_only: bool = True) -> list[dict[str, Any]]:
        """List requests from the queue.

        Args:
            pending_only: If True, only return unacknowledged requests.

        Returns:
            List of request dicts.
        """
        requests = self._read_requests()
        if pending_only:
            requests = [r for r in requests if not r.get("acknowledged", False)]
        return requests

    def acknowledge_request(self, request_id: str) -> None:
        """Mark a request as acknowledged in the queue.

        Args:
            request_id: ID of the request to acknowledge.
        """
        requests = self._read_requests()
        for r in requests:
            if r.get("request_id") == request_id:
                r["acknowledged"] = True
                break
        self._requests_path.write_text(json.dumps(requests, indent=2))

    def delete_session(self) -> None:
        """Delete the entire session directory."""
        if self.session_dir.exists():
            shutil.rmtree(self.session_dir)
            logger.debug(f"Deleted session directory: {self.session_dir}")
