from music_chooser.config import Settings
from music_chooser.db import initialize
from music_chooser.metacritic import MetacriticClient
from music_chooser.repositories import CatalogRepository
from music_chooser.services import RECENT_RELEASE_URL, SyncService


def test_stale_on_run_skips_a_recent_fetch(tmp_path):
    db_path = tmp_path / "test.db"
    initialize(db_path)
    repository = CatalogRepository(db_path)
    repository.record_fetch(RECENT_RELEASE_URL, 200)
    settings = Settings(db_path=db_path, auto_sync=False)
    client = MetacriticClient(settings, repository)

    result = SyncService(settings, repository, client).sync_recent_if_stale()

    assert result == {"status": "fresh", "request_count": 0, "albums": 0}
    assert client.request_count == 0


def test_upsert_does_not_erase_richer_existing_metadata(tmp_path):
    db_path = tmp_path / "test.db"
    initialize(db_path)
    repository = CatalogRepository(db_path)
    url = "https://www.metacritic.com/music/album/artist"
    album_id = repository.upsert_album({"canonical_url": url, "title": "Album", "artist": "Artist", "release_date": "2025-01-01", "description": "A useful description.", "genres": ["Jazz"], "metascore": 88, "review_count": 12, "source_url": url, "source_year": 2025, "source_page": 1})
    assert repository.upsert_album({"canonical_url": url, "title": "Album", "artist": "Artist", "release_date": None, "genres": [], "metascore": None, "review_count": None, "source_url": url}) == album_id
    result = repository.get_album(album_id)
    assert result["release_date"] == "2025-01-01"
    assert result["description"] == "A useful description."
    assert result["source_year"] == 2025
    assert result["source_page"] == 1
    assert result["metascore"] == 88
    assert result["genres"] == ["Jazz"]
