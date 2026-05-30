import importlib.util
import re
from pathlib import Path

from m4.core.derived.builtins import get_tables_by_category

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "update_derived_docs", ROOT / "scripts" / "update_derived_docs.py"
)
assert SPEC and SPEC.loader
update_derived_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_derived_docs)
START = update_derived_docs.START
END = update_derived_docs.END
generated_block = update_derived_docs.generated_block


def test_derived_docs_block_matches_builtins():
    tools = ROOT / "docs" / "TOOLS.md"
    text = tools.read_text()
    start = text.index(START)
    end = text.index(END) + len(END)

    assert text[start:end] == generated_block()


def test_derived_docs_include_current_category_tables():
    block = generated_block()
    categories = get_tables_by_category("mimic-iv")

    for tables in categories.values():
        for table in tables:
            assert f"`{table}`" in block


def test_stale_derived_count_absent_from_docs():
    for path in [ROOT / "docs" / "TOOLS.md", ROOT / "docs" / "DEVELOPMENT.md"]:
        text = path.read_text()
        assert '"total": 42' not in text
        assert '"materialized": 42' not in text


def test_package_urls_use_canonical_github_repo():
    pyproject = (ROOT / "pyproject.toml").read_text()
    urls = re.findall(r'https://github.com/[^\s"]+', pyproject)

    assert urls
    assert all(url.startswith("https://github.com/hannesill/m4") for url in urls)
