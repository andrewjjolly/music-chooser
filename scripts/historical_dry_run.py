from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

from music_chooser.historical import discover_pagination_urls, historical_year_url, historical_years, page_number
from music_chooser.metacritic import ReleaseParser


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch historical Metacritic listing pages without writing to the database.")
    parser.add_argument("--start-year", type=int, default=1999)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", type=Path, default=Path("reports/historical-dry-run.json"))
    args = parser.parse_args()

    release_parser = ReleaseParser()
    queue = [historical_year_url(year) for year in historical_years(args.start_year, args.end_year)]
    queued = set(queue)
    visited: set[str] = set()
    albums: dict[str, object] = {}
    pages_by_year: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    errors: list[dict[str, str]] = []
    missing = Counter()
    last_request_at = 0.0

    with httpx.Client(headers={"User-Agent": "MusicChooser/0.1 (approved historical dry run)"}, timeout=args.timeout, follow_redirects=True) as client:
        while queue:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            wait = args.delay - (time.monotonic() - last_request_at)
            if wait > 0:
                time.sleep(wait)
            print(f"Fetching year page {page_number(url)}: {url}", flush=True)
            try:
                response = client.get(url)
                last_request_at = time.monotonic()
                response.raise_for_status()
                parsed = release_parser.parse(response.text, url)
                query_year = url.split("year_selected=", 1)[1].split("&", 1)[0]
                pages_by_year[query_year].append({"page": page_number(url), "url": url, "albums": len(parsed)})
                for album in parsed:
                    albums[album.canonical_url] = album
                    if not album.artist:
                        missing["artist"] += 1
                    if album.release_date is None:
                        missing["release_date"] += 1
                    if album.metascore is None:
                        missing["metascore"] += 1
                    if not album.description:
                        missing["description"] += 1
                for next_url in discover_pagination_urls(response.text, url):
                    if next_url not in queued:
                        queued.add(next_url)
                        queue.append(next_url)
            except Exception as exc:
                errors.append({"url": url, "error": str(exc)})

    report = {
        "start_year": args.start_year,
        "end_year": args.end_year,
        "request_delay_seconds": args.delay,
        "request_timeout_seconds": args.timeout,
        "request_count": len(visited),
        "page_count": len(visited),
        "unique_albums": len(albums),
        "missing_fields": dict(missing),
        "errors": errors,
        "pages_by_year": {year: sorted(pages, key=lambda item: int(item["page"])) for year, pages in sorted(pages_by_year.items())},
        "database_written": False,
        "sample": [
            {
                "title": album.title,
                "artist": album.artist,
                "release_date": album.release_date.isoformat() if album.release_date else None,
                "metascore": album.metascore,
                "description_present": bool(album.description),
                "canonical_url": album.canonical_url,
            }
            for album in list(albums.values())[:10]
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("request_count", "unique_albums", "missing_fields", "errors", "database_written")}, indent=2, ensure_ascii=False))
    print(f"Report: {args.output.resolve()}")


if __name__ == "__main__":
    main()
