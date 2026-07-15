"""Validate the hitster deck seed (deck-seed.json) before a deck build.

Checks, in order:
  1. The file parses as JSON.
  2. Every song entry has a non-empty title and artist and an integer year in
     the range 1940 to 2026 (inclusive).
  3. Every entry in the "disney" and "movie" categories carries a source object
     whose type is one of disney, movie or musical and whose name is non-empty.
  4. No song appears twice anywhere in the file. Songs are compared on a
     normalised title plus artist (casefolded, diacritics removed, parentheticals
     and punctuation stripped). Two different songs that merely share a title but
     have different artists are NOT flagged.

It also prints a per-category count and a per-decade histogram.

Exit code is 1 (with a clear list of every problem) when anything fails, and 0
when the seed is clean. Run it after editing deck-seed.json and before
build_deck.py.

Usage:
    python tools/validate_seed.py
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

SEED = Path(__file__).parent / "deck-seed.json"

YEAR_MIN = 1940
YEAR_MAX = 2026
ALLOWED_SOURCE_TYPES = {"disney", "movie", "musical"}
SOURCED_CATEGORIES = {"disney", "movie"}


def norm(s):
    """Normalise a title or artist for duplicate comparison."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\bfeat\.?\b.*$", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def main():
    problems = []

    try:
        raw = SEED.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"FAIL: cannot read {SEED}: {exc}")
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"FAIL: deck-seed.json does not parse: {exc}")
        return 1

    songs = data.get("songs")
    if not isinstance(songs, dict):
        print('FAIL: top-level "songs" object is missing or not an object')
        return 1

    counts = {}
    decade_hist = {}
    seen = {}  # norm key -> (category, title, artist)

    for cat, entries in songs.items():
        if not isinstance(entries, list):
            problems.append(f'category "{cat}" is not a list')
            continue
        counts[cat] = len(entries)
        for i, e in enumerate(entries):
            where = f'{cat}[{i}]'
            if not isinstance(e, dict):
                problems.append(f"{where}: entry is not an object")
                continue

            title = e.get("title")
            artist = e.get("artist")
            year = e.get("year")

            if not isinstance(title, str) or not title.strip():
                problems.append(f"{where}: missing or empty title")
            if not isinstance(artist, str) or not artist.strip():
                problems.append(f"{where}: missing or empty artist ({title!r})")

            if isinstance(year, bool) or not isinstance(year, int):
                problems.append(f"{where}: year is not an integer ({title!r} -> {year!r})")
            elif not (YEAR_MIN <= year <= YEAR_MAX):
                problems.append(
                    f"{where}: year {year} out of range {YEAR_MIN}-{YEAR_MAX} ({title!r})"
                )
            else:
                decade = (year // 10) * 10
                decade_hist[decade] = decade_hist.get(decade, 0) + 1

            if cat in SOURCED_CATEGORIES:
                src = e.get("source")
                if not isinstance(src, dict):
                    problems.append(f"{where}: {title!r} missing source object")
                else:
                    stype = src.get("type")
                    sname = src.get("name")
                    if stype not in ALLOWED_SOURCE_TYPES:
                        problems.append(
                            f"{where}: {title!r} source type {stype!r} not in {sorted(ALLOWED_SOURCE_TYPES)}"
                        )
                    if not isinstance(sname, str) or not sname.strip():
                        problems.append(f"{where}: {title!r} source has empty name")

            if isinstance(title, str) and isinstance(artist, str) and title.strip() and artist.strip():
                key = (norm(title), norm(artist))
                if key in seen:
                    pcat, ptitle, partist = seen[key]
                    problems.append(
                        f"DUPLICATE: {artist} - {title} in [{cat}] also appears as "
                        f"{partist} - {ptitle} in [{pcat}]"
                    )
                else:
                    seen[key] = (cat, title, artist)

    total = sum(counts.values())
    print(f"Categories: {len(counts)}  Total songs: {total}\n")
    print("Per-category counts:")
    for cat in songs:
        if cat in counts:
            print(f"  {cat:10s} {counts[cat]}")
    print("\nPer-decade histogram:")
    for decade in sorted(decade_hist):
        bar = "#" * (decade_hist[decade] // 2)
        print(f"  {decade}s  {decade_hist[decade]:4d}  {bar}")

    if problems:
        print(f"\nFAIL: {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("\nOK: seed is clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
