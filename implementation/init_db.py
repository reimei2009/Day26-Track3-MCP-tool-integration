from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "lab.sqlite3"

SCHEMA_SQL = """
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;

CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    cohort TEXT NOT NULL,
    score REAL NOT NULL CHECK (score >= 0 AND score <= 100),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    credits INTEGER NOT NULL CHECK (credits > 0)
);

CREATE TABLE enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'dropped')),
    grade REAL CHECK (grade IS NULL OR (grade >= 0 AND grade <= 100)),
    enrolled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);
"""

SEED_SQL = """
INSERT INTO students (name, email, cohort, score) VALUES
    ('An Nguyen', 'an.nguyen@example.com', 'A1', 88.5),
    ('Binh Tran', 'binh.tran@example.com', 'A1', 91.0),
    ('Chi Le', 'chi.le@example.com', 'B2', 76.0),
    ('Dung Pham', 'dung.pham@example.com', 'B2', 82.5),
    ('Ha Vo', 'ha.vo@example.com', 'C3', 94.0);

INSERT INTO courses (code, title, credits) VALUES
    ('AI101', 'Applied AI Foundations', 3),
    ('MCP201', 'MCP Tool Integration', 4),
    ('DB150', 'Practical Databases', 3);

INSERT INTO enrollments (student_id, course_id, status, grade) VALUES
    (1, 1, 'completed', 87.0),
    (1, 2, 'active', NULL),
    (2, 2, 'completed', 92.0),
    (3, 1, 'completed', 75.0),
    (4, 3, 'active', NULL),
    (5, 2, 'completed', 96.0);
"""


def create_database(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_SQL)
        conn.executescript(SEED_SQL)
        conn.commit()
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the Day 26 SQLite lab database.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    args = parser.parse_args()
    path = create_database(args.db_path)
    print(f"Database created at {path}")


if __name__ == "__main__":
    main()
