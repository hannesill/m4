"""Smoke-test an installed M4 distribution before adding any test dependencies.

Run with the clean environment's Python and -I, from outside the checkout.
Only synthetic SQL and empty dataset directories are used.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="m4-distribution-") as temporary:
        work = Path(temporary).resolve()
        for key in list(os.environ):
            if key.startswith("M4_") or key == "PYTHONPATH":
                os.environ.pop(key)
        os.environ["M4_DATA_DIR"] = str(work / "data")
        os.environ["M4_OAUTH2_ENABLED"] = "false"

        import duckdb
        from fastmcp import Client

        import m4
        from m4.apps.cohort_builder import RESOURCE_URI
        from m4.core.serialization import serialize_for_mcp
        from m4.mcp_server import mcp
        from m4.skills.catalog import (
            MANIFEST_FILE_NAME,
            verify_materialized_bundle,
        )

        package = Path(m4.__file__).resolve()
        assert package.is_relative_to(Path(sys.prefix).resolve()), package
        assert m4.__version__ == importlib.metadata.version("m4-infra")
        # This must work even if another dependency happens to install tabulate.
        sys.modules["tabulate"] = None
        table = serialize_for_mcp([{"name": "synthetic", "rows": 2}])
        assert table.splitlines()[1].split() == ["synthetic", "2"]

        def cli(*args: str) -> dict:
            result = subprocess.run(
                [str(Path(sys.executable).parent / "m4"), *args],
                cwd=work,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            assert result.returncode == 0, (args, result.stdout, result.stderr)
            return json.loads(result.stdout)

        status = cli("status", "--all", "--json")
        assert status["version"] == 1
        assert "mimic-iv-demo" in {d["name"] for d in status["datasets"]}
        datasets = cli("list-datasets", "--json", "--no-interactive")
        assert datasets["ok"] and datasets["command"] == "list-datasets"
        db = work / "data" / "databases" / "mimic_iv_demo.duckdb"
        db.parent.mkdir(parents=True, exist_ok=True)
        duckdb.connect(str(db)).close()
        query = cli(
            "query",
            "--dataset",
            "mimic-iv-demo",
            "--backend",
            "duckdb",
            "--sql",
            "SELECT 1 AS one",
            "--json",
            "--no-interactive",
        )
        assert query["ok"]
        assert query["data"]["result"]["rows"] == [{"one": 1}]

        catalog = cli("skills", "catalog", "--json")
        assert catalog["schemaVersion"] == 1
        assert catalog["packageVersion"] == m4.__version__
        assert catalog["publisher"] == "m4"
        assert "m4:clinical-research-pitfalls" in {s["id"] for s in catalog["skills"]}
        target = work / "skills"
        installed = cli("skills", "materialize", "--target", str(target), "--json")
        assert installed["ok"] and not installed["reused"]
        assert installed["bundleDigest"] == catalog["bundleDigest"]
        assert json.loads((target / MANIFEST_FILE_NAME).read_text()) == catalog
        verify_materialized_bundle(target, catalog)
        assert cli("skills", "materialize", "--target", str(target), "--json")["reused"]

        async def check_mcp() -> None:
            async with Client(mcp) as client:
                tool = next(
                    t for t in await client.list_tools() if t.name == "cohort_builder"
                )
                assert (
                    tool.model_dump(by_alias=True)["_meta"]["ui"]["resourceUri"]
                    == RESOURCE_URI
                )
                content = await client.read_resource(RESOURCE_URI)
                assert "<html" in content[0].text.lower()

        asyncio.run(check_mcp())
        print(
            json.dumps(
                {
                    "package": str(package),
                    "version": m4.__version__,
                    "fastmcp": importlib.metadata.version("fastmcp"),
                    "skills": len(catalog["skills"]),
                    "bundleDigest": catalog["bundleDigest"],
                    "status": "passed",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
