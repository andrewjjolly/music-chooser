from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from music_chooser.metacritic import ReleaseParser


URL = "https://www.metacritic.com/browse/albums/score/metascore/year?sort=desc&year_selected=2026"
REPORT_PATH = Path("reports/2026-page-1-dry-run.json")


def main() -> None:
    response = httpx.get(
        URL,
        headers={"User-Agent": "MusicChooser/0.1 (approved parser dry run)"},
        timeout=30.0,
        follow_redirects=True,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    raw_links = [
        urljoin(URL, link["href"].split("?", 1)[0].split("#", 1)[0])
        for link in soup.select('td.clamp-summary-wrap a.title[href*="/music/"]')
    ]
    albums = ReleaseParser().parse(response.text, URL)

    missing = Counter()
    rows = []
    for album in albums:
        if not album.artist:
            missing["artist"] += 1
        if album.release_date is None:
            missing["release_date"] += 1
        if album.metascore is None:
            missing["metascore"] += 1
        if not album.description:
            missing["description"] += 1
        rows.append(
            {
                "title": album.title,
                "artist": album.artist,
                "release_date": album.release_date.isoformat() if album.release_date else None,
                "metascore": album.metascore,
                "canonical_url": album.canonical_url,
                "description_present": bool(album.description),
            }
        )

    pagination = [
        {"text": link.get_text(" ", strip=True), "url": urljoin(URL, link["href"])}
        for link in soup.select('a[href*="year_selected=2026"]')
        if "page" in link.get("href", "") or link.get_text(" ", strip=True).lower() in {"next", "prev"}
    ]

    report = {
        "url": URL,
        "http_status": response.status_code,
        "response_bytes": len(response.content),
        "raw_album_links": len(raw_links),
        "unique_album_links": len(set(raw_links)),
        "duplicate_album_links": len(raw_links) - len(set(raw_links)),
        "parsed_albums": len(albums),
        "missing_fields": dict(missing),
        "pagination_links": pagination,
        "sample_with_descriptions": [
            {
                "title": album.title,
                "artist": album.artist,
                "release_date": album.release_date.isoformat() if album.release_date else None,
                "metascore": album.metascore,
                "description": album.description,
                "canonical_url": album.canonical_url,
            }
            for album in albums[:3]
        ],
        "albums": rows,
        "database_written": False,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Dry run complete: {len(albums)} albums parsed")
    print(f"Report: {REPORT_PATH.resolve()}")
    print(json.dumps({key: report[key] for key in ("raw_album_links", "unique_album_links", "duplicate_album_links", "parsed_albums", "missing_fields", "pagination_links", "database_written")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
