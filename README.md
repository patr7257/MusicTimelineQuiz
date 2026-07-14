# Hitster: music quiz

A self-contained, single-screen music quiz in the style of Hitster. Hear a song,
then slot it into your timeline by release year. Guess the right spot and you keep
the card. First player to the target number of cards wins.

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
- Hitster coins per player, spendable to steal a card on someone else's wrong guess, or to
  skip a song you already know without giving up your free skip. A player one card from
  winning cannot steal (their seat shows "At match point").
- Fullscreen toggle in the top bar.
- Optional phone play (join with a game id + password; the join QR pops up automatically
  when the game starts): place from your phone, make one bonus guess per round for a coin,
  and press STEAL during a steal window. Hidden automatically when the backend is not set
  up (the game stays fully playable on one screen).

## How to run

No build, no server. Just open `index.html` in a browser.

PowerShell (opens in your default browser):

```
cd "C:\Users\pr\repos\patrickrobelweb\hobby-projects\hitster"; ii index.html
```

## How to play

1. Pick the number of players, enter names, choose categories, cards-to-win, and Hitster
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
   a 10 second steal window opens with a countdown next to the hub.
7. During the steal window, an eligible opponent can press Steal on their seat card. It costs
   them a coin immediately, win or lose. They then tap a different gap in your timeline (the
   countdown pauses while they choose) and confirm. Each opponent may steal at most once per
   round, and several can steal in the same round. Press Reveal now to skip the wait. If two
   or more stealers pick the same gap, a spin wheel picks who gets that attempt.
8. When the countdown ends (or everyone who can steal has done so): if your slot was right,
   you keep the card and every steal attempt fails. If your slot was wrong, the first opponent
   (in the order they locked their steal) whose gap was right wins the card. If nobody was
   right, the card is discarded.
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
- **STEAL**: during a steal window an eligible opponent presses STEAL and picks a gap.

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
cd "C:\Users\pr\repos\patrickrobelweb\hobby-projects\hitster"; python tools\build_deck.py
```

### Offline sample (no credentials)

Builds a small database from the already-verified tracks, for testing the UI:

```
cd "C:\Users\pr\repos\patrickrobelweb\hobby-projects\hitster"; python tools\build_deck.py --offline-sample
```

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
- `tools/validate-tracks.mjs`, `tools/build-songs.mjs` : the earlier oEmbed-based verifier

The website side (`website/src/lib/hitster-redis.ts`, `website/src/app/api/hitster/`) holds the
Redis-backed API the phone page and the game talk to; `website/scripts/sync-hitster.mjs` copies
`index.html`, `guess.html`, `qrcode.js`, and `songs.js` into `website/public/hitster/` for
deploy, run it after any change here.
