# Hitster v3 protocol (issue #28)

Contract between the host screen (index.html), the phone client (guess.html), and the
API (website/src/app/api/hitster/games/**, lib website/src/lib/hitster-redis.ts).
All three implementation lanes build against THIS file. Do not change shapes or names
unilaterally; if a change is needed, the orchestrator updates this file first.

## Core model

- The PC host is the ONLY writer of authoritative game state. Phones send intents;
  the host consumes them on a poll loop, mutates its in-memory state, and republishes.
- Answers never reach phones. The full state stores the remaining deck as song IDs only
  and the current card object (with answers) for the host. The phone endpoint runs the
  stored state through an explicit allowlist projection, which excludes the deck, the
  current card, and its id entirely.
- Change detection: server-assigned monotonically increasing `version` on every state
  write. Phone GET passes `?v=` and receives `{version, unchanged:true}` when nothing
  changed.
- Auth: a per-game dummy `password` gates resume and phone join. A rotating `hostToken`
  (minted on create and on every resume) gates full-state read/write; resuming rotates
  it, fencing out any older host tab. Phones get a per-player `playerToken` on claim,
  required on every intent.

## Redis keys

Game ids: 6 chars from `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (no 0/O/1/I/L), validated
with the existing `isValidRoomCode` (`/^[A-Z0-9]{4,8}$/`).

| Key | Type | Value | TTL |
|---|---|---|---|
| `hitster:games:index` | hash | field = gameId, value = JSON `{gameId, name, players: string[], status, round, createdAt, updatedAt}` | 30 d, refreshed on write; entries lazily pruned on dashboard GET when older than 7 d or meta missing |
| `hitster:game:{id}:meta` | string JSON | `{gameId, name, password, hostToken, hostInstanceId, status, createdAt, updatedAt}` (password plaintext, dummy gate) | 7 d rolling |
| `hitster:game:{id}:state` | string JSON | FullGameState (below), written only via host PUT, contains `version` | 7 d rolling |
| `hitster:game:{id}:claims` | hash | field = playerIdx `"0"`..`"3"`, value = JSON `{deviceId, playerToken, name, at}`; written with HSETNX | 7 d rolling |
| `hitster:game:{id}:intents:{round}` | list | append-only JSON intent entries (below), RPUSH only | 24 h |
| `hitster:game:{id}:tent` | string JSON | `{playerIdx, round, slot, at}` last-writer-wins tentative drag slot | 24 h |

Durable facts (locked slot, pending guesses, registered stealers and their picks,
`players[i].claimed`) always end up inside `:state`. The claims/intents/tent keys are transport
and race arbitration only. The host keeps the multi-steal machine (registered list in press
order, per-stealer picks, the current-picker index, and the countdown-vs-picking sub-phase) in
its opaque `_host` extras inside `:state`; only the projected `steal` block above is public.

## FullGameState (stored in `:state`)

The server validates only the envelope it needs (players 1-4 with valid names/idx,
`phase` string <= 20 chars, `status` enum, `round`/`current` finite ints, total size
<= 200 KB, else 413). Everything else is host-owned and opaque.

```jsonc
{
  "gameId": "ABC234", "name": "Friday night", "version": 41,
  "status": "lobby" | "active" | "paused" | "finished",
  "createdAt": 0, "updatedAt": 0,
  "settings": { "target": 10, "coinsPerPlayer": 3, "cats": ["rock","pop"] },
  "players": [{
    "idx": 0, "name": "Patrick", "color": "#5be0c9", "coins": 3,
    "timeline": [{ "id": "...", "title": "...", "artist": "...", "year": 1971, "cat": "rock" }],
    "roundsPlayed": 4, "claimed": true
  }],
  "deckIds": ["id1", "id2"],            // remaining deck, top = last. NEVER projected
  "current": 0, "round": 7,
  "phase": "lobby"|"place"|"steal"|"revealed"|"equalizer"|"over",
  "card": { "id": "...", "title": "...", "artist": "...", "year": 1999, "cat": "pop",
            "source": { "type": "movie", "name": "8 Mile" } } | null,   // NEVER projected
  "placement": { "tentativeSlot": 2, "lockedSlot": null, "lockedAt": 0 } | null,
  "steal": {
    "windowEndsAt": 1760000000000,      // absolute host-clock ms; counts down in the countdown
                                        // sub-phase only, reports now() (0 left) while picking
    "eligibleIdx": [1, 3],              // coins >= 1, not current, timeline < target - 1
    "presses": [{ "playerIdx": 1, "slot": null, "at": 0 }], // one entry per REGISTERED stealer;
                                        // slot stays null until that stealer's pick is confirmed
    "wheel": { "slot": 2, "candidates": [1, 3], "winnerIdx": null } | null
  } | null,
  "pendingGuesses": [{
    "round": 7, "playerIdx": 0, "type": "artist-title" | "source",
    "artist": "?", "title": "?", "sourceType": "movie", "sourceName": "?",
    "at": 0, "judged": null | "correct" | "wrong", "coinAwarded": false
  }],
  "equalizer": { "firstToTarget": 0, "firstToTargetRounds": 9, "queueIdx": [2] } | null,
  "result": { "correct": false, "stolenBy": 3, "attempted": true } | null
}
```

Timeline entries are revealed cards, safe to project. Deck restore on resume: the host
maps `deckIds` and timeline ids back through `window.HITSTER_DB`, silently dropping ids
that no longer exist.

Game rules encoded host-side (locked with Patrick):
- Placement is by the turn player only (phone or PC).
- Bonus coin: only the CURRENT player's guess counts. It renders as a PENDING chip and
  pays +1 coin at reveal only when the guess was correct AND the player's own placement
  was correct. Steals never pay coins. Guess intents from non-current players are
  ignored by the host.
- A player at `target - 1` cards cannot steal.
- Multi-steal window (batch 7): after Lock in, a 10 s countdown runs. Every eligible opponent
  may press STEAL; a press only REGISTERS them (marks their seat), costs no coin, and does NOT
  pause the countdown, so several register in one window. When the countdown ends (or Reveal now
  is pressed), each registered stealer, in the order they pressed, picks a gap one at a time
  (host tap or phone pick). If two or more picked the SAME gap, a spin wheel picks one keeper per
  contested gap and voids the others on that gap. A steal that STANDS after conflict resolution
  costs its owner exactly 1 coin (wheel losers pay nothing); the coin is charged at resolution,
  never at press time, and is charged even when the current player's own placement turns out
  correct (the steal then simply wins nothing). Resolution order is unchanged: the current
  player's placement is judged first; if correct they keep the card, else the first standing
  steal (press order) on a correct gap wins it.
- Equalizer: when the first player reaches target, every other player at `target - 1`
  with fewer `roundsPlayed` gets one final turn; ties settle by sudden death cycles.

## Phone projection (projectForPhone, explicit allowlist)

```jsonc
{
  "version": 41, "gameId": "ABC234", "name": "Friday night",
  "status": "active", "round": 7, "phase": "place", "currentPlayerIdx": 0,
  "players": [{ "idx": 0, "name": "Patrick", "color": "#5be0c9", "coins": 3,
                "cards": 4, "timeline": [{ "year": 1971, "title": "...", "cat": "rock" }],
                "roundsPlayed": 4, "claimed": true }],
  "guessOpen": true,
  "hasSource": true, "sourceTypes": ["movie","musical","disney"],
  "placement": { "tentativeSlot": 2, "locked": false },
  "steal": { "open": true, "endsAt": 1760000000000, "eligibleIdx": [1,3],
             "presses": [{ "playerIdx": 1, "slot": null }],   // one per registered stealer
             "wheel": { "slot": 2, "candidates": [1,3], "winnerIdx": null } } | null,
  "pendingGuesses": [{ "playerIdx": 0, "type": "artist-title", "judged": null }],
  "equalizer": { "queueIdx": [2] } | null
}
```

Excluded forever: `deckIds`, `card` (including its id), `settings.cats`, password,
tokens, and the guess TEXT of any player (only `type` and `judged` are projected).
`hasSource` is true when the current card has a `source`; `guessOpen` is
`phase === "place" && status === "active"`.

## API routes

All routes: `runtime = "nodejs"`, `dynamic = "force-dynamic"`, 503
`{error:"backend not configured"}` when Redis env is unset, 400 `{error:"invalid json"}`
on unparseable bodies. Hand-rolled validation in the style of the current routes, no new
deps (`crypto.randomBytes(16).toString("hex")` for tokens). Text fields max 80 chars,
names max 24, game name 1-40, password 4-32 printable ASCII.

### `POST /api/hitster/games`
Body `{ name, password, state: FullGameState }` (host builds the initial lobby state).
Server generates gameId (SET meta NX retry loop), hostToken, hostInstanceId; forces
`state.version = 1`; writes meta + state + index.
200 `{ gameId, hostToken, version: 1 }`. 400 invalid body, 413 too large.

### `GET /api/hitster/games`
Dashboard list, no auth. HGETALL index, prune stale, return
`[{gameId, name, players, status, round, updatedAt, createdAt}]` sorted updatedAt desc.

### `POST /api/hitster/games/[gameId]/resume`
Body `{ password }`. 404 no meta, 403 wrong password. Mints NEW hostToken +
hostInstanceId (double-host fence), refreshes TTLs.
200 `{ hostToken, version, state }`.

### `GET /api/hitster/games/[gameId]/state`
Header `x-hitster-host-token`. 401 mismatch. 200 `{ version, state }`.
(Host page reload without retyping the password.)

### `PUT /api/hitster/games/[gameId]/state`
Header `x-hitster-host-token`. Body `{ baseVersion, state }`.
401 token mismatch; 409 `{ currentVersion }` when `stored.version !== baseVersion`;
envelope validation; writes `version = baseVersion + 1`, `updatedAt = Date.now()`;
updates meta.status + index; refreshes all TTLs (the 7 d rolling save).
200 `{ version }`.

### `GET /api/hitster/games/[gameId]/phone?pw=...&v=41`
404 no game; 403 wrong pw; `version === v` gives 200 `{ version, unchanged: true }`;
else 200 `{ version, state: projectForPhone(state) }`. Use one pipelined Redis round
trip for meta + state.

### `POST /api/hitster/games/[gameId]/claim`
Body `{ pw, playerIdx: 0-3, deviceId: string(8-64) }`. 403 wrong pw.
HSETNX claims. Won: 200 `{ playerToken }`. Lost with same deviceId: 200 with the
existing token (idempotent reload). Lost, other device: 409 `{ error: "taken" }`.
Also RPUSH a `{type:"claim", playerIdx}` intent for prompt host pickup.

### `DELETE /api/hitster/games/[gameId]/claim`
Header `x-hitster-host-token`, body `{ playerIdx }`. HDEL. 200 `{ok:true}`.
(Host releases a slot.)

### `POST /api/hitster/games/[gameId]/intent`
Body `{ playerIdx, playerToken, round, type, ...payload }`. Auth: HGET claims by idx,
403 token mismatch. `round` finite int >= 0.

| type | payload | behavior |
|---|---|---|
| `tentative` | `{slot: int 0-30}` | SET `:tent` `{playerIdx, round, slot, at}` (LWW). Phone throttles to ~300 ms |
| `lockin` | `{slot}` | RPUSH intents; 409 if this player already locked in this round |
| `guess` | `{guessType:"artist-title"\|"source", artist?, title?, sourceType?, sourceName?}` (field rules copied from the old guess route; named guessType because the outer `type` is the intent kind) | RPUSH; 409 if already guessed this round |
| `steal-press` | `{}` | RPUSH; 409 on repeat per player/round. Multiple DIFFERENT players may press in one window; each press registers that player as a stealer (the host no longer stops at the first) |
| `steal-slot` | `{slot}` | RPUSH always; the host takes the LAST slot per player, and applies it only to the stealer whose turn it currently is in the pick phase. A slot sent early (during the countdown) waits in the round list and is applied by reprocessing once it is that player's turn |

200 `{ok:true}`. Entries stored as `{type, playerIdx, round, at, ...payload}`,
EXPIRE 24 h after push.

### `GET /api/hitster/games/[gameId]/intents?round=N`
Header `x-hitster-host-token`. Pipelines LRANGE intents + GET tent + HGETALL claims.
200 `{ intents: [...], tentative: {...} | null, claims: { "0": {deviceId, name, at} } }`
with playerTokens STRIPPED from claims.

The old `room/route.ts` and `guess/route.ts` are DELETED (no back-compat).

## Client sync loops

Host:
- Every state mutation triggers a debounced (250-500 ms) PUT with
  `baseVersion = lastAckedVersion`. On 401/409 stop writing and show a
  "game was opened elsewhere, take over?" overlay (take over = password to resume,
  adopt server state).
- Polls `GET intents?round=` every 1.5 s while active (3 s in lobby for claims).
  Reprocessing a whole round list after reload is safe: lockin/guess/steal-press are
  deduped per player+type, tentative/steal-slot are last-wins.
- Steal window is an absolute `windowEndsAt`; on reload at ANY point of the steal phase
  (countdown or picking) the host restarts a fresh countdown (STEAL_SECONDS, currently 10 s):
  it discards half-collected registrations, picks, and wheel state and recomputes eligibility
  from current coins. No coin is double-charged because coins are only spent when a steal STANDS
  at resolution, never earlier. Worst case on reload: the steal phase replays from the countdown.
- localStorage `hitster_host` = `{gameId, hostToken}`.

Phone:
- Polls `GET phone?pw&v` every 2 s; re-renders only on version change (keep guess.html's
  computeRenderKey/applyRender gate so typing is never wiped).
- Own drag renders optimistically; `tentative` is fire-and-forget; `lockin` waits for
  the 200 then shows locked state. 409 anywhere is treated as "already done", success.
- localStorage `hitster_phone_{gameId}` = `{pw, deviceId, playerIdx, playerToken}`;
  reload rejoins silently via the idempotent claim.

## URLs

- Host: `/hitster` (dashboard first when the backend is up; plain local setup on
  file:// or when Redis is unconfigured).
- Phone: `/hitster/guess?game=GAMEID` (existing rewrite `/hitster/guess` serves
  guess.html). QR on the host encodes `location.origin + "/hitster/guess?game=" + id`.
