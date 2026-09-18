from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Iterable

from .db import connect, row_dict


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode_genres(genres: Iterable[str]) -> str:
    return json.dumps(sorted({g.strip() for g in genres if g and g.strip()}), ensure_ascii=False)


def decode_genres(value: str | None) -> list[str]:
    try:
        result = json.loads(value or "[]")
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        return []


class CatalogRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def upsert_album(self, album: dict[str, Any]) -> int:
        now = utc_now()
        release_date = album.get("release_date")
        if isinstance(release_date, date):
            release_date = release_date.isoformat()
        with connect(self.db_path) as db:
            existing = db.execute("SELECT id FROM albums WHERE canonical_url = ?", (album["canonical_url"],)).fetchone()
            if existing:
                db.execute(
                    """UPDATE albums SET
                    title=COALESCE(NULLIF(?, ''), title),
                    artist=COALESCE(NULLIF(?, ''), artist),
                    release_date=COALESCE(?, release_date),
                    description=COALESCE(NULLIF(?, ''), description),
                    genres=CASE WHEN ? = '[]' THEN genres ELSE ? END,
                    metascore=COALESCE(?, metascore),
                    review_count=COALESCE(?, review_count),
                    source_url=?,
                    source_year=COALESCE(?, source_year),
                    source_page=COALESCE(?, source_page),
                    last_seen_at=? WHERE id=?""",
                    (album.get("title", ""), album.get("artist", ""), release_date, album.get("description", ""), encode_genres(album.get("genres", [])), encode_genres(album.get("genres", [])), album.get("metascore"), album.get("review_count"), album.get("source_url", album["canonical_url"]), album.get("source_year"), album.get("source_page"), now, existing["id"]),
                )
                return int(existing["id"])
            cursor = db.execute(
                """INSERT INTO albums(canonical_url,title,artist,release_date,description,genres,metascore,review_count,source_url,source_year,source_page,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (album["canonical_url"], album["title"], album["artist"], release_date, album.get("description"), encode_genres(album.get("genres", [])), album.get("metascore"), album.get("review_count"), album.get("source_url", album["canonical_url"]), album.get("source_year"), album.get("source_page"), now, now),
            )
            return int(cursor.lastrowid)

    def list_albums(self, search: str = "", sort: str = "release_date", descending: bool = True) -> list[dict[str, Any]]:
        allowed = {"release_date", "metascore", "artist", "title", "last_seen_at"}
        order = sort if sort in allowed else "release_date"
        direction = "DESC" if descending else "ASC"
        query = """SELECT a.*, COALESCE(l.state, 'unheard') AS listening_state, l.sentiment, l.rating, l.note FROM albums a LEFT JOIN listening_records l ON l.album_id=a.id"""
        params: list[Any] = []
        if search.strip():
            query += " WHERE a.title LIKE ? OR a.artist LIKE ? OR a.genres LIKE ?"
            needle = f"%{search.strip()}%"
            params.extend([needle, needle, needle])
        query += f" ORDER BY a.{order} {direction}, a.artist COLLATE NOCASE ASC, a.title COLLATE NOCASE ASC"
        with connect(self.db_path) as db:
            rows = db.execute(query, params).fetchall()
        return [self._hydrate(row) for row in rows]

    def get_album(self, album_id: int) -> dict[str, Any] | None:
        with connect(self.db_path) as db:
            row = db.execute("SELECT a.*, COALESCE(l.state, 'unheard') AS listening_state, l.sentiment, l.rating, l.note FROM albums a LEFT JOIN listening_records l ON l.album_id=a.id WHERE a.id=?", (album_id,)).fetchone()
        return self._hydrate(row) if row else None

    def _hydrate(self, row) -> dict[str, Any]:
        result = row_dict(row) or {}
        result["genres"] = decode_genres(result.get("genres"))
        return result

    def update_listening(self, album_id: int, state: str, sentiment: str | None, rating: int | None, note: str | None) -> None:
        if state not in {"unheard", "listened"}:
            raise ValueError("Invalid listening state")
        if sentiment not in {None, "liked", "disliked", "neutral"}:
            raise ValueError("Invalid sentiment")
        if rating is not None and rating not in range(1, 6):
            raise ValueError("Rating must be between 1 and 5")
        with connect(self.db_path) as db:
            db.execute(
                """INSERT INTO listening_records(album_id,state,sentiment,rating,note,updated_at) VALUES(?,?,?,?,?,?)
                ON CONFLICT(album_id) DO UPDATE SET state=excluded.state,sentiment=excluded.sentiment,rating=excluded.rating,note=excluded.note,updated_at=excluded.updated_at""",
                (album_id, state, sentiment, rating, note, utc_now()),
            )

    def latest_fetch(self, url: str) -> dict[str, Any] | None:
        with connect(self.db_path) as db:
            return row_dict(db.execute("SELECT * FROM fetch_cache WHERE url=?", (url,)).fetchone())

    def record_fetch(self, url: str, status: int | None, etag: str | None = None, last_modified: str | None = None, error: str | None = None) -> None:
        with connect(self.db_path) as db:
            db.execute(
                """INSERT INTO fetch_cache(url,fetched_at,http_status,etag,last_modified,last_error) VALUES(?,?,?,?,?,?)
                ON CONFLICT(url) DO UPDATE SET fetched_at=excluded.fetched_at,http_status=excluded.http_status,etag=excluded.etag,last_modified=excluded.last_modified,last_error=excluded.last_error""",
                (url, utc_now(), status, etag, last_modified, error),
            )

    def create_or_get_week(self, week_key: str) -> int:
        with connect(self.db_path) as db:
            db.execute("INSERT OR IGNORE INTO weekly_sets(week_key,created_at,status) VALUES(?,?, 'in_progress')", (week_key, utc_now()))
            return int(db.execute("SELECT id FROM weekly_sets WHERE week_key=?", (week_key,)).fetchone()["id"])

    def weekly_set(self, week_key: str) -> dict[str, Any] | None:
        with connect(self.db_path) as db:
            week = row_dict(db.execute("SELECT * FROM weekly_sets WHERE week_key=?", (week_key,)).fetchone())
            if not week:
                return None
            albums = db.execute("""SELECT w.bucket_key,w.position,w.accepted_at,a.*,COALESCE(l.state,'unheard') AS listening_state,l.sentiment,l.rating FROM weekly_set_albums w JOIN albums a ON a.id=w.album_id LEFT JOIN listening_records l ON l.album_id=a.id WHERE w.weekly_set_id=? ORDER BY w.position""", (week["id"],)).fetchall()
            week["albums"] = [self._hydrate(row) | {"bucket_key": row["bucket_key"], "position": row["position"]} for row in albums]
            return week

    def accepted_ids(self, weekly_set_id: int) -> set[int]:
        with connect(self.db_path) as db:
            return {int(row["album_id"]) for row in db.execute("SELECT album_id FROM weekly_set_albums WHERE weekly_set_id=?", (weekly_set_id,)).fetchall()}

    def rejected_ids(self, weekly_set_id: int, bucket_key: str) -> set[int]:
        with connect(self.db_path) as db:
            return {int(row["album_id"]) for row in db.execute("SELECT album_id FROM weekly_rejections WHERE weekly_set_id=? AND bucket_key=?", (weekly_set_id, bucket_key)).fetchall()}

    def accept_album(self, weekly_set_id: int, album_id: int, bucket_key: str, position: int) -> None:
        if position not in range(1, 6):
            raise ValueError("A weekly set can contain exactly five positions")
        with connect(self.db_path) as db:
            db.execute("INSERT INTO weekly_set_albums(weekly_set_id,album_id,bucket_key,position,accepted_at) VALUES(?,?,?,?,?)", (weekly_set_id, album_id, bucket_key, position, utc_now()))
            if position == 5:
                db.execute("UPDATE weekly_sets SET status='complete', completed_at=? WHERE id=?", (utc_now(), weekly_set_id))

    def reject_album(self, weekly_set_id: int, album_id: int, bucket_key: str) -> None:
        with connect(self.db_path) as db:
            db.execute("INSERT OR IGNORE INTO weekly_rejections(weekly_set_id,album_id,bucket_key,rejected_at) VALUES(?,?,?,?)", (weekly_set_id, album_id, bucket_key, utc_now()))

    def latest_sync(self) -> dict[str, Any] | None:
        with connect(self.db_path) as db:
            return row_dict(db.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone())

    def start_sync(self, urls: list[str]) -> int:
        with connect(self.db_path) as db:
            cursor = db.execute("INSERT INTO sync_runs(started_at,source_urls,status) VALUES(?,?,?)", (utc_now(), json.dumps(urls), "running"))
            return int(cursor.lastrowid)

    def finish_sync(self, sync_id: int, request_count: int, status: str, error_detail: str | None = None) -> None:
        with connect(self.db_path) as db:
            db.execute("UPDATE sync_runs SET finished_at=?,request_count=?,status=?,error_detail=? WHERE id=?", (utc_now(), request_count, status, error_detail, sync_id))
