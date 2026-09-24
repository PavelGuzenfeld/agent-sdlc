"""Intent: #185 — every key `Config.load` accepts, including its nested
tables' fields, has a row in docs/config.md. Keys come from the dataclasses,
so a field added later fails here until the reference names it."""

from dataclasses import fields
from pathlib import Path

import pytest

from mutation_gate.repo import Config, DocAllow, Golden, LanguageConfig, ModelExclude

CONFIG_DOCS_PATH = Path(__file__).parents[2] / "docs" / "config.md"

TOP_LEVEL_FIELDS = sorted(
    {f.name for f in fields(Config)} | {f.name for f in fields(LanguageConfig)}
)

NESTED_TABLES = {"model_exclude": ModelExclude, "golden": Golden, "doc_allow": DocAllow}
NESTED_FIELDS = [
    (table, f.name) for table, cls in NESTED_TABLES.items() for f in fields(cls)
]


@pytest.mark.parametrize("name", TOP_LEVEL_FIELDS)
def test_every_config_field_has_its_own_row(name):
    assert f"| `{name}` |" in CONFIG_DOCS_PATH.read_text()


@pytest.mark.parametrize("table,field_name", NESTED_FIELDS)
def test_every_nested_table_field_is_named_in_its_row(table, field_name):
    docs = CONFIG_DOCS_PATH.read_text()
    row_start = docs.index(f"| `{table}` |")
    row_end = docs.index("\n", row_start)
    assert f"`{field_name}`" in docs[row_start:row_end]
