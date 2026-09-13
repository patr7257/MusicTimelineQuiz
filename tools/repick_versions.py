#!/usr/bin/env python3
"""Re-resolve already-built cards with the year-aware picker in build_deck.py.

Why this exists: Spotify now returns popularity 0 for every track under client
credentials, so the old pick_best scored every exact-title hit identically and kept
whichever Spotify listed first. That is often a re-release, which is how the 2013
julekalender single "I En Stjerneregn Af Sne" became a 2026 re-recording of the
same name. pick_best now prefers the release closest to the seed year, but cards
resolved before that change still carry the old pick.

What it does, per seed song that already has a cached track:
  1. searches Spotify again, with the seed year feeding the tie-break,
  2. if the winner is a different track id, reads the CURRENT track's release year
     off the public embed page (no credentials) and compares,
  3. replaces the card only when the new track sits strictly closer to the seed
     year, and never touches an entry marked "pinned" (hand-resolved by a human).

Every replacement is written to the fetch cache and to deck.json immediately, so a
rate limit or Ctrl-C never loses work, and a rerun resumes from the checkpoint.
Afterwards run:  python tools/build_deck.py --no-fetch

Usage:
  python tools/repick_versions.py                 # whole deck
  python tools/repick_versions.py --only christmas
  python tools/repick_versions.py --dry-run       # decide and report, change nothing
"""
import argparse
import json
import os
import sys
import time
from getpass import getpass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from audit_deck import fetch_track  # noqa: E402  (public embed page, no credentials)
from build_deck import (  # noqa: E402
    DECK_JSON, FETCH_CACHE, SEED, RateLimited, TokenExpired,
    get_token, norm, qr_data_uri, release_year, resolve,
)

CHECKPOINT = HERE / "repick_checkpoint.jsonl"
REPORT = HERE / "repick_report.json"
SEARCH_GAP = 0.6  # same spacing build_deck uses between live calls


def should_replace(seed_year, old_year, new_year):
    """Replace only when the new track is strictly closer to the seed year.

    An unknown year on either side means no opinion, so the card stays as it is:
    a silent swap based on missing metadata is exactly the failure being fixed.
    """
    if not seed_year or not old_year or not new_year:
        return False
    return abs(new_year - seed_year) < abs(old_year - seed_year)


def load_checkpoint():
    if not CHECKPOINT.exists():
        return {}
    done = {}
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            done[row["key"]] = row
    return done


def append_checkpoint(row):
    with CHECKPOINT.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="limit to one category key, e.g. christmas")
    ap.add_argument("--dry-run", action="store_true", help="report the swaps, write nothing")
    args = ap.parse_args()

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    cache = json.loads(FETCH_CACHE.read_text(encoding="utf-8"))
    deck = json.loads(DECK_JSON.read_text(encoding="utf-8"))
    deck_by_id = {s["id"]: s for s in deck["songs"]}
    done = load_checkpoint()

    todo = []
    for cat, entries in seed["songs"].items():
        if args.only and cat != args.only:
            continue
        for e in entries:
            key = cat + "|" + norm(e["title"])
            cached = cache.get(key)
            if not cached or not cached.get("id"):
                continue
            if cached.get("pinned"):
                continue
            if key in done:
                continue
            todo.append((key, cat, e, cached))

    print(f"{len(todo)} cards to re-check"
          + (f" (skipping {len(done)} already checked)" if done else "")
          + (" [dry run]" if args.dry_run else "") + ".")
    if not todo:
        return 0

    print("Spotify credentials (from https://developer.spotify.com/dashboard):")
    client_id = os.environ.get("SPOTIFY_CLIENT_ID") or input("  Client ID: ").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET") or getpass("  Client secret (hidden): ").strip()
    token = get_token(client_id, client_secret)
    token_at = time.time()
    print("Token OK. .=unchanged  *=replaced  ?=kept, new pick was not closer\n", flush=True)

    swaps, kept, checked = [], [], 0
    for key, cat, e, cached in todo:
        if time.time() - token_at > 50 * 60:
            token = get_token(client_id, client_secret)
            token_at = time.time()
        try:
            best = resolve(token, e["title"], e["artist"], seed_year=e.get("year"))
        except TokenExpired:
            token = get_token(client_id, client_secret)
            token_at = time.time()
            best = resolve(token, e["title"], e["artist"], seed_year=e.get("year"))
        except RateLimited as rl:
            print(f"\n\nRate limited, Retry-After {rl.seconds}s. Stopping here; "
                  f"rerun the same command to resume ({checked} checked this run).")
            break
        time.sleep(SEARCH_GAP)
        checked += 1

        if not best or best["id"] == cached["id"]:
            print(".", end="", flush=True)
            append_checkpoint({"key": key, "id": cached["id"], "action": "unchanged"})
            continue

        old = fetch_track(cached["id"])
        old_year = old.get("release_year") if old else None
        new_year = release_year(best)
        row = {
            "key": key, "cat": cat, "title": e["title"], "artist": e["artist"],
            "seed_year": e.get("year"), "old_id": cached["id"], "old_year": old_year,
            "new_id": best["id"], "new_year": new_year, "new_title": best.get("name", ""),
        }
        if not should_replace(e.get("year"), old_year, new_year):
            row["action"] = "kept"
            kept.append(row)
            print("?", end="", flush=True)
            append_checkpoint(row)
            continue

        row["action"] = "replaced"
        swaps.append(row)
        print("*", end="", flush=True)
        if not args.dry_run:
            url = f"https://open.spotify.com/track/{best['id']}"
            entry = {"id": best["id"], "title": e["title"], "artist": e["artist"],
                     "year": e["year"], "cat": cat, "url": url, "qr": qr_data_uri(url)}
            if "source" in e:
                entry["source"] = e["source"]
            cache[key] = entry
            FETCH_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            stale = deck_by_id.pop(cached["id"], None)
            if stale is not None:
                stale.update(entry)
                deck_by_id[best["id"]] = stale
                DECK_JSON.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
        append_checkpoint(row)

    print(f"\n\n{checked} checked, {len(swaps)} replaced, {len(kept)} left alone.")
    REPORT.write_text(json.dumps({"replaced": swaps, "kept": kept}, ensure_ascii=False, indent=2),
                      encoding="utf-8", newline="\n")
    for r in swaps:
        print(f"  [{r['cat']}] {r['artist']} - {r['title']}: "
              f"{r['old_year']} -> {r['new_year']} (seed {r['seed_year']})")
    print(f"\nFull report: {REPORT}")
    if swaps and not args.dry_run:
        print("Now rebuild:  python tools/build_deck.py --no-fetch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
