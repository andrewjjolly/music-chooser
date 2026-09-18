from music_chooser.metacritic import AlbumParser, ReleaseParser, validate_metacritic_url
from music_chooser.historical import discover_pagination_urls, historical_year_url, page_number


def test_album_parser_reads_jsonld_and_score():
    html = '''<html><script type="application/ld+json">{"@type":"MusicAlbum","name":"Test Record","byArtist":{"name":"Test Artist"},"datePublished":"2025-02-14","genre":["Indie"]}</script><main>Metascore: 87 Based on 12 critic reviews</main></html>'''
    album = AlbumParser().parse(html, "https://www.metacritic.com/music/test-record/test-artist")
    assert album.title == "Test Record"
    assert album.artist == "Test Artist"
    assert album.release_date.isoformat() == "2025-02-14"
    assert album.metascore == 87
    assert album.review_count == 12


def test_release_parser_finds_album_links():
    html = '''<table><tr><td class="clamp-summary-wrap"><a class="title" href="/music/test-record/test-artist"><h3>Test Record</h3></a><div class="artist">by Test Artist</div><div class="clamp-details"><span>May 2, 2025</span></div><div class="summary">A concise description.</div><div class="clamp-metascore"><div class="metascore_w">81</div></div></td></tr></table>'''
    albums = ReleaseParser().parse(html, "https://www.metacritic.com/browse/albums/release-date")
    assert len(albums) == 1
    assert albums[0].canonical_url.endswith("/music/test-record/test-artist")
    assert albums[0].artist == "Test Artist"
    assert albums[0].metascore == 81
    assert albums[0].release_date.isoformat() == "2025-05-02"
    assert albums[0].description == "A concise description."


def test_url_validation_rejects_other_hosts():
    assert validate_metacritic_url("https://www.metacritic.com/music/a/b")
    try:
        validate_metacritic_url("https://example.com/music/a/b")
    except ValueError:
        pass
    else:
        raise AssertionError("non-Metacritic URL should be rejected")


def test_historical_pagination_is_discovered_and_normalized():
    url = historical_year_url(2026)
    html = '<a href="?sort=desc&year_selected=2026&page=1">2</a><a href="?sort=desc&year_selected=2026&page=2">3</a><a href="?year_selected=2025&page=1">other year</a>'
    pages = discover_pagination_urls(html, url)
    assert pages == [
        "https://www.metacritic.com/browse/albums/score/metascore/year?sort=desc&year_selected=2026&page=1",
        "https://www.metacritic.com/browse/albums/score/metascore/year?sort=desc&year_selected=2026&page=2",
    ]
    assert page_number(url) == 1
    assert page_number(pages[0]) == 2
