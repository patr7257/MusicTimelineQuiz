# Hitster: music quiz

A self-contained, single-screen music quiz in the style of Hitster. Hear a song,
then slot it into your timeline by release year. Guess the right spot and you keep
the card. First player to the target number of cards wins.

- 2 to 4 players, names entered per player.
- 7 song categories plus All Mixed: Rock, Pop, Hip-Hop & R&B, Dance & Electronic,
  Soul/Funk/Disco, BANGERTIME, Happy Days. All span 1970 to 2026.
- QR codes link straight to the Spotify track and are baked into the database.
- Current player sits at the front; the other players are docked to the left and right
  edges of the stage, never overlapping the music hub.
- Hitster coins per player, spendable to steal a card on someone else's wrong guess, or to
  skip a song you already know without giving up your free skip.
- Fullscreen toggle in the top bar, and drag-and-drop (or tap) to place the drawn card.
- Optional bonus guesses from players' phones: while a card is being placed, the current
  player can use their own phone for one extra guess per round to earn a Hitster coin (see
  "Bonus guesses from phones" below). Hidden automatically if the backend is not set up.

## How to run

No build, no server. Just open `index.html` in a browser.

PowerShell (opens in your default browser):

```
cd "C:\Users\pr\repos\patrickrobelweb\hitster"; ii index.html
```

## How to play

1. Pick the number of players, enter names, choose a category, cards-to-win, and Hitster
   coins per player (0 to 5, default 3), press Start.
2. Each player starts with one free card (its year is shown) as the seed of their timeline,
   plus their starting coins.
3. On your turn: press Draw song. A QR code appears in the center. Its category is hidden
   while you are guessing.
4. Scan the QR with your phone camera and press play in Spotify. Do not read the title, just
   listen.
5. Tap a gold + slot in your own timeline, or drag the card down from the hub onto a slot,
   where you think the song fits by release year. You can change your mind before locking in.
6. Press Lock in answer. If any opponent still has a coin, a 5 second steal window opens
   with a countdown next to the hub.
7. During the steal window, any opponent holding at least one coin can press Steal on their
   seat card. It costs them a coin immediately, win or lose. They then pick a different slot
   in your timeline (the countdown pauses while they choose) and confirm. Each opponent may
   steal at most once per round, and several opponents can steal in the same round. You can
   press Reveal now to skip the rest of the wait.
8. When the countdown ends (or everyone who can steal has done so): if your slot was right,
   you keep the card and every steal attempt fails. If your slot was wrong, the first
   opponent (in the order they locked their steal) whose guess was right wins the card into
   their own timeline instead. If nobody was right, the card is discarded.
9. Instead of guessing, you can press Skip duplicate (free, if you already know the song) or
   Skip with coin (costs you one of your own coins) to discard the card and draw a fresh one.
10. Press Next player. The other players orbit round and the next player comes to the front.
11. First to the target (or most cards when the deck runs out) wins.

## Bonus guesses from phones

While the current player is listening (the "place" phase, before they lock in a slot), they
can make one extra guess per round from their own phone to earn a Hitster coin:

- **Artist + title**: type both the artist and the song title; both must match.
- **Where is it from**: pick movie, musical, or Disney, and type the source name (only shown
  when the current card actually has that metadata).

Matching is typo-tolerant (small edit-distance allowance, punctuation and accents ignored),
but there is no partial credit and no reveal of the right answer while the round is still
being played; the main screen only shows whether the guess earned a coin.

Setup: press the **Phones** button in the top bar (shown only when the feature is available)
to display a QR code and a room code. Each player scans it once at the start of the game with
their phone camera, taps their name on the page it opens, and then only sees a guess form when
it is genuinely their turn with an open guess window; otherwise it shows a quiet "waiting"
screen. Room state never contains the answer (artist, title, or source name), only whose turn
it is and whether guessing is open.

This runs through the website's own backend: a Vercel API at `/api/hitster/room` and
`/api/hitster/guess`, backed by an Upstash Redis database (Vercel Marketplace). The static
game page and the phone page are served from the same origin as the API, so no configuration
is needed beyond the environment variables below.

**Required on Vercel** (either naming scheme works, the plain Upstash pair takes priority if
both are set):

- `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN`, or
- `KV_REST_API_URL` / `KV_REST_API_TOKEN`

If neither pair is configured (or the API is unreachable, or the page is opened as a local
`file://` document), the game detects this once at startup and silently hides the Phones
button and all bonus-guess UI. The rest of the game, including scoring, steals, and skips,
keeps working exactly as before.

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
cd "C:\Users\pr\repos\patrickrobelweb\hitster"; python tools\build_deck.py
```

### Offline sample (no credentials)

Builds a small database from the already-verified tracks, for testing the UI:

```
cd "C:\Users\pr\repos\patrickrobelweb\hitster"; python tools\build_deck.py --offline-sample
```

## Files

- `index.html` : the whole game (HTML + CSS + JS)
- `guess.html`  : the phone bonus-guess page, served at `/hitster/guess?room=CODE`
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
