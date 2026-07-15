"""Audit the built hitster deck (deck.json) against real Spotify metadata.

For every track in deck.json this fetches Spotify's public track embed page
(https://open.spotify.com/embed/track/<id>) and reads the __NEXT_DATA__ JSON
blob out of it. That gives the actual artist name(s), the actual track title and
the actual release year straight from Spotify, with NO credentials or API keys
required (the embed pages are public).

Each track's seed values are then compared against what Spotify says and flagged
when they disagree:
  - ARTIST_MISMATCH / ARTIST_WORD_ONLY: the seed artist does not match (or only
    partially matches) the artist Spotify returns, i.e. the build resolved the
    wrong recording.
  - TITLE_MISMATCH: the seed title does not match the Spotify title.
  - RELEASED_BEFORE_SEED_YEAR: Spotify's release year is meaningfully earlier
    than the seed year (a hint the wrong edition was matched).
  - FETCH_FAILED: the embed page could not be fetched after retries.

A JSON report is written to audit_report.json next to this script, and progress
is checkpointed line by line to audit_checkpoint.jsonl so an interrupted run
(connection resets are common) resumes where it left off. Both files are
throwaway and git-ignored.

When to run: after every deck build (python tools/build_deck.py). The build
resolves Spotify track ids by search, which occasionally matches a cover, a
re-recording or the wrong artist; this audit is how you catch that before the
deck ships.

Usage:
    python tools/audit_deck.py            # audit the whole deck
    python tools/audit_deck.py danish     # audit a single category only
"""
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

DECK = Path(__file__).parent / "deck.json"
OUT = Path(__file__).parent / "audit_report.json"
CHECKPOINT = Path(__file__).parent / "audit_checkpoint.jsonl"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\bfeat\.?\b.*$", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def find_entity(obj):
    """Recursively find the dict that has both 'artists' and 'name' keys."""
    if isinstance(obj, dict):
        if "artists" in obj and "name" in obj:
            return obj
        for v in obj.values():
            r = find_entity(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_entity(v)
            if r:
                return r
    return None


def fetch_track(tid, tries=0):
    try:
        resp = SESSION.get(
            f"https://open.spotify.com/embed/track/{tid}",
            timeout=15,
        )
    except requests.exceptions.RequestException:
        if tries < 5:
            time.sleep(10 * (tries + 1))
            return fetch_track(tid, tries + 1)
        return None
    if resp.status_code != 200:
        if tries < 5:
            time.sleep(10 * (tries + 1))
            return fetch_track(tid, tries + 1)
        return None
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        resp.text,
        re.S,
    )
    if not m:
        return None
    data = json.loads(m.group(1))
    ent = find_entity(data)
    if not ent:
        return None
    artists = [a.get("name", "") for a in ent.get("artists", [])]
    uris = [a.get("uri", "") for a in ent.get("artists", [])]
    rel = (ent.get("releaseDate") or {}).get("isoString", "")
    year = int(rel[:4]) if rel[:4].isdigit() else None
    return {"name": ent.get("name", ""), "artists": artists,
            "artist_uris": uris, "release_year": year}


def main():
    deck = json.loads(DECK.read_text(encoding="utf-8"))
    songs = deck["songs"]
    only_cat = sys.argv[1] if len(sys.argv) > 1 else None
    if only_cat:
        songs = [s for s in songs if s["cat"] == only_cat]
    done = {}
    if CHECKPOINT.exists():
        for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["id"]] = r
    results = []
    for i, s in enumerate(songs):
        if s["id"] in done:
            results.append(done[s["id"]])
            continue
        info = fetch_track(s["id"])
        time.sleep(0.8)
        row = {"cat": s["cat"], "seed_artist": s["artist"],
               "seed_title": s["title"], "seed_year": s["year"], "id": s["id"]}
        if not info:
            row["status"] = "FETCH_FAILED"
            results.append(row)
            print(f"{i + 1}/{len(songs)} FETCH_FAILED {s['artist']} - {s['title']}", flush=True)
            continue
        row.update({"actual_title": info["name"],
                    "actual_artists": info["artists"],
                    "artist_uris": info["artist_uris"],
                    "release_year": info["release_year"]})
        na = norm(s["artist"])
        cand = norm(" ".join(info["artists"]))
        full_match = na and na in cand
        word_match = any(w in cand for w in na.split() if len(w) > 3)
        nt = norm(s["title"])
        ct = norm(info["name"])
        title_ok = nt and (nt in ct or ct in nt)
        problems = []
        if not full_match:
            problems.append("ARTIST_WORD_ONLY" if word_match else "ARTIST_MISMATCH")
        if not title_ok:
            problems.append("TITLE_MISMATCH")
        if info["release_year"] and info["release_year"] < s["year"] - 1:
            problems.append("RELEASED_BEFORE_SEED_YEAR")
        row["status"] = ",".join(problems) if problems else "OK"
        results.append(row)
        with CHECKPOINT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        mark = "!" if problems else "."
        print(f"{i + 1}/{len(songs)} {mark} {s['artist']} - {s['title']}"
              + (f"  => {', '.join(info['artists'])} / {info['name']} [{row['status']}]" if problems else ""),
              flush=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    bad = [r for r in results if r["status"] != "OK"]
    print(f"\nDone. {len(results)} checked, {len(bad)} flagged. Report: {OUT}", flush=True)
    for r in bad:
        print(f"  [{r['cat']}] {r['seed_artist']} - {r['seed_title']}: {r['status']}"
              f" (actual: {', '.join(r.get('actual_artists', []))} / {r.get('actual_title', '?')},"
              f" rel {r.get('release_year')})", flush=True)


if __name__ == "__main__":
    main()
