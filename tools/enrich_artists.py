"""Add missing co/featured artists to every deck card's artist credit.

The "Calvin Harris problem": Spotify credits This Is What You Came For to
Calvin Harris AND Rihanna, but the card only says "Calvin Harris", so guessing
Rihanna scores nothing. The host's guess matcher already splits the card artist
on feat./ft./,/&, so the whole fix is data: rewrite the credit as
"Calvin Harris (feat. Rihanna)" and every listed artist becomes a correct answer.

For every track in deck.json this fetches Spotify's public embed page (same
credential-free mechanism as audit_deck.py) and appends any artists missing
from the current credit as "(feat. A, B)". Tracks whose current artist does not
match Spotify at all (the known audit flags, i.e. wrong recordings) are SKIPPED
and reported; importing a wrong recording's credits would make things worse.

Applies IN LOCKSTEP to all four data files, so validators and future builds
stay consistent:
  - songs.js            (the shipped deck)
  - tools/deck.json     (audit_deck.py input)
  - tools/fetch-cache.json  (build_deck.py reuse cache)
  - tools/deck-seed.json    (so a future rebuild keeps the credit)

The "(feat. X)" format is safe for validate_seed.py and audit_deck.py: both
normalize away parentheticals and feat. tails. Reruns are idempotent: an artist
already named anywhere in the credit is never appended again.

Usage:
    python tools/enrich_artists.py            # DRY-RUN: fetch + report only
    python tools/enrich_artists.py --apply    # write the four files

Progress is checkpointed to enrich_checkpoint.jsonl (git-ignored), so an
interrupted run resumes and an --apply after a dry-run rewrites instantly.
"""
import argparse
import json
import re
import time
import unicodedata
from pathlib import Path

from audit_deck import fetch_track, norm

TOOLS = Path(__file__).parent
DECK_JSON = TOOLS / "deck.json"
SEED_JSON = TOOLS / "deck-seed.json"
FETCH_CACHE = TOOLS / "fetch-cache.json"
SONGS_JS = TOOLS.parent / "songs.js"
CHECKPOINT = TOOLS / "enrich_checkpoint.jsonl"


def norm_keep(s):
    """Like audit_deck.norm but WITHOUT dropping parentheticals or the feat. tail,
    so an already-added "(feat. X)" credit counts as covering X on a rerun."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


# Generic soundtrack entities Spotify credits as "artists" (Disney itself, choruses,
# casts, ensembles, orchestras). They would clutter the card and make e.g. "Disney" a
# correct artist guess, so they are never appended.
JUNK_RE = re.compile(
    r"^disney$|^students$|\b(chorus|choir|ensemble|orchestra|cast|singers)\b", re.I)
HONORIFICS = {"ms", "mr", "mrs", "dr"}


def covers(credit, artist_name):
    """True when artist_name already appears (as whole words) in the credit string,
    ignoring honorifics ("Ms. Lauryn Hill" is covered by "Lauryn Hill")."""
    n = norm_keep(artist_name)
    if not n:
        return True
    ck = norm_keep(credit)
    if f" {n} " in f" {ck} ":
        return True
    # Reverse containment: the addition is a fuller form of the credit itself
    # ("James Brown & The Famous Flames" on a "James Brown" card) - skip, not append.
    if ck and f" {ck} " in f" {n} ":
        return True
    toks = set(n.split()) - HONORIFICS
    return bool(toks) and toks <= set(ck.split())


def load_checkpoint():
    done = {}
    if CHECKPOINT.exists():
        for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["id"]] = row
    return done


def gather(songs):
    """Fetch (or reuse checkpointed) embed artists for every song; classify each."""
    done = load_checkpoint()
    changes, skips, fails = [], [], []
    for i, s in enumerate(songs):
        row = done.get(s["id"])
        if row is None:
            info = fetch_track(s["id"])
            time.sleep(0.5)
            row = {"id": s["id"], "artists": info["artists"] if info else None}
            with CHECKPOINT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            done[s["id"]] = row
        artists = row.get("artists")
        label = f'{i + 1}/{len(songs)} [{s["cat"]}] {s["artist"]} - {s["title"]}'
        if not artists:
            fails.append(s)
            print(f"{label}  FETCH_FAILED", flush=True)
            continue
        # Wrong-recording guard: the current credit must match Spotify's artists at all
        # (same check as audit_deck.py) before we trust the embed's artist list.
        na = norm(s["artist"])
        if na and na not in norm(" ".join(artists)):
            skips.append((s, artists))
            print(f"{label}  SKIP_MISMATCH (Spotify says: {', '.join(artists)})", flush=True)
            continue
        missing = [a for a in artists if not covers(s["artist"], a) and not JUNK_RE.search(a)]
        if missing:
            new_artist = f'{s["artist"]} (feat. {", ".join(missing)})'
            changes.append({"id": s["id"], "cat": s["cat"], "title": s["title"],
                            "old": s["artist"], "new": new_artist})
            print(f"{label}  ->  {new_artist}", flush=True)
        elif (i + 1) % 50 == 0:
            print(f"{label}  ok", flush=True)
    return changes, skips, fails


def apply_changes(changes):
    by_id = {c["id"]: c for c in changes}

    # deck.json (pretty) and songs.js (banner + one-line JSON), matching build_deck.write_db.
    deck = json.loads(DECK_JSON.read_text(encoding="utf-8"))
    for s in deck["songs"]:
        c = by_id.get(s["id"])
        if c:
            s["artist"] = c["new"]
    DECK_JSON.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")

    js = SONGS_JS.read_text(encoding="utf-8")
    m = re.match(r"^(//[^\n]*\n)window\.HITSTER_DB = (.*);\n?$", js, re.S)
    if not m:
        raise SystemExit("songs.js layout not recognized; aborting before writing.")
    db = json.loads(m.group(2))
    for s in db["songs"]:
        c = by_id.get(s["id"])
        if c:
            s["artist"] = c["new"]
    SONGS_JS.write_text(m.group(1) + "window.HITSTER_DB = " + json.dumps(db, ensure_ascii=False) + ";\n",
                        encoding="utf-8")

    cache = json.loads(FETCH_CACHE.read_text(encoding="utf-8"))
    for entry in cache.values():
        c = by_id.get(entry.get("id"))
        if c:
            entry["artist"] = c["new"]
    tmp = FETCH_CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(FETCH_CACHE)

    # deck-seed.json is hand-formatted (one entry per line), so patch it textually to keep
    # the diff to exactly the changed lines: on the line holding this title, swap the artist.
    seed_text = SEED_JSON.read_text(encoding="utf-8")
    lines = seed_text.split("\n")
    unmatched = []
    for c in changes:
        title_needle = '"title": ' + json.dumps(c["title"], ensure_ascii=False)
        artist_old = '"artist": ' + json.dumps(c["old"], ensure_ascii=False)
        artist_new = '"artist": ' + json.dumps(c["new"], ensure_ascii=False)
        hit = False
        for idx, line in enumerate(lines):
            if title_needle in line and artist_old in line:
                lines[idx] = line.replace(artist_old, artist_new, 1)
                hit = True
                break
        if not hit:
            unmatched.append(c)
    SEED_JSON.write_text("\n".join(lines), encoding="utf-8")
    if unmatched:
        print(f"\nWARNING: {len(unmatched)} change(s) had no matching deck-seed.json line "
              f"(seed formatting drift?); songs.js/deck.json/cache were still updated:")
        for c in unmatched:
            print(f'  [{c["cat"]}] {c["old"]} - {c["title"]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default is dry-run)")
    args = ap.parse_args()

    deck = json.loads(DECK_JSON.read_text(encoding="utf-8"))
    songs = deck["songs"]
    print(f"{len(songs)} songs; {'APPLY' if args.apply else 'DRY-RUN'} mode.\n", flush=True)
    changes, skips, fails = gather(songs)

    print(f"\n{len(changes)} credits to enrich, {len(skips)} skipped (artist mismatch, "
          f"fix via audit flow), {len(fails)} fetch failures (rerun to retry).", flush=True)
    if not args.apply:
        print("Dry-run only. Rerun with --apply to write songs.js, deck.json, "
              "fetch-cache.json and deck-seed.json (instant, reuses the checkpoint).")
        return
    if not changes:
        print("Nothing to write.")
        return
    apply_changes(changes)
    print(f"Applied {len(changes)} credit updates to songs.js, tools/deck.json, "
          f"tools/fetch-cache.json and tools/deck-seed.json.")


if __name__ == "__main__":
    main()
