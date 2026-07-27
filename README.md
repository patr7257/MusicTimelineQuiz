# Music Timeline Quiz

A self-contained, single-screen, Hitster-like music timeline game. Hear a song,
then slot it into your timeline by release year. Guess the right spot and you keep
the card. First player to the target number of cards wins.

A Hitster-like music timeline game. Not affiliated with Jumbo or the official
Hitster board game.

- Vinyl Lounge look: wood console, cream record-sleeve cards, Righteous display font
  (bundled in `fonts/`), themed scrollbars, fluid sizing.
- 2 to 4 players, names entered per player.
- Song categories plus All Mixed (Rock, Pop, Hip-Hop & R&B, Dance & Electronic, Soul/Funk/
  Disco, BANGERTIME, Happy Days, Danish, Festival), plus a year-span slider in setup to
  limit the deck to a release-year range.
- QR codes link straight to the Spotify track and are baked into the database. The song QR
  can be shown fullscreen ("Show QR big"), and "Play here" plays the track through a hidden
  Spotify embed without revealing the answer.
- Current player sits at the front; the other players are docked to the left and right
  edges of the stage, never overlapping the music hub. Tap another player's seat to peek at
  their timeline read-only, then "Back to turn".
- The song is drawn automatically when a turn starts (no Draw button). Place it by dragging
  the card from the hub into a gap in your timeline, and re-drag it freely until you lock in.
- Coins per player, spendable to steal a card on someone else's wrong guess, or to
  skip a song you already know without giving up your free skip. A player one card from
  winning cannot steal (their seat shows "At match point"). A steal costs its coin only when it
  still stands after the window (uncontested, or the winner of a same-gap spin wheel).
- Fullscreen toggle in the top bar.
- Optional phone play (join with a game id + password; the join QR pops up automatically
  when the game starts): place from your phone, make one bonus guess per round for a coin,
  and press STEAL during a steal window. Hidden automatically when the backend is not set
  up (the game stays fully playable on one screen).

## How to run

No build, no server. Just open `index.html` in a browser.

PowerShell (opens in your default browser):

```
cd "C:\Users\pr\repos\hitster"; ii index.html
```

## How to play

1. Pick the number of players, enter names, choose categories, cards-to-win, and
   coins per player (0 to 5, default 3), press Start.
2. Each player starts with one free card (its year is shown) as the seed of their timeline,
   plus their starting coins.
3. Your turn starts automatically: a QR code appears in the center. Its year and category
   stay hidden while you guess.
4. Scan the QR with your phone camera and press play in Spotify. Do not read the title, just
   listen.
5. Drag the card from the hub into a gap in your own timeline where you think it fits by
   release year. Gaps open up while you drag. Re-drag the card as often as you like to move
   it; a drop outside any gap keeps your previous choice.
6. Press Lock in answer. If any opponent still has a coin (and is not one card from winning),
   a 10 second steal window opens with a countdown next to the hub. The number holds at 10 for
   a 2 second grace before it starts dropping.
7. During the steal window, every eligible opponent can press Steal on their seat card (or from
   their phone). A press registers them for a steal but costs nothing yet and does NOT pause
   the countdown, so several opponents can register in the same window. Who pressed stays
   hidden until the countdown ends (only your own phone confirms you are in), so nobody can
   copy a press. Pressing again does nothing. Press Reveal now to skip the rest of the wait.
8. When the countdown ends: if nobody registered, the round resolves as usual. Otherwise each
   registered stealer, in the order they pressed, picks a gap in your timeline, one at a time
   and with no time limit. A stealer on a phone picks privately there (the shared screen only
   shows whose pick it is, never the spot); a stealer without a phone taps a gap on the shared
   screen and confirms. If two or more stealers pick the same gap, a spin
   wheel picks who keeps that gap; the others on that gap are dropped. Every steal that still
   stands then costs its owner one coin (win or lose, and even if your own placement was right).
   Resolution: if your slot was right you keep the card and the standing steals win nothing (they
   still paid); if your slot was wrong, the first standing steal (in press order) whose gap was
   right wins the card. If nobody was right, the card is discarded.
9. Instead of guessing, you can press Skip duplicate (free, if you already know the song) or
   Skip with coin (costs you one of your own coins) to discard the card and draw a fresh one.
10. Press Next player. The other players orbit round and the next player's song is drawn.
11. First to the target wins. When the first player reaches the target, any other player who
    is one card away and has had fewer turns gets one final equalizing turn. If they tie at
    the top, a sudden-death round decides it (or, by build config, the win is shared). If the
    deck runs out first, most cards wins.

## Playing from phones

When the backend is available the host opens on a **dashboard**: start a new game (with a
game name and password), or continue a saved one. Every state change is saved online, so you
can **Pause** (top bar) back to the dashboard and **Resume** later, even from a different
screen. Resuming rotates a host token, so a second screen taking over fences out the first
(the old screen shows a "opened elsewhere, take over?" prompt).

Players join from their phones anytime by scanning the **Phones** QR (it encodes the game id;
the password is shown alongside). On the phone a player can, on their own turn:

- **Place**: drag the new card into a gap, then lock in, all from the phone.
- **Bonus guess** (one per round, current player only, worth a coin):
  - **Artist + title**: type both; both must match.
  - **Where is it from**: pick movie, musical, or Disney, and type the source name (only
    offered when the current card actually has that metadata).
- **STEAL**: during a steal window an eligible opponent presses STEAL to register, then picks a
  gap when the pick phase reaches them. The coin is charged only if their steal still stands.

The bonus coin pays out only when the guess was right AND the current player's own placement
was right; steals never pay a coin. Matching is typo-tolerant (small edit-distance allowance,
punctuation, apostrophes, and accents ignored, parenthetical alt titles accepted), with no
partial credit. The phone never receives the answer: the server projects an answer-free view
(no deck, no current card, no guess text) from the host's authoritative state.

Phones send intents; the PC host is the only writer of game state and consumes intents on a
poll loop. This runs through the website's own backend under `/api/hitster/games/**`, backed
by an Upstash Redis database (Vercel Marketplace). The full endpoint contract, state shape,
projection, and sync cadences live in **`PROTOCOL.md`** next to this file.

**Required on Vercel** (either naming scheme works, the plain Upstash pair takes priority if
both are set):

- `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`, or
- `KV_REST_API_URL` / `KV_REST_API_TOKEN`

If neither pair is configured (or the API is unreachable, or the page is opened as a local
`file://` document), the game detects this once at startup and shows the plain offline setup
with zero persistence and no phone features. The rest of the game, including scoring, steals,
the steal wheel, the equalizer, and skips, keeps working entirely on one screen.

## Note on direct Spotify links

The QR links straight to the Spotify track, so whoever scans will see the song title on
their phone. Agree to just press play and not read the title. The shared screen never
shows the answer until you reveal.

## Building the full song database

The game reads `songs.js`, which is generated by `tools/build_deck.py` from the curated
`tools/deck-seed.json`. Two modes:

### Full deck (needs a free Spotify app)

Resolves every seed song to a real, Denmark-available Spotify track and bakes a QR code
for each into the database. Needs Spotify API credentials (client credentials flow, no
user login). The script prompts for them and stores nothing.

1. Create a free app at https://developer.spotify.com/dashboard (any name, any redirect URI).
2. Copy its Client ID and Client secret.
3. Run and paste them at the prompts:

```
cd "C:\Users\pr\repos\hitster"; python tools\build_deck.py
```

### Offline sample (no credentials)

Builds a small database from the already-verified tracks, for testing the UI:

```
cd "C:\Users\pr\repos\hitster"; python tools\build_deck.py --offline-sample
```

## Expanding the deck

To add songs, work through these steps in order (from the repo root):

1. Edit `tools/deck-seed.json`: append entries to the relevant category arrays. A song is
   `{ "title", "artist", "year" }`; disney and movie entries also need
   `"source": { "type": "disney" | "movie" | "musical", "name": "..." }`.
2. Validate the seed before building:

   ```
   python tools/validate_seed.py
   ```

   It fails (exit 1) on empty fields, a year outside 1940 to 2026, a disney/movie entry with no
   source, or any duplicate song (same title + artist) anywhere in the file, and prints a
   per-category count and a per-decade histogram. Fix everything it lists until it is clean.
3. Build the deck. This is incremental: only new seeds are fetched, already-resolved tracks
   are reused from the fetch cache. Needs Spotify credentials (see above); `--wait` slows the
   requests down to stay under Spotify's rate limit:

   ```
   python tools/build_deck.py --wait
   ```
4. Audit the built deck against real Spotify metadata (no credentials needed) and fix any
   flagged track (wrong artist, wrong title, or a suspicious release year) back in the seed,
   then rebuild:

   ```
   python tools/audit_deck.py
   ```
5. Sync the built game into the website repo (a sibling clone of `patrickrobelweb`,
   which serves the game at patrickrobel.dk/hitster) and commit:

   ```
   cd "C:\Users\pr\repos\patrickrobelweb\website"; pnpm sync:hitster
   ```

   Then commit `tools/deck-seed.json` and the regenerated `songs.js` here, and the
   synced `website/public/hitster/` files in the website repo.

## Files

- `index.html` : the whole host game (HTML + CSS + JS)
- `guess.html`  : the phone page, served at `/hitster/guess?game=GAMEID`
- `PROTOCOL.md` : the v3 contract between host, phone, and API (state shape, projection,
  intents, endpoints, localStorage keys, sync cadences, locked game rules)
- `songs.js`   : AUTO-GENERATED database, `window.HITSTER_DB = { categories, songs }`
  (optionally carries a `source: { type, name }` field per song for the "where is it from"
  bonus guess)
- `qrcode.js`  : runtime QR fallback (baked QR data URIs are used when present)
- `tools/deck-seed.json` : curated songs per category (edit to change the deck; a song can
  carry an optional `source: { type: "movie" | "musical" | "disney", name }` field)
- `tools/build_deck.py`  : resolves Spotify IDs + bakes QR codes, writes `songs.js`, carries
  any `source` field from the seed through to the generated entry
- `tools/inject-sources.mjs` : patches `source` fields from `deck-seed.json` onto the already
  committed `songs.js` in place, for when new sources are added to the seed but a full
  Spotify-backed rebuild is not available. Run with `node tools/inject-sources.mjs`.
- `tools/enrich_artists.py` : adds missing co/featured artists to every card's artist credit
  as "(feat. X)" (so guessing any credited artist scores), credential-free via the public
  Spotify embed pages; patches `songs.js`, `deck.json`, `fetch-cache.json`, and
  `deck-seed.json` in lockstep. Dry-run by default; `--apply` writes.
- `tools/validate-tracks.mjs`, `tools/build-songs.mjs` : the earlier oEmbed-based verifier

The website side lives in the separate `patrickrobelweb` repo
(`website/src/lib/hitster-redis.ts`, `website/src/app/api/hitster/`): it holds the
Redis-backed API the phone page and the game talk to; its `website/scripts/sync-hitster.mjs`
copies `index.html`, `guess.html`, `qrcode.js`, and `songs.js` from this repo (expected as a
sibling clone) into `website/public/hitster/` for deploy, run it after any change here.

## Saved games: E2E test games and the wipe script

Games are saved online (Upstash Redis) so a host can resume with the continuation password.
Normal saved games get roughly a week of persistence and show up in the saved-games list.

- **E2E guard (issue #36):** a game whose name or any player name contains "e2e"
  (case insensitive) is treated as a nightly automated test run, not a real saved game. It is
  never added to the saved-games list, and it gets a 1 hour TTL instead of the normal
  persistence, so it disappears on its own. This is enforced server-side (every route that
  writes game data checks this), and a caller can also opt in explicitly by sending
  `ephemeral: true` in the create-game request body.
- **Admin delete (single game):** `DELETE /api/hitster/games/[gameId]` with the master password
  in an `X-Hitster-Admin` header removes one saved game completely (meta, state, claims, tent,
  intents, and its saved-games list entry) and returns `{deleted: true, gameId}`. The password
  comes from the `HITSTER_ADMIN_PASSWORD` env var (server-side only, set in Vercel and in a
  local `website/.env.local`, never `NEXT_PUBLIC`). If the env var is unset every request gets
  403 `admin password not configured`; wrong password gets 403; unknown game gets 404. The
  trash icon in the saved-games UI uses this endpoint.
- **Wipe script:** for occasionally clearing out saved games by hand (leftover E2E games from
  before this guard existed, or any other cleanup), use `scripts/wipe-hitster-games.ps1` in
  this repo. It prompts for the Upstash REST URL and token (never pass them as arguments, they
  are never written to disk), prints a dry run of every game found (id, name, players,
  created/updated time), then asks for an explicit "yes" before deleting anything. Only keys
  starting with `hitster:` are ever touched.

Run it with:

```
cd "C:\Users\pr\repos\hitster"; .\scripts\wipe-hitster-games.ps1
```

It will prompt for, in order: the Upstash REST URL, then the Upstash REST token (input hidden).
Both values live in the Vercel project's environment variables (`KV_REST_API_URL` /
`KV_REST_API_TOKEN`, or `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`).
