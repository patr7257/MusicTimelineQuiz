"""Tests for the replace-or-keep decision in repick_versions.py.

The decision is the whole risk in that script: it rewrites cards nobody re-checks by
ear, so it must only ever move a card CLOSER to its seed year, and must refuse to
act on missing metadata.

Usage:
    python tools/test_repick_versions.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from repick_versions import should_replace  # noqa: E402


def test_replaces_when_the_new_track_is_closer():
    # the real case: seeded 2013, holding a 2026 re-recording, offered the 2013 single
    assert should_replace(2013, 2026, 2013) is True
    assert should_replace(1942, 2019, 1998) is True


def test_keeps_when_the_new_track_is_further_or_equal():
    assert should_replace(2013, 2013, 2026) is False
    assert should_replace(1984, 1984, 1984) is False
    assert should_replace(1970, 2007, 2007) is False


def test_distance_is_symmetric_not_just_older_wins():
    # an earlier release is not automatically better: 1998 is further from 2004 than 2006
    assert should_replace(2004, 2006, 1998) is False
    assert should_replace(2004, 1998, 2006) is True


def test_refuses_to_act_on_missing_years():
    assert should_replace(None, 2000, 1990) is False
    assert should_replace(2000, None, 1990) is False
    assert should_replace(2000, 2010, None) is False


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"{len(tests)} repick decision tests passed")
