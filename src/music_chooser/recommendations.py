from __future__ import annotations

from collections import defaultdict
from datetime import date

from .dates import Bucket
from .repositories import CatalogRepository


class RecommendationService:
    def __init__(self, repository: CatalogRepository):
        self.repository = repository

    def recommend(self, bucket: Bucket, weekly_set_id: int, limit: int = 1) -> list[dict]:
        albums = self.repository.list_albums(sort="metascore", descending=True)
        accepted = self.repository.accepted_ids(weekly_set_id)
        rejected = self.repository.rejected_ids(weekly_set_id, bucket.key)
        affinity = self._affinity(albums)
        candidates = []
        for album in albums:
            release_date = date.fromisoformat(album["release_date"]) if album.get("release_date") else None
            if album["id"] in accepted or album["id"] in rejected or album.get("listening_state") != "unheard":
                continue
            if not bucket.contains(release_date):
                continue
            artist_score, genre_score = affinity[album["id"]]
            candidates.append((album, artist_score, genre_score))
        candidates.sort(key=lambda item: (
            -(1 if item[0]["metascore"] is not None else 0),
            -(item[0]["metascore"] if item[0]["metascore"] is not None else -1),
            -item[1],
            -item[2],
            item[0]["artist"].casefold(),
            item[0]["title"].casefold(),
        ))
        return [album | {"artist_affinity": artist, "genre_affinity": genre} for album, artist, genre in candidates[:limit]]

    @staticmethod
    def _affinity(albums: list[dict]) -> dict[int, tuple[float, float]]:
        artist_weights: dict[str, list[float]] = defaultdict(list)
        genre_weights: dict[str, list[float]] = defaultdict(list)
        for album in albums:
            if album.get("listening_state") != "listened":
                continue
            rating = album.get("rating")
            sentiment = album.get("sentiment")
            if rating is not None:
                weight = float(rating)
            elif sentiment == "liked":
                weight = 5.0
            elif sentiment == "disliked":
                weight = 1.0
            else:
                continue
            artist_weights[album["artist"].casefold()].append(weight)
            for genre in album.get("genres", []):
                genre_weights[genre.casefold()].append(weight)

        result = {}
        for album in albums:
            artist_values = artist_weights.get(album["artist"].casefold(), [])
            genre_values = [value for genre in album.get("genres", []) for value in genre_weights.get(genre.casefold(), [])]
            result[album["id"]] = (
                sum(artist_values) / len(artist_values) if artist_values else 0.0,
                sum(genre_values) / len(genre_values) if genre_values else 0.0,
            )
        return result
