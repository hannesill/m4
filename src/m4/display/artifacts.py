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

import json
import logging
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

    def read_table_page(
        self,
        card_id: str,
        offset: int = 0,
        limit: int = 50,
        sort_col: str | None = None,
        sort_asc: bool = True,
        filter_expr: str | None = None,
    ) -> dict[str, Any]:
        """Read a page of rows from a stored Parquet artifact using DuckDB.

        Args:
            card_id: Card ID whose Parquet artifact to read.
            offset: Row offset for paging.
            limit: Maximum rows to return.
            sort_col: Column to sort by (None for insertion order).
            sort_asc: Sort ascending if True, descending if False.
            filter_expr: SQL WHERE expression for filtering (not yet implemented).

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
            # Get total row count
            total = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{path}')"
            ).fetchone()[0]

            # Build query
            query = f"SELECT * FROM read_parquet('{path}')"

            if sort_col:
                direction = "ASC" if sort_asc else "DESC"
                # Validate sort_col is an actual column name to prevent injection
                columns = [
                    row[0]
                    for row in con.execute(
                        f"SELECT name FROM parquet_schema('{path}')"
                    ).fetchall()
                ]
                if sort_col in columns:
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

    def delete_session(self) -> None:
        """Delete the entire session directory."""
        if self.session_dir.exists():
            shutil.rmtree(self.session_dir)
            logger.debug(f"Deleted session directory: {self.session_dir}")
