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
    if resp.status_code == 429 and tries < 2:
        wait = min(int(resp.headers.get("Retry-After", "2")) + 1, 25)
        print(f"[rate limited {wait}s]", end="", flush=True)
        time.sleep(wait)
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
    return pick_best(_do_search(token, f"{title} {artist}", market), title, artist)


def pick_best(items, title, artist):
    nt, na = norm(title), norm(artist)
    best, best_score = None, -1
    for it in items:
        cand_title = norm(it.get("name", ""))
        cand_artists = norm(" ".join(a.get("name", "") for a in it.get("artists", [])))
        title_ok = nt and (nt in cand_title or cand_title in nt)
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


def build_online():
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    force_full = "--force-full" in sys.argv

    # Incremental: reuse everything already resolved (from a previous deck.json) and
    # only fetch songs still missing. This keeps request counts tiny so Spotify's
    # rate limit is not tripped, and never re-fetches what already works.
    existing = {}
    if not force_full and DECK_JSON.exists():
        try:
            prev = json.loads(DECK_JSON.read_text(encoding="utf-8"))
            for s in prev.get("songs", []):
                existing[s["cat"] + "|" + norm(s["title"])] = s
        except Exception:
            existing = {}

    def key_of(cat, title):
        return cat + "|" + norm(title)

    missing = [(cat, e) for cat, entries in seed["songs"].items() for e in entries
               if key_of(cat, e["title"]) not in existing]
    print(f"Reusing {len(existing)} cached tracks; {len(missing)} to fetch"
          + (" (--force-full: refetching all)" if force_full else "") + ".")

    token = None
    if missing or force_full:
        print("Spotify credentials (from https://developer.spotify.com/dashboard):")
        client_id = os.environ.get("SPOTIFY_CLIENT_ID") or input("  Client ID: ").strip()
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET") or getpass("  Client secret (hidden): ").strip()
        token = get_token(client_id, client_secret)
        print("Token OK. o=reused  .=fetched  _=no match  ==duplicate\n", flush=True)
    else:
        print("Nothing to fetch, rebuilding songs.js from cache.\n")

    songs = []
    seen_ids = set()
    dropped = []
    for cat, entries in seed["songs"].items():
        kept = 0
        print(f"  {cat:8s}: ", end="", flush=True)
        for e in entries:
            reuse = existing.get(key_of(cat, e["title"])) if not force_full else None
            if reuse and reuse.get("id") and reuse.get("qr") and reuse["id"] not in seen_ids:
                seen_ids.add(reuse["id"])
                songs.append(reuse)
                kept += 1
                print("o", end="", flush=True)
                continue
            best = resolve(token, e["title"], e["artist"]) if token else None
            time.sleep(0.4)  # gentle spacing between live calls to avoid re-tripping the rate limit
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
            songs.append({"id": tid, "title": e["title"], "artist": e["artist"],
                          "year": e["year"], "cat": cat, "url": url, "qr": qr_data_uri(url)})
            kept += 1
            print(".", end="", flush=True)
        print(f"  {kept}/{len(entries)}", flush=True)

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

    # index seed by normalized title for category lookup
    cat_of = {}
    for cat, entries in seed["songs"].items():
        for e in entries:
            cat_of[norm(e["title"])] = cat

    songs = []
    seen = set()
    for t in verified:
        if norm(t.get("spotifyTitle", "")).find(norm(t["title"])) < 0 and norm(t["title"]) not in norm(t.get("spotifyTitle", "")):
            continue  # title mismatch, skip
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        url = f"https://open.spotify.com/track/{t['id']}"
        songs.append({
            "id": t["id"],
            "title": t["title"],
            "artist": t["artist"],
            "year": t["year"],
            "cat": cat_of.get(norm(t["title"]), "pop"),
            "url": url,
            "qr": qr_data_uri(url),
        })
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
    args = ap.parse_args()
    if args.offline_sample:
        build_offline()
    else:
        build_online()
