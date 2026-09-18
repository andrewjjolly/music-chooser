from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .config import Settings
from .repositories import CatalogRepository


METACRITIC_HOSTS = {"www.metacritic.com", "metacritic.com"}


class MetacriticError(RuntimeError):
    pass


def validate_metacritic_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() not in METACRITIC_HOSTS:
        raise ValueError("Only https://www.metacritic.com URLs are accepted")
    return url.strip().split("#", 1)[0]


def _json_values(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _json_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_values(child)


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\b(\d{1,3})\b", str(value))
    if not match:
        return None
    number = int(match.group(1))
    return number if 0 <= number <= 100 else None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value)
    numeric = re.search(r"\b(\d{4})[-/]?(\d{2})[-/]?(\d{2})\b", text)
    if numeric:
        try:
            return date(int(numeric.group(1)), int(numeric.group(2)), int(numeric.group(3)))
        except ValueError:
            return None
    named = re.search(r"\b[A-Za-z]+\s+\d{1,2},?\s+\d{4}\b", text)
    if not named:
        return None
    for pattern in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(named.group(0).replace(",", ""), pattern).date()
        except ValueError:
            continue
    return None


def _text(soup: BeautifulSoup) -> str:
    return " ".join(soup.stripped_strings)


@dataclass
class ParsedAlbum:
    canonical_url: str
    title: str
    artist: str
    release_date: date | None
    genres: list[str]
    metascore: int | None
    review_count: int | None
    source_url: str
    description: str | None = None


class ReleaseParser:
    def parse(self, html: str, source_url: str) -> list[ParsedAlbum]:
        soup = BeautifulSoup(html, "html.parser")
        parsed: dict[str, ParsedAlbum] = {}
        links = soup.select('td.clamp-summary-wrap a.title[href*="/music/"]')
        links = links or soup.select('a[href*="/music/"]')
        for link in links:
            href = link.get("href", "").split("?", 1)[0].split("#", 1)[0]
            if not href.startswith("/music/") or href.rstrip("/").count("/") < 2:
                continue
            canonical = f"https://www.metacritic.com{href}" if href.startswith("/") else href
            container = link.find_parent("td", class_="clamp-summary-wrap") or link.find_parent(["article", "li", "div"]) or link.parent
            text = _text(container)
            title_node = link.find(["h2", "h3"])
            title = title_node.get_text(" ", strip=True) if title_node else link.get_text(" ", strip=True)
            if not title or title.lower() in {"read more", "details"}:
                continue
            artist_node = container.select_one(".artist") if hasattr(container, "select_one") else None
            details_node = container.select_one(".clamp-details") if hasattr(container, "select_one") else None
            description_node = container.select_one(".summary") if hasattr(container, "select_one") else None
            score_node = container.select_one(".clamp-metascore .metascore_w") if hasattr(container, "select_one") else None
            artist = artist_node.get_text(" ", strip=True) if artist_node else self._artist_from_text(text, title)
            artist = re.sub(r"^by\s+", "", artist, flags=re.I).strip()
            details = details_node.get_text(" ", strip=True) if details_node else text
            description = description_node.get_text(" ", strip=True) if description_node else None
            score_text = score_node.get_text(" ", strip=True) if score_node else ""
            score_match = re.search(r"(?:Metascore|Score)\s*:?\s*(\d{1,3})", text, re.I)
            metascore = _parse_int(score_text) if score_text else (_parse_int(score_match.group(1)) if score_match else None)
            parsed[canonical] = ParsedAlbum(canonical, title, artist, _parse_date(details), [], metascore, self._review_count(text), source_url, description)
        return list(parsed.values())

    @staticmethod
    def _artist_from_text(text: str, title: str) -> str:
        cleaned = text.replace(title, "", 1).strip(" |–—-:")
        date_match = re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}", cleaned, re.I)
        if date_match:
            cleaned = cleaned[:date_match.start()]
        return cleaned.split("|")[0].strip() or "Unknown artist"

    @staticmethod
    def _review_count(text: str) -> int | None:
        match = re.search(r"Based on\s+(\d+)\s+critic", text, re.I)
        return int(match.group(1)) if match else None


class AlbumParser:
    def parse(self, html: str, source_url: str) -> ParsedAlbum:
        soup = BeautifulSoup(html, "html.parser")
        title = artist = None
        release_date = None
        genres: list[str] = []
        metascore = review_count = None
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                value = json.loads(script.string or script.get_text())
            except (json.JSONDecodeError, TypeError):
                continue
            for item in _json_values(value):
                if not title and item.get("name") and item.get("@type") in {"MusicAlbum", "Album", "Product"}:
                    title = str(item["name"])
                if not artist and isinstance(item.get("byArtist"), dict):
                    artist = item["byArtist"].get("name")
                release_date = release_date or _parse_date(item.get("datePublished") or item.get("releaseDate"))
                if isinstance(item.get("genre"), list):
                    genres.extend(str(g) for g in item["genre"])
                elif item.get("genre"):
                    genres.append(str(item["genre"]))

        text = _text(soup)
        title = title or (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "Unknown album")
        artist = artist or self._artist_from_url(source_url) or "Unknown artist"
        score_match = re.search(r"(?:Metascore|Metascore:|critic score)\s*:?\s*(\d{1,3})", text, re.I)
        metascore = _parse_int(score_match.group(1)) if score_match else None
        review_match = re.search(r"Based on\s+(\d+)\s+critic", text, re.I)
        review_count = int(review_match.group(1)) if review_match else None
        release_date = release_date or _parse_date(text)
        return ParsedAlbum(validate_metacritic_url(source_url), title, artist, release_date, sorted(set(genres)), metascore, review_count, source_url)

    @staticmethod
    def _artist_from_url(url: str) -> str | None:
        parts = [p for p in urlparse(url).path.split("/") if p]
        return parts[-1].replace("-", " ").title() if len(parts) >= 3 else None


class MetacriticClient:
    def __init__(self, settings: Settings, repository: CatalogRepository):
        self.settings = settings
        self.repository = repository
        self.memory_cache: dict[str, str] = {}
        self.last_request_at = 0.0
        self.request_count = 0

    def fetch(self, url: str, force: bool = False) -> str:
        url = validate_metacritic_url(url)
        if url in self.memory_cache:
            return self.memory_cache[url]
        cached = self.repository.latest_fetch(url)
        if cached and not force:
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            age_seconds = (datetime.now(fetched_at.tzinfo) - fetched_at).total_seconds()
            if age_seconds < self.settings.refresh_hours * 3600:
                raise MetacriticError(f"URL was fetched recently; wait before refreshing: {url}")
        wait = self.settings.request_delay_seconds - (time.monotonic() - self.last_request_at)
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": self.settings.user_agent, "Accept": "text/html,application/xhtml+xml"}
        last_error = None
        for attempt in range(3):
            try:
                response = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
                self.request_count += 1
                self.last_request_at = time.monotonic()
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise httpx.HTTPStatusError("temporary HTTP status", request=response.request, response=response)
                response.raise_for_status()
                self.repository.record_fetch(url, response.status_code, response.headers.get("etag"), response.headers.get("last-modified"))
                self.memory_cache[url] = response.text
                return response.text
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                self.repository.record_fetch(url, getattr(getattr(exc, "response", None), "status_code", None), error=str(exc))
                if attempt < 2:
                    time.sleep(2**attempt)
        raise MetacriticError(f"Could not fetch {url}: {last_error}")
