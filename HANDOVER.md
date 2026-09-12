# HANDOVER

## 1. Date, branch, PR, CI
- Date: 2026-09-12
- Branch: `feat/christmas-category` (squash-merged to `main` as `360efdb`, local and remote copies deleted at close)
- PR: MusicTimelineQuiz #14 (Christmas category), squash-merged. Website side: PatrickRobelWeb #178, squash-merged as `c15e399`
- CI: repo has no CI checks; verification was `validate_seed.py`, `audit_deck.py christmas`, `node --check songs.js`, and fetching the live `songs.js` back off production

## 2. TLDR of session outcome
Done, and live on production:
- New filterable deck category `christmas` "Christmas" 🎄 `#2e9e5b`, 150 cards, 1942 to 2025.
- 100 English cards: the standards (Bing Crosby, Nat King Cole, Brenda Lee, Elvis, Darlene Love, Eartha Kitt), the 70s and 80s radio canon (Slade, Wizzard, Elton John, Wham!, Band Aid, Queen, Chris Rea, Pogues, Shakin' Stevens), the soul and hip-hop side (Donny Hathaway, Stevie Wonder, James Brown, Clarence Carter, Run-D.M.C., Kurtis Blow) and the modern hits (Mariah, Bieber, Bublé, Ariana, Sia, Kelly Clarkson, Taylor Swift, Ed Sheeran).
- 50 Danish cards: julekalender themes (Jul i Gammelby, Nissebanden, Pyrus, Bamses Julerejse, Jul i Juleland, Jul på Kronborg, Jesus & Josefine, Jul i Valhal, Absalons Hemmelighed, Pagten, Ludvig og Julemanden, Julestjerner, Tvillingerne og Julemanden, Tidsrejsen, Tinka, Theo og den magiske talisman, Kometernes Jul), the classics (Søren Banjomus, Den Himmelblå, Rap Jul, Endelig Jul Igen, Så' det jul, Gnags' Julesang, Vi ønsker jer alle en glædelig jul) and the modern ones (Rasmus Seebach, Mads Langer, Burhan G, Lukas Graham, Oh Land, Christopher, Suspekt, Anne Linnet).
- Julekalender cards carry the AIRING year, not the Spotify reissue year, the same rule `mgp` and `eurovision` use for the contest year.
- Deck goes 970 -> 1120 songs, 14 -> 15 categories. The frontend needed no change: `renderCats()` is driven by `DB.categories`.
- Fixed a latent fetch-cache bug found while building (see gotchas). Two cards were silently unbuildable because of it.
- Website repo synced, merged and deploy verified by fetching the live `songs.js`: 15 categories, 1120 songs, 150 in `christmas`.

NOT done: the Christmas deck has not been play-tested with phones.

## 3. Prioritized next steps
1. Play a round on the Christmas deck before using it at a party: check card years read sensibly on the timeline and that the Danish julekalender cards are recognisable.
2. Issue #15 "feat: chromecasting" holds the full research for getting the game screen onto a TV. Start there, not from scratch: a cast button cannot work from an iPhone, so the cheap route depends on which Chromecast model is on the TV.
3. Carry-over: confirm the PRODUCTION Spotify redirect URI is registered (game URL plus the Vercel production URL in the Spotify app), or Connect Spotify fails on the live domain.
4. Carry-over: decide on true server-side delete of finished games (needs a host-token delete-on-finish endpoint in patrickrobelweb) vs keeping the client-side list filter.
5. Optional deck work: 32 old seed entries still never resolve on Spotify DK, so a plain `build_deck.py` always prompts for credentials. They could be retitled or dropped.

## 4. Verbatim resume commands (PowerShell)
Rebuild the deck from cache with no credentials and no API calls:
```
cd "C:\Users\pr\repos\1-Personal\MusicTimelineQuiz"; python tools/build_deck.py --no-fetch
```
Gate any seed change (pre-build, then post-build, neither needs credentials):
```
cd "C:\Users\pr\repos\1-Personal\MusicTimelineQuiz"; python tools/validate_seed.py; python tools/audit_deck.py christmas
```
Sync the game into the website repo (then commit there; merging that is what deploys):
```
cd "C:\Users\pr\repos\1-Personal\patrickrobelweb\website"; pnpm sync:music-timeline-quiz
```

## 5. Gotchas discovered this session
- **Fetch-cache key collision.** The cache keys on `cat + "|" + norm(title)` and `norm()` strips parentheticals, so two cards in one category whose titles differ only inside brackets share one slot. The later card overwrites it, the earlier one then reuses the wrong track id, and the second card is dropped as a duplicate. `validate_seed.py` cannot see it: it compares title plus artist, and the artists differ. Hit by "Christmas Time" vs "Christmas Time (Don't Let The Bells End)" and "Merry Christmas" vs "Merry Christmas (I Don't Want To Fight Tonight)". Fix is to move the qualifier outside the brackets. A stale `tools/deck.json` re-seeds the collided key on every rebuild, so that file has to be corrected too, not just the cache.
- **Spotify search API changed.** `limit=50` is now rejected with `{"error":{"status":400,"message":"Invalid limit"}}`, max is 10, and `popularity` comes back 0 for every track under client credentials. Ranking candidates by popularity is no longer possible. `build_deck.py` already uses `limit=10`, so builds are unaffected.
- **Resolving a card by hand.** When search cannot match a card, write a `cat|norm(title)` entry into `tools/fetch-cache.json` with the real track id and `qr_data_uri(url)`, then rebuild with `--no-fetch`. Track ids for cards that were built at least once can be read back out of `tools/audit_checkpoint.jsonl`, which is how two lost ids were recovered this session. 14 of the 150 Christmas cards were placed this way, and all 14 come back OK in the audit.
- **Two accepted audit flags in `christmas`**, both cosmetic: Spotify dates Gene Autry's Rudolph 1947 against the 1949 recording (seed keeps 1949), and credits "Pretenders" without "The".
- **Website repo pushes need the personal gh config.** That clone's `.git/config` sets `credential.helper !gh auth git-credential` with no config dir, which overrides the global pin to `gh-personal`, so git authenticates as `przrm` and a private `patr7257` repo answers "Repository not found". Prefix the command with `GH_CONFIG_DIR=C:\Users\pr\.config\gh-personal`, or remove that local line.
- The stale handover claimed the website repo still needed the steal-phase sync. It did not: `songs.js` was the only file the sync changed, so that work had already shipped.

## 6. Open decisions waiting on Patrick
- Chromecast: which model is on the TV decides everything (see issue #15). A Google TV device can sideload a browser and open the game URL with no code at all; an older dongle can only ever show a registered Cast receiver, which needs a native iOS app to launch from an iPhone.
- Whether the TV should show a read-only display client instead of the authoritative host screen. That needs a new display-scoped projection, because the phone projection deliberately strips the current card and its answers.
- Whether to remove the local `credential.helper` line in the patrickrobelweb clone so the global gh-personal pin wins.

## 7. Environment state
- No dev servers, Docker or localhost ports were started this session; nothing left running.
- No cron jobs, scheduled tasks or wake timers were created.
- Branches deleted at close, all with merged PRs: `feat/christmas-category` and `docs/handover-mgp-eurovision` (local and remote), `feat/mgp-eurovision-categories` (remote), and `feat/music-timeline-quiz-christmas-deck` in the website repo (local and remote). Both repos are now `main` only.
- Single worktree per repo, both clean and synced with origin.
