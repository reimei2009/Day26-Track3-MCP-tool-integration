from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fastmcp import Client

from init_db import create_database
from mcp_server import mcp


def _content_to_json(result: Any) -> Any:
    payload = result.content[0]
    text = getattr(payload, "text", None)
    if text is not None:
        return json.loads(text)
    return payload


async def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "verify.sqlite3"
        create_database(db_path)
        os.environ["SQLITE_LAB_DB_PATH"] = str(db_path)

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = sorted(tool.name for tool in tools)
            assert tool_names == ["aggregate", "insert", "search"], tool_names
            print(f"tools: {', '.join(tool_names)}")

            resources = await client.list_resources()
            resource_uris = [str(resource.uri) for resource in resources]
            assert "schema://database" in resource_uris, resource_uris
            templates = await client.list_resource_templates()
            template_uris = [str(template.uriTemplate) for template in templates]
            assert "schema://table/{table_name}" in template_uris, template_uris
            print("resources: schema://database, schema://table/{table_name}")

            search_result = _content_to_json(
                await client.call_tool(
                    "search",
                    {
                        "table": "students",
                        "filters": {"cohort": "A1"},
                        "columns": ["id", "name", "cohort", "score"],
                        "order_by": "score",
                        "descending": True,
                    },
                )
            )
            assert search_result["count"] == 2, search_result
            print(f"search cohort A1: {search_result['rows']}")

            insert_result = _content_to_json(
                await client.call_tool(
                    "insert",
                    {
                        "table": "students",
                        "values": {
                            "name": "Minh Hoang",
                            "email": "minh.hoang@example.com",
                            "cohort": "A1",
                            "score": 85.0,
                        },
                    },
                )
            )
            assert insert_result["values"]["name"] == "Minh Hoang", insert_result
            print(f"insert student id: {insert_result['inserted_id']}")

            aggregate_result = _content_to_json(
                await client.call_tool(
                    "aggregate",
                    {"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"},
                )
            )
            assert any(row["cohort"] == "A1" for row in aggregate_result["rows"]), aggregate_result
            print(f"avg score by cohort: {aggregate_result['rows']}")

            schema_result = await client.read_resource("schema://table/students")
            schema_text = schema_result[0].text
            assert '"name": "students"' in schema_text, schema_text
            print("table schema read: students")

            invalid_result = await client.call_tool(
                "search", {"table": "missing_table"}, raise_on_error=False
            )
            assert invalid_result.is_error is True, invalid_result
            invalid_text = invalid_result.content[0].text
            assert "unknown table" in invalid_text, invalid_text
            print(f"invalid request rejected: {invalid_text}")


if __name__ == "__main__":
    asyncio.run(main())
