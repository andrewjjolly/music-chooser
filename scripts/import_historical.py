from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from music_chooser.config import Settings
from music_chooser.db import initialize
from music_chooser.historical import discover_pagination_urls, historical_year_url, historical_years, page_number
from music_chooser.metacritic import MetacriticClient, ReleaseParser
from music_chooser.repositories import CatalogRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Import approved historical Metacritic listing pages into the local database.")
    parser.add_argument("--start-year", type=int, default=1999)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--db", type=Path, default=Path(".music-chooser/music-chooser.db"))
    args = parser.parse_args()

    initialize(args.db)
    settings = Settings(db_path=args.db, request_delay_seconds=args.delay, auto_sync=False)
    repository = CatalogRepository(args.db)
    client = MetacriticClient(settings, repository)
    release_parser = ReleaseParser()
    queue = [historical_year_url(year) for year in historical_years(args.start_year, args.end_year)]
    queued = set(queue)
    visited: set[str] = set()
    page_counts: defaultdict[str, int] = defaultdict(int)
    album_count = 0
    errors: list[str] = []
    sync_id = repository.start_sync(queue.copy())

    try:
        while queue:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            print(f"Importing page {page_number(url)}: {url}", flush=True)
            try:
                html = client.fetch(url, force=True)
                year = int(url.split("year_selected=", 1)[1].split("&", 1)[0])
                page_counts[str(year)] += 1
                for album in release_parser.parse(html, url):
                    repository.upsert_album({
                        "canonical_url": album.canonical_url,
                        "title": album.title,
                        "artist": album.artist,
                        "release_date": album.release_date,
                        "description": album.description,
                        "genres": album.genres,
                        "metascore": album.metascore,
                        "review_count": album.review_count,
                        "source_url": album.source_url,
                        "source_year": year,
                        "source_page": page_number(url),
                    })
                    album_count += 1
                for next_url in discover_pagination_urls(html, url):
                    if next_url not in queued:
                        queued.add(next_url)
                        queue.append(next_url)
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                print(f"  ERROR: {exc}", flush=True)

        status = "partial" if errors and album_count else "failed" if errors else "complete"
        repository.finish_sync(sync_id, client.request_count, status, "\n".join(errors) or None)
        print(f"Imported {album_count} parsed album rows across {len(visited)} pages.")
        print(f"Unique pages: {len(visited)}; request count: {client.request_count}; errors: {len(errors)}")
        print(f"Pages by year: {dict(sorted(page_counts.items()))}")
        if errors:
            print("Errors:")
            print("\n".join(errors))
        if errors:
            raise SystemExit(1)
    except KeyboardInterrupt:
        repository.finish_sync(sync_id, client.request_count, "failed", "Import interrupted")
        raise


if __name__ == "__main__":
    main()
