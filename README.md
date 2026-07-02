# Day 26 Lab - Database MCP Server with FastMCP and SQLite

This repository implements a local Model Context Protocol server that exposes a small SQLite student database through three tools:

- `search`
- `insert`
- `aggregate`

It also exposes database schema context through MCP resources:

- `schema://database`
- `schema://table/{table_name}`

The implementation is intentionally small, reproducible, and validation-heavy so it can be reviewed and graded against the lab rubric.

## Project Structure

```text
implementation/
  db.py                 # SQLite adapter, validation, safe SQL builders
  init_db.py            # reproducible schema and seed data
  mcp_server.py         # FastMCP tools and resources
  verify_server.py      # repeatable MCP client smoke test
  tests/
    conftest.py
    test_db.py          # pytest coverage for adapter behavior and errors
requirements.txt
.mcp.json.example
codex-config.example.toml
start_inspector.ps1
```

## Setup

```powershell
python -m pip install -r requirements.txt
python implementation\init_db.py
```

The default database is created at:

```text
implementation/lab.sqlite3
```

You can override it with:

```powershell
$env:SQLITE_LAB_DB_PATH = "D:\path\to\lab.sqlite3"
```

The OpenAI/OpenRouter variables are not required for this lab because the MCP server is database-backed and `ENABLE_LLM_ENRICHMENT=false`.

## Run the Server

The default transport is stdio, which is the expected mode for Claude Code, Codex, Gemini CLI, and MCP Inspector.

```powershell
python implementation\mcp_server.py
```

Optional HTTP/SSE demo transports:

```powershell
python implementation\mcp_server.py --transport http --host 127.0.0.1 --port 8000
python implementation\mcp_server.py --transport sse --host 127.0.0.1 --port 8000
```

## Tool Descriptions

### `search`

Search rows from a validated table with optional selected columns, filters, ordering, limit, and offset.

Example arguments:

```json
{
  "table": "students",
  "filters": {"cohort": "A1"},
  "columns": ["id", "name", "cohort", "score"],
  "limit": 20,
  "offset": 0,
  "order_by": "score",
  "descending": true
}
```

Supported filter operators:

```text
eq, ne, gt, gte, lt, lte, like, in, is_null
```

### `insert`

Insert one row into a validated table and return the inserted payload.

Example arguments:

```json
{
  "table": "students",
  "values": {
    "name": "Minh Hoang",
    "email": "minh.hoang@example.com",
    "cohort": "A1",
    "score": 85.0
  }
}
```

### `aggregate`

Run `count`, `avg`, `sum`, `min`, or `max`, with optional filters and grouping.

Example arguments:

```json
{
  "table": "students",
  "metric": "avg",
  "column": "score",
  "group_by": "cohort"
}
```

## Resources

Read the full schema:

```text
schema://database
```

Read one table schema:

```text
schema://table/students
```

The schema output includes table names, columns, primary key flags, defaults, nullability, and foreign keys.

## Validation and Safety

The database adapter rejects:

- unknown table names
- unknown column names
- unsupported filter operators
- invalid aggregate metrics
- aggregate calls that require a column but omit it
- empty inserts
- invalid pagination values

SQL values are passed through SQLite parameters. Table and column identifiers are accepted only after schema validation and an identifier regex check.

## Verification

Run unit tests:

```powershell
python -m pytest implementation\tests -q
```

Run the end-to-end MCP smoke test:

```powershell
python implementation\verify_server.py
```

The verification script checks:

- tools are discoverable: `search`, `insert`, `aggregate`
- resources are discoverable: `schema://database`, `schema://table/{table_name}`
- a valid `search` call succeeds
- a valid `insert` call succeeds
- a valid grouped `aggregate` call succeeds
- a table schema resource can be read
- an invalid table request is rejected with a clear error

Current local verification:

```text
8 passed
tools: aggregate, insert, search
resources: schema://database, schema://table/{table_name}
invalid request rejected: Error calling tool 'search': unknown table 'missing_table'
```

## MCP Inspector

From PowerShell:

```powershell
.\start_inspector.ps1
```

Manual equivalent:

```powershell
npx -y @modelcontextprotocol/inspector python implementation\mcp_server.py
```

In Inspector, verify:

- all three tools appear with schemas
- `schema://database` appears
- `schema://table/{table_name}` appears as a resource template
- valid calls return rows
- invalid calls return clear errors

## Client Configuration Examples

Use absolute paths in real client configs.

### Claude Code

Copy `.mcp.json.example` to `.mcp.json` and replace the placeholders:

```json
{
  "mcpServers": {
    "sqlite-lab": {
      "type": "stdio",
      "command": "python",
      "args": ["D:/ABSOLUTE/PATH/TO/implementation/mcp_server.py"],
      "env": {}
    }
  }
}
```

Example resource reference:

```text
@sqlite-lab:schema://database
```

### Codex

Example `~/.codex/config.toml`:

```toml
[mcp_servers.sqlite_lab]
command = "python"
args = ["D:/ABSOLUTE/PATH/TO/implementation/mcp_server.py"]
```

### Gemini CLI

Recommended setup:

```powershell
gemini mcp add sqlite-lab (Get-Command python).Source D:\ABSOLUTE\PATH\TO\implementation\mcp_server.py --description "SQLite lab FastMCP server" --timeout 10000
gemini mcp list
```

Smoke prompt:

```powershell
gemini --allowed-mcp-server-names sqlite-lab --yolo -p "Use the sqlite-lab MCP server. Read schema://database, then show the top 2 students by score."
```

## Demo Script

A two-minute demo can follow this order:

1. Run `python implementation\init_db.py`.
2. Run `python implementation\verify_server.py` to show discovery, success calls, schema read, and error handling.
3. Open MCP Inspector with `.\start_inspector.ps1`.
4. Show `search` for cohort `A1`.
5. Show `insert` of a new student.
6. Show `aggregate` average score grouped by `cohort`.
7. Read `schema://table/students`.
8. Call `search` with `missing_table` and show the clear rejection.
