from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from db import SQLiteAdapter, ValidationError
from init_db import DEFAULT_DB_PATH, create_database


mcp = FastMCP("SQLite Lab MCP Server")


def get_adapter() -> SQLiteAdapter:
    db_path = Path(os.environ.get("SQLITE_LAB_DB_PATH", DEFAULT_DB_PATH))
    if not db_path.exists():
        create_database(db_path)
    return SQLiteAdapter(db_path)


@mcp.tool(name="search")
def search(
    table: str,
    filters: list[dict[str, Any]] | dict[str, Any] | None = None,
    columns: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str | None = None,
    descending: bool = False,
) -> dict[str, Any]:
    """Search rows with safe filters, ordering, and pagination."""
    return get_adapter().search(table, columns, filters, limit, offset, order_by, descending)


@mcp.tool(name="insert")
def insert(table: str, values: dict[str, Any]) -> dict[str, Any]:
    """Insert one row and return the inserted database payload."""
    return get_adapter().insert(table, values)


@mcp.tool(name="aggregate")
def aggregate(
    table: str,
    metric: str,
    column: str | None = None,
    filters: list[dict[str, Any]] | dict[str, Any] | None = None,
    group_by: str | list[str] | None = None,
) -> dict[str, Any]:
    """Run count, avg, sum, min, or max with optional filters and grouping."""
    return get_adapter().aggregate(table, metric, column, filters, group_by)


@mcp.resource("schema://database")
def database_schema() -> str:
    """Return a JSON snapshot of all database tables, columns, and foreign keys."""
    return json.dumps(get_adapter().database_schema(), indent=2)


@mcp.resource("schema://table/{table_name}")
def table_schema(table_name: str) -> str:
    """Return a JSON schema description for one validated table."""
    return json.dumps(get_adapter().get_table_schema(table_name), indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SQLite Lab FastMCP server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        help="FastMCP transport to run. stdio is the default for local MCP clients.",
    )
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")))
    args = parser.parse_args()

    get_adapter()
    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    try:
        main()
    except ValidationError as exc:
        raise SystemExit(str(exc)) from exc
