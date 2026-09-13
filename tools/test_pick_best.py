"""Tests for pick_best's candidate scoring in build_deck.py.

Spotify returns popularity 0 for every track under client credentials, so the old
score was a flat tie between every exact-title hit and the first result won, which
is usually the newest re-release. These tests pin the year-distance tie-break that
replaced it, and the limits of that tie-break.

Usage:
    python tools/test_pick_best.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_deck import pick_best, release_year  # noqa: E402


def track(tid, name, artist, date, popularity=0):
    """A search hit, shaped like the Spotify /v1/search response."""
    return {
        "id": tid,
        "name": name,
        "artists": [{"name": artist}],
        "album": {"release_date": date},
        "popularity": popularity,
    }


def test_release_year_reads_every_date_precision():
    assert release_year(track("a", "x", "y", "2013-11-22")) == 2013
    assert release_year(track("a", "x", "y", "2013")) == 2013
    assert release_year(track("a", "x", "y", "")) is None
    assert release_year({"id": "a", "name": "x"}) is None


def test_seed_year_breaks_the_tie_between_identical_titles():
    """The real regression: a 2026 re-recording beat the 2013 original."""
    items = [
        track("new", "I En Stjerneregn Af Sne", "Mads Langer", "2026-04-10"),
        track("orig", "I En Stjerneregn Af Sne", "Mads Langer", "2013-11-01"),
    ]
    assert pick_best(items, "I En Stjerneregn Af Sne", "Mads Langer", 2013)["id"] == "orig"
    # and the other way round, so this is year distance and not "prefer older"
    assert pick_best(items, "I En Stjerneregn Af Sne", "Mads Langer", 2026)["id"] == "new"


def test_without_a_seed_year_the_first_hit_still_wins():
    items = [
        track("new", "White Christmas", "Bing Crosby", "2019-11-01"),
        track("orig", "White Christmas", "Bing Crosby", "1942-10-01"),
    ]
    assert pick_best(items, "White Christmas", "Bing Crosby")["id"] == "new"


def test_closest_available_reissue_wins_when_no_original_is_on_spotify():
    """Most pre-1960 cards only exist as reissues; take the nearest one."""
    items = [
        track("late", "White Christmas", "Bing Crosby", "2019-11-01"),
        track("early", "White Christmas", "Bing Crosby", "1998-10-06"),
    ]
    assert pick_best(items, "White Christmas", "Bing Crosby", 1942)["id"] == "early"


def test_an_exact_title_outranks_a_closer_edition_of_a_different_title():
    """Year distance orders candidates; it never overturns the title match."""
    items = [
        track("live", "Christmas Time - Live", "Bryan Adams", "1985-12-01"),
        track("studio", "Christmas Time", "Bryan Adams", "2019-11-15"),
    ]
    assert pick_best(items, "Christmas Time", "Bryan Adams", 1985)["id"] == "studio"


def test_the_year_penalty_is_capped():
    items = [
        track("a", "Jingle Bells", "Frank Sinatra", "2017-01-01"),
        track("b", "Jingle Bells", "Frank Sinatra", "1800-01-01"),
    ]
    # Both sit past the cap from a 1957 seed, so the first hit wins rather than the
    # absurdly old one dragging the score arbitrarily far down.
    assert pick_best(items, "Jingle Bells", "Frank Sinatra", 1957)["id"] == "a"


def test_a_wrong_artist_is_still_rejected_outright():
    items = [track("cover", "Last Christmas", "Ariana Grande", "1984-12-01")]
    assert pick_best(items, "Last Christmas", "Wham!", 1984) is None


def test_popularity_still_counts_when_spotify_supplies_it():
    items = [
        track("meh", "Last Christmas", "Wham!", "1984-12-01", popularity=10),
        track("hit", "Last Christmas", "Wham!", "1984-12-01", popularity=90),
    ]
    assert pick_best(items, "Last Christmas", "Wham!", 1984)["id"] == "hit"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"{len(tests)} pick_best tests passed")
