from datetime import date

from music_chooser.dates import buckets_for, week_key


def test_calendar_buckets_use_previous_complete_periods():
    buckets = {bucket.key: bucket for bucket in buckets_for(date(2026, 9, 17))}
    assert (buckets["last_week"].start, buckets["last_week"].end) == (date(2026, 9, 7), date(2026, 9, 13))
    assert (buckets["last_month"].start, buckets["last_month"].end) == (date(2026, 8, 1), date(2026, 8, 31))
    assert (buckets["last_year"].start, buckets["last_year"].end) == (date(2025, 1, 1), date(2025, 12, 31))
    assert (buckets["last_5_years"].start, buckets["last_5_years"].end) == (date(2021, 1, 1), date(2025, 12, 31))


def test_overlapping_bucket_accepts_a_release_in_both_periods():
    buckets = {bucket.key: bucket for bucket in buckets_for(date(2026, 9, 3))}
    release = date(2026, 8, 28)
    assert buckets["last_week"].contains(release)
    assert buckets["last_month"].contains(release)


def test_week_key_is_stable_throughout_the_week():
    assert week_key(date(2026, 9, 17)) == "2026-09-14"
    assert week_key(date(2026, 9, 20)) == "2026-09-14"
