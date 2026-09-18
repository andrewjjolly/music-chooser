from __future__ import annotations

from datetime import datetime

from .config import Settings
from .metacritic import AlbumParser, MetacriticClient, ReleaseParser, validate_metacritic_url
from .repositories import CatalogRepository


RECENT_RELEASE_URL = "https://www.metacritic.com/browse/albums/release-date"


class SyncService:
    def __init__(self, settings: Settings, repository: CatalogRepository, client: MetacriticClient | None = None):
        self.settings = settings
        self.repository = repository
        self.client = client or MetacriticClient(settings, repository)
        self.release_parser = ReleaseParser()
        self.album_parser = AlbumParser()

    def sync_recent_if_stale(self, force: bool = False) -> dict:
        cached = self.repository.latest_fetch(RECENT_RELEASE_URL)
        if cached and not force:
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            if (datetime.now(fetched_at.tzinfo) - fetched_at).total_seconds() < self.settings.refresh_hours * 3600:
                return {"status": "fresh", "request_count": 0, "albums": 0}
        return self.import_urls([RECENT_RELEASE_URL], force=force)

    def import_urls(self, urls: list[str], force: bool = False) -> dict:
        clean_urls = [validate_metacritic_url(url) for url in urls if url.strip()]
        sync_id = self.repository.start_sync(clean_urls)
        starting_request_count = self.client.request_count
        imported = 0
        errors: list[str] = []
        try:
            for url in clean_urls:
                try:
                    html = self.client.fetch(url, force=force)
                    if "/music/" in url and "/browse/" not in url:
                        parsed = [self.album_parser.parse(html, url)]
                    else:
                        parsed = self.release_parser.parse(html, url)
                    for album in parsed:
                        self.repository.upsert_album({
                            "canonical_url": album.canonical_url,
                            "title": album.title,
                            "artist": album.artist,
                            "release_date": album.release_date,
                            "description": album.description,
                            "genres": album.genres,
                            "metascore": album.metascore,
                            "review_count": album.review_count,
                            "source_url": album.source_url,
                        })
                        imported += 1
                except Exception as exc:  # keep a multi-URL import resumable
                    errors.append(f"{url}: {exc}")
            status = "partial" if errors and imported else "failed" if errors else "complete"
            request_count = self.client.request_count - starting_request_count
            self.repository.finish_sync(sync_id, request_count, status, "\n".join(errors) or None)
            return {"status": status, "request_count": request_count, "albums": imported, "errors": errors}
        except Exception as exc:
            request_count = self.client.request_count - starting_request_count
            self.repository.finish_sync(sync_id, request_count, "failed", str(exc))
            raise
