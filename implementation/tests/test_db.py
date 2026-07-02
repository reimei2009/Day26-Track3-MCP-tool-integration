from __future__ import annotations

import pytest

from db import SQLiteAdapter, ValidationError
from init_db import create_database


@pytest.fixture()
def adapter(tmp_path):
    db_path = create_database(tmp_path / "lab.sqlite3")
    return SQLiteAdapter(db_path)


def test_search_filters_ordering_and_pagination(adapter):
    result = adapter.search(
        "students",
        columns=["name", "cohort", "score"],
        filters=[{"column": "score", "op": "gte", "value": 80}],
        limit=2,
        order_by="score",
        descending=True,
    )

    assert result["count"] == 2
    assert result["rows"][0]["score"] >= result["rows"][1]["score"]


def test_insert_returns_inserted_payload(adapter):
    result = adapter.insert(
        "students",
        {
            "name": "Lan Do",
            "email": "lan.do@example.com",
            "cohort": "C3",
            "score": 89.0,
        },
    )

    assert result["inserted_id"] > 0
    assert result["values"]["email"] == "lan.do@example.com"


def test_aggregate_avg_by_group(adapter):
    result = adapter.aggregate("students", "avg", column="score", group_by="cohort")

    cohorts = {row["cohort"] for row in result["rows"]}
    assert {"A1", "B2", "C3"}.issubset(cohorts)


def test_schema_contains_foreign_keys(adapter):
    schema = adapter.get_table_schema("enrollments")

    assert schema["name"] == "enrollments"
    assert {fk["references_table"] for fk in schema["foreign_keys"]} == {"students", "courses"}


@pytest.mark.parametrize(
    ("callable_name", "args", "message"),
    [
        ("search", ("missing_table",), "unknown table"),
        ("search", ("students", ["missing_column"]), "unknown column"),
        ("aggregate", ("students", "median", "score"), "unsupported aggregate metric"),
        ("insert", ("students", {}), "non-empty object"),
    ],
)
def test_invalid_requests_are_rejected(adapter, callable_name, args, message):
    with pytest.raises(ValidationError, match=message):
        getattr(adapter, callable_name)(*args)
