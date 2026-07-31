#!/usr/bin/env python3
"""Import the Musik i Gentofte festival playlist as its own deck category.

Source of truth is the festival data the website repo already builds for
https://www.patrickrobel.dk/musikigentofte:

    patrickrobelweb/website/src/data/musikigentofte.json

That file has exact Spotify track ids but no release years, so this script
fetches each track's public embed page (the same credential-free trick
audit_deck.py uses) to read the real title, the real artist credits and the
real release year straight from Spotify.

It then writes, in one --apply pass:
  - tools/deck-seed.json : a "gentofte" category plus one seed entry per track.
    The category is inserted FIRST in "songs" so that a track already present in
    another category (Rasmus Seebach in "danish") lands in Gentofte, and the
    other category's now-duplicate line is removed (validate_seed.py rejects the
    same song twice, and build_deck.py would silently drop one of them).
  - tools/fetch-cache.json : a resolved entry per track, complete with QR code,
    keyed exactly like build_deck.py's reuse cache. Because every track is
    pre-resolved from its known id, the following build_deck.py run needs ZERO
    Spotify API calls and never prompts for credentials, and no search step can
    match the wrong recording.

Re-running is safe and idempotent: an existing "gentofte" block is replaced, not
appended to. Fetches are checkpointed to gentofte_checkpoint.jsonl (git-ignored),
so a rerun after an interrupted fetch costs nothing.

Wrong years (Spotify dates a re-release or a compilation, not the original
recording) are corrected in tools/gentofte-overrides.json:

    { "<spotify track id>": { "year": 1974, "title": "...", "artist": "..." } }

Every key is optional; only "year" is usually needed. Rerun --apply after
editing it, then rebuild.

Usage:
    python tools/import_gentofte.py                # dry run, prints everything
    python tools/import_gentofte.py --apply        # write seed + fetch cache
    python tools/import_gentofte.py --source PATH  # non-default festival json

After --apply:
    python tools/validate_seed.py
    python tools/build_deck.py
    python tools/audit_deck.py gentofte
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from audit_deck import fetch_track, norm
from build_deck import qr_data_uri

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
SEED = TOOLS / "deck-seed.json"
FETCH_CACHE = TOOLS / "fetch-cache.json"
CHECKPOINT = TOOLS / "gentofte_checkpoint.jsonl"
OVERRIDES = TOOLS / "gentofte-overrides.json"
DEFAULT_SOURCE = REPO.parent / "patrickrobelweb" / "website" / "src" / "data" / "musikigentofte.json"

CAT_KEY = "gentofte"
CAT_LINE = ('{ "key": "gentofte", "label": "Musik i Gentofte", '
            '"emoji": "\U0001F3A1", "color": "#2fbf9f" }')

# "Sprækker ft. Søn", "Tættere (feat. Gilli)", "Hva Så [featuring X]": the deck
# convention keeps the title clean and credits everyone in the artist field.
FEAT_TAIL = re.compile(
    r"\s*[\(\[]?\s*(?:feat\.?|ft\.?|featuring|med)\s+(?P<names>[^)\]]+?)\s*[\)\]]?\s*$",
    re.I,
)
SPLIT_NAMES = re.compile(r"\s*(?:,|&|\+|\bog\b|\band\b|\bx\b)\s*", re.I)


def split_title(spotify_name):
    """Return (clean title, [names lifted out of a feat. tail])."""
    m = FEAT_TAIL.search(spotify_name or "")
    if not m:
        return (spotify_name or "").strip(), []
    title = (spotify_name[: m.start()]).strip()
    if not title:  # the whole name was the tail, leave it alone
        return (spotify_name or "").strip(), []
    names = [n.strip() for n in SPLIT_NAMES.split(m.group("names")) if n.strip()]
    return title, names


def credit(artists, extra_names):
    """Build a deck artist credit: "Main (feat. Second, Third)"."""
    if not artists:
        artists = ["Unknown"]
    main, rest = artists[0], list(artists[1:])
    seen = {norm(main)}
    extras = []
    for name in rest + extra_names:
        key = norm(name)
        if not key or key in seen:
            continue
        seen.add(key)
        extras.append(name)
    if not extras:
        return main
    return f"{main} (feat. {', '.join(extras)})"


def load_checkpoint():
    done = {}
    if CHECKPOINT.exists():
        for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["id"]] = row
    return done


def append_checkpoint(row):
    with CHECKPOINT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_overrides():
    if not OVERRIDES.exists():
        return {}
    try:
        return json.loads(OVERRIDES.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: {OVERRIDES.name} does not parse: {exc}")
        sys.exit(1)


def gather(tracks):
    """Resolve every source track to a deck entry (title, artist, year, id)."""
    done = load_checkpoint()
    overrides = load_overrides()
    entries, failed = [], []
    for i, t in enumerate(tracks, 1):
        tid = t["id"]
        info = done.get(tid)
        if info is None:
            fetched = fetch_track(tid)
            time.sleep(0.8)  # same gentle spacing as audit_deck.py
            if not fetched:
                failed.append({"id": tid, "name": t.get("name", ""), "why": "embed fetch failed"})
                print(f"{i}/{len(tracks)} FETCH_FAILED {t.get('name', '')}", flush=True)
                continue
            info = {"id": tid, "name": fetched["name"], "artists": fetched["artists"],
                    "year": fetched["release_year"]}
            append_checkpoint(info)
        title, extra = split_title(info["name"])
        entry = {"id": tid, "title": title, "artist": credit(info["artists"], extra),
                 "year": info["year"], "spotify_name": info["name"],
                 "spotify_artists": info["artists"]}
        ov = overrides.get(tid) or {}
        for field in ("title", "artist", "year"):
            if field in ov:
                entry[field] = ov[field]
                entry["overridden"] = True
        if not isinstance(entry["year"], int):
            failed.append({"id": tid, "name": info["name"],
                           "why": "no release year from Spotify, add one to " + OVERRIDES.name})
            print(f"{i}/{len(tracks)} NO_YEAR {info['name']}", flush=True)
            continue
        entries.append(entry)
        print(f"{i}/{len(tracks)} ok {entry['year']} {entry['artist']} - {entry['title']}"
              + ("  [override]" if entry.get("overridden") else ""), flush=True)
    return entries, failed


def dedupe(entries):
    """Drop a track listed twice in the festival data (same song, same credit)."""
    kept, seen, dropped = [], {}, []
    for e in entries:
        key = (norm(e["title"]), norm(e["artist"]))
        if key in seen:
            dropped.append(e)
            continue
        seen[key] = e
        kept.append(e)
    return kept, dropped


def seed_lines(entries):
    out = []
    for i, e in enumerate(entries):
        line = ('      { "title": ' + json.dumps(e["title"], ensure_ascii=False)
                + ', "artist": ' + json.dumps(e["artist"], ensure_ascii=False)
                + ', "year": ' + str(e["year"]) + ' }')
        out.append(line + ("," if i < len(entries) - 1 else ""))
    return out


def patch_seed(entries):
    """Rewrite deck-seed.json: gentofte category + songs block, dups removed.

    Returns (new text, [removed duplicate descriptions]).
    """
    text = SEED.read_text(encoding="utf-8")
    data = json.loads(text)

    # 1. Drop any previous gentofte block / category line so a rerun replaces them.
    text = re.sub(r'\n    "gentofte": \[\n.*?\n    \],', "", text, count=1, flags=re.S)
    text = re.sub(r',\n    \{ "key": "gentofte"[^\n]*\}', "", text, count=1)

    # 2. Remove lines in OTHER categories for songs that now belong to Gentofte.
    #    validate_seed.py fails on a repeated song and build_deck.py would drop
    #    one of the two cards depending on iteration order.
    wanted = {(norm(e["title"]), norm(e["artist"])) for e in entries}
    removed = []
    drop_idx = set()
    lines = text.split("\n")
    cat_of_line = None
    for idx, line in enumerate(lines):
        m = re.match(r'\s*"([a-z0-9_]+)": \[', line)
        if m:
            cat_of_line = m.group(1)
            continue
        stripped = line.strip().rstrip(",")
        if not (stripped.startswith("{") and stripped.endswith("}")):
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if "title" not in obj or "artist" not in obj or cat_of_line == CAT_KEY:
            continue
        if (norm(obj["title"]), norm(obj["artist"])) in wanted:
            drop_idx.add(idx)
            removed.append(f'[{cat_of_line}] {obj["artist"]} - {obj["title"]} ({obj.get("year")})')

    if drop_idx:
        out = []
        for idx, line in enumerate(lines):
            if idx in drop_idx:
                nxt = next((l for l in lines[idx + 1:] if l.strip()), "")
                # Removing the last entry of an array leaves a trailing comma behind.
                if nxt.strip().startswith("]") and out and out[-1].rstrip().endswith(","):
                    out[-1] = out[-1].rstrip()[:-1]
                continue
            out.append(line)
        text = "\n".join(out)

    # 3. Insert the category (last tile in the setup grid).
    anchor = '\n  ],\n  "songs": {'
    if anchor not in text:
        print("FAIL: could not find the categories/songs anchor in deck-seed.json")
        sys.exit(1)
    text = text.replace(anchor, ",\n    " + CAT_LINE + anchor, 1)

    # 4. Insert the songs block FIRST so Gentofte wins any cross-category tie.
    block = ('\n    "gentofte": [\n' + "\n".join(seed_lines(entries)) + "\n    ],")
    text = text.replace('\n  "songs": {', '\n  "songs": {' + block, 1)

    new = json.loads(text)  # never write a seed that does not parse
    if list(new["songs"])[0] != CAT_KEY:
        print("FAIL: gentofte did not end up first in \"songs\"")
        sys.exit(1)
    if len(new["songs"][CAT_KEY]) != len(entries):
        print("FAIL: gentofte block has the wrong entry count")
        sys.exit(1)
    if len(new["categories"]) != len(data["categories"]) + (
            0 if any(c["key"] == CAT_KEY for c in data["categories"]) else 1):
        print("FAIL: categories array changed unexpectedly")
        sys.exit(1)
    return text, removed


def patch_cache(entries):
    """Pre-resolve every Gentofte track in build_deck.py's reuse cache."""
    cache = {}
    if FETCH_CACHE.exists():
        cache = json.loads(FETCH_CACHE.read_text(encoding="utf-8"))
    for key in [k for k in cache if k.startswith(CAT_KEY + "|")]:
        del cache[key]  # rerun replaces, so a retitled entry leaves no stale key
    for e in entries:
        url = f"https://open.spotify.com/track/{e['id']}"
        cache[CAT_KEY + "|" + norm(e["title"])] = {
            "id": e["id"], "title": e["title"], "artist": e["artist"],
            "year": e["year"], "cat": CAT_KEY, "url": url, "qr": qr_data_uri(url),
        }
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.environ.get("GENTOFTE_DATA") or str(DEFAULT_SOURCE),
                    help="path to musikigentofte.json (default: sibling patrickrobelweb clone)")
    ap.add_argument("--apply", action="store_true",
                    help="write deck-seed.json and fetch-cache.json (default is a dry run)")
    args = ap.parse_args()

    src = Path(args.source)
    if not src.exists():
        print(f"FAIL: festival data not found at {src}\n"
              "Pass --source PATH or set GENTOFTE_DATA to the website repo's "
              "website/src/data/musikigentofte.json")
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))
    tracks = data.get("tracks") or []
    festival = (data.get("festival") or {}).get("name", "Musik i Gentofte")
    print(f"{festival}: {len(tracks)} tracks from {src}\n")
    if not tracks:
        print("FAIL: no tracks in the source file")
        return 1

    entries, failed = gather(tracks)
    entries, dupes = dedupe(entries)
    entries.sort(key=lambda e: (e["year"], norm(e["artist"]), norm(e["title"])))

    print(f"\nResolved {len(entries)} of {len(tracks)} tracks.")
    if dupes:
        print(f"\nListed twice in the festival data, kept once ({len(dupes)}):")
        for e in dupes:
            print(f"  {e['artist']} - {e['title']}")
    if failed:
        print(f"\nNOT imported ({len(failed)}):")
        for f in failed:
            print(f"  {f['name']} ({f['id']}): {f['why']}")

    decades = {}
    for e in entries:
        decades[e["year"] // 10 * 10] = decades.get(e["year"] // 10 * 10, 0) + 1
    print("\nPer-decade:")
    for d in sorted(decades):
        print(f"  {d}s  {decades[d]:3d}  {'#' * decades[d]}")

    text, removed = patch_seed(entries)
    if removed:
        print(f"\nMoved into Gentofte, removed from its old category ({len(removed)}):")
        for r in removed:
            print(f"  {r}")

    print("\nGentofte entries, oldest first:")
    for e in entries:
        print(f"  {e['year']}  {e['artist']} - {e['title']}"
              + ("  [override]" if e.get("overridden") else ""))

    if not args.apply:
        print("\nDry run. Nothing written. Rerun with --apply to write "
              "deck-seed.json + fetch-cache.json.")
        print(f"Check the years above first; correct any wrong one in {OVERRIDES.name}.")
        return 0

    cache = patch_cache(entries)
    SEED.write_text(text, encoding="utf-8")
    tmp = FETCH_CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, FETCH_CACHE)
    print(f"\nWrote {SEED}")
    print(f"Wrote {FETCH_CACHE} ({len(entries)} gentofte tracks pre-resolved, "
          "so the build needs no Spotify credentials)")
    print("\nNext:\n  python tools/validate_seed.py\n  python tools/build_deck.py"
          "\n  python tools/audit_deck.py gentofte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
