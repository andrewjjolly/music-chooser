from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    release_date TEXT,
    description TEXT,
    genres TEXT NOT NULL DEFAULT '[]',
    metascore INTEGER,
    review_count INTEGER,
    source_url TEXT NOT NULL,
    source_year INTEGER,
    source_page INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_albums_release_date ON albums(release_date);
CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS listening_records (
    album_id INTEGER PRIMARY KEY REFERENCES albums(id) ON DELETE CASCADE,
    state TEXT NOT NULL DEFAULT 'unheard' CHECK(state IN ('unheard', 'listened')),
    sentiment TEXT CHECK(sentiment IN ('liked', 'disliked', 'neutral')),
    rating INTEGER CHECK(rating IS NULL OR (rating BETWEEN 1 AND 5)),
    note TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK(status IN ('in_progress', 'complete')),
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS weekly_set_albums (
    weekly_set_id INTEGER NOT NULL REFERENCES weekly_sets(id) ON DELETE CASCADE,
    album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    bucket_key TEXT NOT NULL,
    position INTEGER NOT NULL,
    accepted_at TEXT NOT NULL,
    PRIMARY KEY(weekly_set_id, album_id),
    UNIQUE(weekly_set_id, position)
);

CREATE TABLE IF NOT EXISTS weekly_rejections (
    weekly_set_id INTEGER NOT NULL REFERENCES weekly_sets(id) ON DELETE CASCADE,
    album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    bucket_key TEXT NOT NULL,
    rejected_at TEXT NOT NULL,
    PRIMARY KEY(weekly_set_id, album_id, bucket_key)
);

CREATE TABLE IF NOT EXISTS fetch_cache (
    url TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    http_status INTEGER,
    etag TEXT,
    last_modified TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source_urls TEXT NOT NULL DEFAULT '[]',
    request_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error_detail TEXT
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize(db_path: Path) -> None:
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(albums)").fetchall()}
        migrations = {
            "description": "ALTER TABLE albums ADD COLUMN description TEXT",
            "source_year": "ALTER TABLE albums ADD COLUMN source_year INTEGER",
            "source_page": "ALTER TABLE albums ADD COLUMN source_page INTEGER",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None
