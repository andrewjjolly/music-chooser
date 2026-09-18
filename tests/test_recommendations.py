from pathlib import Path

from music_chooser.config import Settings
from music_chooser.db import initialize
from music_chooser.dates import Bucket
from music_chooser.recommendations import RecommendationService
from music_chooser.repositories import CatalogRepository


def make_repo(tmp_path: Path):
    path = tmp_path / "test.db"
    initialize(path)
    return CatalogRepository(path)


def test_recommendation_is_score_first_and_excludes_listened(tmp_path):
    repo = make_repo(tmp_path)
    low = repo.upsert_album({"canonical_url":"https://www.metacritic.com/music/low/a","title":"Low","artist":"Artist","release_date":"2025-01-01","genres":["Jazz"],"metascore":70,"source_url":"https://www.metacritic.com/music/low/a"})
    high = repo.upsert_album({"canonical_url":"https://www.metacritic.com/music/high/a","title":"High","artist":"Other","release_date":"2025-01-02","genres":["Rock"],"metascore":90,"source_url":"https://www.metacritic.com/music/high/a"})
    heard = repo.upsert_album({"canonical_url":"https://www.metacritic.com/music/heard/a","title":"Heard","artist":"Loved","release_date":"2025-01-03","genres":["Rock"],"metascore":99,"source_url":"https://www.metacritic.com/music/heard/a"})
    repo.update_listening(heard, "listened", "liked", 5, None)
    weekly_id = repo.create_or_get_week("2026-09-17")
    bucket = Bucket("anytime", "Anytime", None, None)
    result = RecommendationService(repo).recommend(bucket, weekly_id)
    assert result[0]["id"] == high
    assert all(album["id"] != heard for album in result)
