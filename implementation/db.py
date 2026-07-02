from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    """Raised when a request cannot be safely executed."""


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SUPPORTED_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "like", "in", "is_null"}
SUPPORTED_METRICS = {"count", "avg", "sum", "min", "max"}


class SQLiteAdapter:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def list_tables(self) -> list[str]:
        with closing(self.connect()) as conn:
            rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        return [row["name"] for row in rows]

    def database_schema(self) -> dict[str, Any]:
        return {"tables": {table: self.get_table_schema(table) for table in self.list_tables()}}

    def get_table_schema(self, table: str) -> dict[str, Any]:
        table = self._validate_table(table)
        with closing(self.connect()) as conn:
            column_rows = conn.execute(f"PRAGMA table_info({self._quote_identifier(table)})").fetchall()
            fk_rows = conn.execute(f"PRAGMA foreign_key_list({self._quote_identifier(table)})").fetchall()

        columns = [
            {
                "name": row["name"],
                "type": row["type"],
                "not_null": bool(row["notnull"]),
                "default": row["dflt_value"],
                "primary_key": bool(row["pk"]),
            }
            for row in column_rows
        ]
        foreign_keys = [
            {
                "column": row["from"],
                "references_table": row["table"],
                "references_column": row["to"],
            }
            for row in fk_rows
        ]
        return {"name": table, "columns": columns, "foreign_keys": foreign_keys}

    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: list[dict[str, Any]] | dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        table = self._validate_table(table)
        table_columns = self._column_names(table)
        selected_columns = self._validate_columns(table, columns or table_columns)
        where_sql, params = self._build_where_clause(table, filters)
        limit, offset = self._validate_pagination(limit, offset)

        sql = f"SELECT {self._join_identifiers(selected_columns)} FROM {self._quote_identifier(table)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if order_by is not None:
            self._validate_column(table, order_by)
            direction = "DESC" if descending else "ASC"
            sql += f" ORDER BY {self._quote_identifier(order_by)} {direction}"
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with closing(self.connect()) as conn:
            rows = conn.execute(sql, params).fetchall()

        return {
            "table": table,
            "columns": selected_columns,
            "limit": limit,
            "offset": offset,
            "count": len(rows),
            "rows": [dict(row) for row in rows],
        }

    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        table = self._validate_table(table)
        if not isinstance(values, dict) or not values:
            raise ValidationError("insert values must be a non-empty object")

        for column in values:
            self._validate_column(table, column)

        columns = list(values.keys())
        placeholders = ", ".join("?" for _ in columns)
        sql = (
            f"INSERT INTO {self._quote_identifier(table)} "
            f"({self._join_identifiers(columns)}) VALUES ({placeholders})"
        )

        try:
            with closing(self.connect()) as conn:
                cursor = conn.execute(sql, [values[column] for column in columns])
                conn.commit()
                rowid = cursor.lastrowid
                row = conn.execute(
                    f"SELECT * FROM {self._quote_identifier(table)} WHERE rowid = ?",
                    [rowid],
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"insert failed integrity check: {exc}") from exc

        return {
            "table": table,
            "inserted_id": rowid,
            "values": dict(row) if row is not None else dict(values),
        }

    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: list[dict[str, Any]] | dict[str, Any] | None = None,
        group_by: str | list[str] | None = None,
    ) -> dict[str, Any]:
        table = self._validate_table(table)
        metric = metric.lower()
        if metric not in SUPPORTED_METRICS:
            raise ValidationError(f"unsupported aggregate metric '{metric}'")

        if metric == "count" and column is None:
            metric_expr = "COUNT(*)"
        else:
            if column is None:
                raise ValidationError(f"aggregate metric '{metric}' requires a column")
            self._validate_column(table, column)
            metric_expr = f"{metric.upper()}({self._quote_identifier(column)})"

        group_columns = self._normalize_group_by(table, group_by)
        select_parts = [self._quote_identifier(column_name) for column_name in group_columns]
        select_parts.append(f"{metric_expr} AS value")
        where_sql, params = self._build_where_clause(table, filters)

        sql = f"SELECT {', '.join(select_parts)} FROM {self._quote_identifier(table)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if group_columns:
            sql += f" GROUP BY {self._join_identifiers(group_columns)}"
            sql += f" ORDER BY {self._join_identifiers(group_columns)}"

        with closing(self.connect()) as conn:
            rows = conn.execute(sql, params).fetchall()

        return {
            "table": table,
            "metric": metric,
            "column": column,
            "group_by": group_columns,
            "rows": [dict(row) for row in rows],
        }

    def _validate_table(self, table: str) -> str:
        if not isinstance(table, str) or not IDENTIFIER_RE.match(table):
            raise ValidationError(f"invalid table name '{table}'")
        if table not in self.list_tables():
            raise ValidationError(f"unknown table '{table}'")
        return table

    def _column_names(self, table: str) -> list[str]:
        schema = self.get_table_schema(table)
        return [column["name"] for column in schema["columns"]]

    def _validate_columns(self, table: str, columns: list[str]) -> list[str]:
        if not columns:
            raise ValidationError("at least one column must be selected")
        return [self._validate_column(table, column) for column in columns]

    def _validate_column(self, table: str, column: str) -> str:
        if not isinstance(column, str) or not IDENTIFIER_RE.match(column):
            raise ValidationError(f"invalid column name '{column}'")
        if column not in self._column_names(table):
            raise ValidationError(f"unknown column '{column}' for table '{table}'")
        return column

    def _normalize_filters(
        self, filters: list[dict[str, Any]] | dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        if filters is None:
            return []
        if isinstance(filters, dict):
            return [{"column": column, "op": "eq", "value": value} for column, value in filters.items()]
        if not isinstance(filters, list):
            raise ValidationError("filters must be an object or a list of filter objects")
        return filters

    def _build_where_clause(
        self, table: str, filters: list[dict[str, Any]] | dict[str, Any] | None
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        for item in self._normalize_filters(filters):
            if not isinstance(item, dict):
                raise ValidationError("each filter must be an object")
            column = self._validate_column(table, item.get("column"))
            op = item.get("op", "eq")
            if not isinstance(op, str):
                raise ValidationError("filter operator must be a string")
            op = op.lower()
            if op not in SUPPORTED_OPERATORS:
                raise ValidationError(f"unsupported filter operator '{op}'")

            quoted_column = self._quote_identifier(column)
            value = item.get("value")
            if op == "eq":
                clauses.append(f"{quoted_column} = ?")
                params.append(value)
            elif op == "ne":
                clauses.append(f"{quoted_column} != ?")
                params.append(value)
            elif op == "gt":
                clauses.append(f"{quoted_column} > ?")
                params.append(value)
            elif op == "gte":
                clauses.append(f"{quoted_column} >= ?")
                params.append(value)
            elif op == "lt":
                clauses.append(f"{quoted_column} < ?")
                params.append(value)
            elif op == "lte":
                clauses.append(f"{quoted_column} <= ?")
                params.append(value)
            elif op == "like":
                clauses.append(f"{quoted_column} LIKE ?")
                params.append(value)
            elif op == "in":
                if not isinstance(value, list) or not value:
                    raise ValidationError("operator 'in' requires a non-empty list value")
                clauses.append(f"{quoted_column} IN ({', '.join('?' for _ in value)})")
                params.extend(value)
            elif op == "is_null":
                clauses.append(f"{quoted_column} IS {'NOT ' if value is False else ''}NULL")

        return " AND ".join(clauses), params

    def _normalize_group_by(self, table: str, group_by: str | list[str] | None) -> list[str]:
        if group_by is None:
            return []
        group_columns = [group_by] if isinstance(group_by, str) else group_by
        if not isinstance(group_columns, list):
            raise ValidationError("group_by must be a string or list of strings")
        return self._validate_columns(table, group_columns)

    def _validate_pagination(self, limit: int, offset: int) -> tuple[int, int]:
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            raise ValidationError("limit must be an integer between 1 and 100")
        if not isinstance(offset, int) or offset < 0:
            raise ValidationError("offset must be a non-negative integer")
        return limit, offset

    def _quote_identifier(self, identifier: str) -> str:
        if not isinstance(identifier, str) or not IDENTIFIER_RE.match(identifier):
            raise ValidationError(f"invalid SQL identifier '{identifier}'")
        return f'"{identifier}"'

    def _join_identifiers(self, identifiers: list[str]) -> str:
        return ", ".join(self._quote_identifier(identifier) for identifier in identifiers)
