#!/usr/bin/env python3
"""
Build the Hitster song database (hitster/songs.js).

Online mode (default): resolves every song in deck-seed.json to a real,
Denmark-available Spotify track via the Spotify Web API (client credentials),
then bakes a QR code for each track straight into the database. Needs a free
Spotify app (client id + secret); the script prompts for them, nothing is stored.

Offline sample mode (--offline-sample): builds a small database from the already
verified tracks in verified.json / verified2.json, no credentials needed. Used to
test the frontend before the full deck is fetched.

Usage:
  python build_deck.py                 # online, prompts for Spotify credentials
  python build_deck.py --offline-sample
"""

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import unicodedata
from getpass import getpass
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = HERE / "deck-seed.json"
SONGS_JS = HERE.parent / "songs.js"
DECK_JSON = HERE / "deck.json"
FETCH_CACHE = HERE / "fetch-cache.json"

try:
    import qrcode
except ImportError:
    print("Missing dependency. Run:  python -m pip install qrcode pillow requests")
    sys.exit(1)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)          # drop parentheticals
    s = re.sub(r"\bfeat\.?\b.*$", " ", s)            # drop featuring tails
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def qr_data_uri(url: str) -> str:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ---------- fetch checkpoint ----------
# A persistent cache of every song resolved during a fetch run, saved to disk right
# after each successful resolve so a rate limit, crash, or Ctrl-C never loses work
# already paid for in API calls. Same shape as a deck.json entry, keyed the same way.
def load_fetch_cache() -> dict:
    if not FETCH_CACHE.exists():
        return {}
    try:
        return json.loads(FETCH_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_fetch_cache(cache: dict) -> None:
    tmp = FETCH_CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, FETCH_CACHE)


class RateLimited(Exception):
    """Raised when Spotify's rate limit cannot be waited out safely."""
    def __init__(self, seconds: int):
        self.seconds = seconds
        super().__init__(f"rate limited, Retry-After {seconds}s")


class TokenExpired(Exception):
    """Raised when the search endpoint answers 401 (the access token aged out)."""


def format_duration(seconds: int) -> str:
    if seconds >= 60:
        return f"{seconds / 60:.1f} minutes"
    return f"{seconds} seconds"


# ---------- Spotify Web API ----------
def get_token(client_id: str, client_secret: str) -> str:
    import requests
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=20,
    )
    if resp.status_code != 200:
        print(f"Token request failed ({resp.status_code}): {resp.text[:200]}")
        sys.exit(1)
    return resp.json()["access_token"]


def _do_search(token: str, q: str, market: str, tries: int = 0):
    import requests
    resp = requests.get(
        "https://api.spotify.com/v1/search",
        params={"q": q, "type": "track", "limit": 10, "market": market},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if resp.status_code == 401:
        raise TokenExpired()
    if resp.status_code == 429:
        wait = int(float(resp.headers.get("Retry-After", "2")))
        # A short wait is worth riding out (up to 4 tries total); a long one, or one
        # that keeps recurring, means honesty beats silently dropping songs.
        if wait > 60 or tries >= 3:
            raise RateLimited(wait)
        print(f"[rate limited {wait + 1}s]", end="", flush=True)
        time.sleep(wait + 1)
        return _do_search(token, q, market, tries + 1)
    if resp.status_code != 200:
        return []
    return resp.json().get("tracks", {}).get("items", [])


def resolve(token: str, title: str, artist: str, market: str = "DK"):
    # Strict field query first; only fall back to a looser plain query when it fails.
    # The plain query is more forgiving for Danish titles (accents, punctuation), and
    # pick_best still enforces a real title + artist match, so loosening stays safe.
    best = pick_best(_do_search(token, f'track:"{title}" artist:"{artist}"', market), title, artist)
    if best:
        return best
    time.sleep(0.6)  # these are two separate API calls, space them like any other call
    return pick_best(_do_search(token, f"{title} {artist}", market), title, artist)


_TITLE_SUFFIX_WORDS = {
    "remaster", "remastered", "remix", "version", "edit", "live", "acoustic",
    "mono", "stereo", "deluxe", "bonus", "track", "single", "radio", "extended",
    "instrumental", "karaoke", "anniversary", "original", "album", "explicit",
    "clean", "mix",
}


def _title_matches(nt, ct):
    """True when a seed title and a candidate's title are the same song.

    An exact normalized match always counts. A one-sided containment match
    (one title is a prefix/suffix/substring of the other) is only trusted
    when every leftover word on the longer side is a known edition qualifier
    (remaster, remix, radio edit, a year, ...). Otherwise a short seed title
    like "CPH" spuriously matches an unrelated longer title that merely
    starts with it, such as "CPH Girls (feat. Brandon Beal)".
    """
    if not nt or not ct:
        return False
    if nt == ct:
        return True
    shorter, longer = (nt, ct) if len(nt) <= len(ct) else (ct, nt)
    if shorter not in longer:
        return False
    leftover = longer.replace(shorter, " ", 1).split()
    return all(w in _TITLE_SUFFIX_WORDS or w.isdigit() for w in leftover)


def pick_best(items, title, artist):
    nt, na = norm(title), norm(artist)
    best, best_score = None, -1
    for it in items:
        cand_title = norm(it.get("name", ""))
        cand_artists = norm(" ".join(a.get("name", "") for a in it.get("artists", [])))
        title_ok = _title_matches(nt, cand_title)
        # Artist is enforced when given, but optional: soundtrack/ensemble tracks whose
        # exact credited artist is fuzzy still resolve on a distinctive title alone.
        artist_ok = (not na) or (na in cand_artists) or any(w in cand_artists for w in na.split() if len(w) > 3)
        if not (title_ok and artist_ok):
            continue
        score = it.get("popularity", 0)
        if cand_title == nt:
            score += 200
        if best is None or score > best_score:
            best, best_score = it, score
    return best


def build_online(wait=False):
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    force_full = "--force-full" in sys.argv

    def key_of(cat, title):
        return cat + "|" + norm(title)

    # Persistent fetch checkpoint: every song resolved in any past run (including one
    # interrupted by a rate limit or Ctrl-C before songs.js/deck.json were written).
    # Kept separate from "existing" so it can still be appended to and saved even
    # under --force-full, where existing is intentionally ignored.
    fetch_cache = load_fetch_cache()

    # Incremental: reuse everything already resolved (from a previous deck.json, plus
    # the fetch checkpoint) and only fetch songs still missing. This keeps request
    # counts tiny so Spotify's rate limit is not tripped, and never re-fetches what
    # already works.
    existing = {}
    if not force_full:
        if DECK_JSON.exists():
            try:
                prev = json.loads(DECK_JSON.read_text(encoding="utf-8"))
                for s in prev.get("songs", []):
                    existing[s["cat"] + "|" + norm(s["title"])] = s
            except Exception:
                existing = {}
        for key, s in fetch_cache.items():
            existing.setdefault(key, s)

    # Songs resolved during this process, so a --wait resume pass reuses them instead
    # of refetching. Consulted even under --force-full: a resume pass must never redo
    # calls this same run already paid for.
    session_resolved = {}

    def try_reuse(cat, e, seen_ids):
        reuse = session_resolved.get(key_of(cat, e["title"]))
        if reuse is None and not force_full:
            reuse = existing.get(key_of(cat, e["title"]))
        if not (reuse and reuse.get("id") and reuse.get("qr") and reuse["id"] not in seen_ids):
            return None
        # Keep source metadata in sync with the seed, even for a cached/reused entry,
        # so adding or editing "source" in deck-seed.json takes effect without a refetch.
        if "source" in e:
            reuse["source"] = e["source"]
        elif "source" in reuse:
            del reuse["source"]
        seen_ids.add(reuse["id"])
        return reuse

    missing = [(cat, e) for cat, entries in seed["songs"].items() for e in entries
               if key_of(cat, e["title"]) not in existing]
    print(f"Reusing {len(existing)} cached tracks; {len(missing)} to fetch"
          + (" (--force-full: refetching all)" if force_full else "") + ".")

    token = None
    creds = None
    token_at = 0.0
    if missing or force_full:
        print("Spotify credentials (from https://developer.spotify.com/dashboard):")
        client_id = os.environ.get("SPOTIFY_CLIENT_ID") or input("  Client ID: ").strip()
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET") or getpass("  Client secret (hidden): ").strip()
        creds = (client_id, client_secret)  # held in memory only, never written to disk
        token = get_token(client_id, client_secret)
        token_at = time.time()
        print("Token OK. o=reused  .=fetched  _=no match  ==duplicate\n", flush=True)
    else:
        print("Nothing to fetch, rebuilding songs.js from cache.\n")

    def refresh_token(reason):
        nonlocal token, token_at
        print(f"[token refresh: {reason}] ", end="", flush=True)
        token = get_token(creds[0], creds[1])
        token_at = time.time()

    def resolve_fresh(e):
        # Client-credentials tokens live about 1 hour; refresh proactively before
        # the edge, and reactively if the search endpoint says 401 anyway.
        if time.time() - token_at > 50 * 60:
            refresh_token("50 minutes since last token")
        try:
            return resolve(token, e["title"], e["artist"])
        except TokenExpired:
            refresh_token("search returned 401")
            return resolve(token, e["title"], e["artist"])

    def fetch_pass():
        songs = []
        seen_ids = set()
        dropped = []
        fetched = 0
        limited = None
        for cat, entries in seed["songs"].items():
            if limited:
                break
            kept = 0
            print(f"  {cat:8s}: ", end="", flush=True)
            for e in entries:
                reuse = try_reuse(cat, e, seen_ids)
                if reuse:
                    songs.append(reuse)
                    kept += 1
                    print("o", end="", flush=True)
                    continue
                try:
                    best = resolve_fresh(e) if token else None
                except RateLimited as rl:
                    limited = rl
                    break
                time.sleep(0.6)  # gentle spacing between live calls to avoid re-tripping the rate limit
                if not best:
                    dropped.append(f"[{cat}] {e['artist']} - {e['title']} (no DK match)")
                    print("_", end="", flush=True)
                    continue
                tid = best["id"]
                if tid in seen_ids:
                    dropped.append(f"[{cat}] {e['artist']} - {e['title']} (dup of another card)")
                    print("=", end="", flush=True)
                    continue
                seen_ids.add(tid)
                url = f"https://open.spotify.com/track/{tid}"
                song = {"id": tid, "title": e["title"], "artist": e["artist"],
                        "year": e["year"], "cat": cat, "url": url, "qr": qr_data_uri(url)}
                if "source" in e:
                    song["source"] = e["source"]
                songs.append(song)
                kept += 1
                fetched += 1
                print(".", end="", flush=True)
                # Save the checkpoint immediately so this track survives a later abort,
                # and remember it in-session so a --wait resume pass reuses it.
                key = key_of(cat, e["title"])
                fetch_cache[key] = song
                session_resolved[key] = song
                save_fetch_cache(fetch_cache)
            print(f"  {kept}/{len(entries)}", flush=True)
        return songs, seen_ids, dropped, fetched, limited

    fetched_total = 0
    while True:
        songs, seen_ids, dropped, fetched, limited = fetch_pass()
        fetched_total += fetched
        if not limited:
            break  # pass completed: every song was reused, fetched, or dropped legitimately
        if not wait:
            # Graceful stop. The break above stops fetching immediately, but categories or
            # entries the loop had not reached yet may still have a perfectly good
            # cached/reused resolution. Pull those in too so the rebuild reflects
            # everything resolved so far, not just what this pass happened to reach.
            for cat, entries in seed["songs"].items():
                for e in entries:
                    reuse = try_reuse(cat, e, seen_ids)
                    if reuse:
                        songs.append(reuse)

            still_missing = len(missing) - fetched_total
            print(f"\nSpotify rate limited, asks for {format_duration(limited.seconds)}. "
                  f"Progress saved: {fetched_total} fetched this run, {still_missing} still missing. "
                  "Re-run the same command later, it resumes from the checkpoint.")
            print("Tip: run with --wait to sleep out the cooldown and finish unattended.")
            if existing and len(songs) < 0.5 * len(existing):
                print(f"Only {len(songs)} songs vs {len(existing)} cached, below the safety threshold. "
                      "Kept the existing songs.js; the checkpoint alone preserves this run's progress.")
            else:
                write_db(seed["categories"], songs)
                print(f"Rebuilt songs.js from {len(songs)} resolved songs so far.")
            return
        # --wait: sleep out the cooldown (plus a buffer) and resume automatically.
        pause = limited.seconds + 120
        resume_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + pause))
        print(f"\nSpotify rate limited, asks for {format_duration(limited.seconds)}. "
              f"--wait: sleeping {format_duration(pause)} (Retry-After plus a 120 second buffer), "
              f"resuming around {resume_at}. Ctrl-C is safe, progress is checkpointed per song.")
        time.sleep(pause)
        refresh_token("resuming after cooldown")

    # Safety: never clobber a healthy deck with a much smaller one (e.g. a rate-limited run).
    if existing and len(songs) < 0.5 * len(existing):
        print(f"\nRefusing to write: only {len(songs)} songs vs {len(existing)} cached "
              "(looks rate limited). Kept the existing songs.js. Wait a few minutes and retry.")
        return

    write_db(seed["categories"], songs)
    print(f"\nTotal: {len(songs)} songs. Dropped this run: {len(dropped)}.")
    for d in dropped:
        print("  drop:", d)


def build_offline():
    # Reuse the earlier verified tracks; assign categories by matching the seed.
    verified = []
    for name in ("verified.json", "verified2.json"):
        p = HERE / name
        if p.exists():
            verified += json.loads(p.read_text(encoding="utf-8"))
    seed = json.loads(SEED.read_text(encoding="utf-8"))

    # index seed by normalized title for category (and source metadata) lookup
    cat_of = {}
    source_of = {}
    for cat, entries in seed["songs"].items():
        for e in entries:
            cat_of[norm(e["title"])] = cat
            if "source" in e:
                source_of[norm(e["title"])] = e["source"]

    songs = []
    seen = set()
    for t in verified:
        if norm(t.get("spotifyTitle", "")).find(norm(t["title"])) < 0 and norm(t["title"]) not in norm(t.get("spotifyTitle", "")):
            continue  # title mismatch, skip
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        url = f"https://open.spotify.com/track/{t['id']}"
        song = {
            "id": t["id"],
            "title": t["title"],
            "artist": t["artist"],
            "year": t["year"],
            "cat": cat_of.get(norm(t["title"]), "pop"),
            "url": url,
            "qr": qr_data_uri(url),
        }
        if norm(t["title"]) in source_of:
            song["source"] = source_of[norm(t["title"])]
        songs.append(song)
    write_db(seed["categories"], songs)
    print(f"Offline sample: {len(songs)} songs written for UI testing.")


def write_db(categories, songs):
    db = {"categories": categories, "songs": songs}
    banner = "// AUTO-GENERATED by hitster/tools/build_deck.py - do not edit by hand.\n"
    SONGS_JS.write_text(banner + "window.HITSTER_DB = " + json.dumps(db, ensure_ascii=False) + ";\n", encoding="utf-8")
    DECK_JSON.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {SONGS_JS}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-sample", action="store_true", help="build from verified*.json without Spotify credentials")
    ap.add_argument("--force-full", action="store_true", help="refetch every song, ignoring the deck.json cache")
    ap.add_argument("--wait", action="store_true", help="sleep out long Spotify cooldowns and resume automatically until done")
    args = ap.parse_args()
    if args.offline_sample:
        build_offline()
    else:
        build_online(wait=args.wait)
