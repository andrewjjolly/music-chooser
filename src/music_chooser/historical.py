from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup


HISTORICAL_URL_TEMPLATE = "https://www.metacritic.com/browse/albums/score/metascore/year?sort=desc&year_selected={year}"


def historical_year_url(year: int) -> str:
    if year < 1900 or year > 2100:
        raise ValueError("year must be between 1900 and 2100")
    return HISTORICAL_URL_TEMPLATE.format(year=year)


def page_number(url: str) -> int:
    value = parse_qs(urlparse(url).query).get("page", ["0"])[0]
    return int(value) + 1 if value.isdigit() else 1


def discover_pagination_urls(html: str, current_url: str) -> list[str]:
    current = urlparse(current_url)
    current_query = parse_qs(current.query)
    selected_year = current_query.get("year_selected", [None])[0]
    discovered: dict[int, str] = {}
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.select("a[href]"):
        candidate = urljoin(current_url, link["href"])
        parsed = urlparse(candidate)
        query = parse_qs(parsed.query)
        page = query.get("page", [None])[0]
        if parsed.path != current.path or query.get("year_selected", [None])[0] != selected_year or not page or not page.isdigit():
            continue
        if page == "0":
            continue
        normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))
        discovered[int(page)] = normalized
    return [discovered[key] for key in sorted(discovered)]


def historical_years(start_year: int, end_year: int) -> Iterable[int]:
    if start_year > end_year:
        raise ValueError("start_year must not be greater than end_year")
    return range(start_year, end_year + 1)
