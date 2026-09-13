# HANDOVER

## 1. Date, branch, PR, CI
- Date: 2026-09-13 (a second session the same day as the Christmas deck, 2026-09-12)
- Branches: `hotfix/specials-default-off` and `fix/pick-best-closest-release`, both squash-merged to `main` and deleted
- PRs: MusicTimelineQuiz #17 (Standard/Specials split, `c51c4a5`) and #18 (year-aware picker plus 28 re-picked cards, `5a707d6`). Website: PatrickRobelWeb #179 (`7a6cdc7`) and #180 (`1eab2b8`)
- CI: repo has no CI checks. Verification was `tools/test_pick_best.py`, `tools/test_repick_versions.py`, `scripts/check-picker.mjs`, `validate_seed.py`, `audit_deck.py christmas`, `node --check`, and fetching the live files off production

## 2. TLDR of session outcome
Done, and live on production:
- **Standard / Specials split.** Every category carries a `group` in `deck-seed.json`. Specials are Disney, Musik i Gentofte, MGP (Børn), Eurovision and Christmas; Standard is the other ten. A new game ticks Standard only, so it opens on 709 songs instead of 1120 and a themed deck is always a deliberate tap. `renderCats()` draws one thin square framed box per group, name in the border, Specials dashed and gold, each box with its own All and None. The design was picked from three mockups first.
- **Year-aware track picking.** `pick_best` now prefers the release closest to the seed year. Spotify returns `popularity: 0` for every track under client credentials, which had collapsed the tie-break to "whatever Spotify listed first", usually the newest re-release. That is how the 2013 julekalender single "I En Stjerneregn Af Sne" became a 2026 re-recording of the same name, which Patrick caught by ear.
- **`tools/repick_versions.py`** re-resolves already-built cards with that picker and swaps one in only when the new track is strictly closer to the seed year. Run over `christmas`: 135 unpinned cards checked, 28 replaced, 0 kept back, none landing earlier than the seed. Cards sitting 5+ years past their seed year fell from 49 to 37.
- **Pinned cards.** The 15 cards resolved by hand carry `"pinned": true` in the fetch cache, so a later search can never override a human's track id. The flag never reaches `songs.js`.
- **Chromecast** was researched, not built: findings live in issue #15.

NOT done: no phone play-test of either change, and the other 970 cards have not been re-picked (Patrick's call, the tool is there when he wants it).

## 3. Prioritized next steps
1. Play one round on a phone: the two category boxes on the setup screen, and a few Christmas cards to confirm the re-picked recordings sound like the ones people remember.
2. Optional: `python tools/repick_versions.py --only <cat>` for the remaining categories. Christmas found 28 stale picks in 135 cards, so the rest of the deck likely holds well over 100.
3. Issue #15 (Chromecast) is blocked on one fact: which Chromecast model is on the TV. A Google TV device can sideload a browser and open the game URL with no code; an older dongle can only show a registered Cast receiver, which on an iPhone needs a native app.
4. Watch the next website merge: the GitHub to Vercel webhook did NOT fire for `1eab2b8` (see gotchas). If it happens again, that integration is the thing to fix, not the code.
5. Carry-over: confirm the PRODUCTION Spotify redirect URI is registered, or Connect Spotify fails on the live domain.
6. Carry-over: server-side delete of finished games, vs keeping the client-side list filter.

## 4. Verbatim resume commands (PowerShell)
Check the category picker after touching `renderCats()`, the `group` fields or the setup defaults:
```
cd "C:\Users\pr\repos\1-Personal\MusicTimelineQuiz"; node scripts/check-picker.mjs
```
Run the deck tool tests (no credentials, no network):
```
cd "C:\Users\pr\repos\1-Personal\MusicTimelineQuiz"; python tools/test_pick_best.py; python tools/test_repick_versions.py
```
Re-pick one category onto the closest release (prompts for Spotify credentials, resumable):
```
cd "C:\Users\pr\repos\1-Personal\MusicTimelineQuiz"; python tools/repick_versions.py --only danish
```
Rebuild from cache, then sync and deploy:
```
cd "C:\Users\pr\repos\1-Personal\MusicTimelineQuiz"; python tools/build_deck.py --no-fetch
```
```
cd "C:\Users\pr\repos\1-Personal\patrickrobelweb\website"; pnpm sync:music-timeline-quiz
```

## 5. Gotchas discovered this session
- **Spotify's `popularity` is 0 for every track under client credentials, and `limit=50` is rejected** (`{"error":{"status":400,"message":"Invalid limit"}}`, max 10). Any scoring that leaned on popularity is silently dead. `pick_best` now leans on release-year distance instead, capped at 60 so it orders same-title candidates without ever overturning an exact title match.
- **`audit_deck.py` cannot catch a re-recording.** Same artist, same title, later release is none of the three things it flags, and the public embed page carries no album name, only title, artist, release date and duration. So nothing credential-free separates "the original on a 2026 compilation" from "a 2026 re-recording". The year-distance picker is the defence, not the audit.
- **A hand-picked track id needs `"pinned": true`** in `tools/fetch-cache.json` or the next `repick_versions.py` run can search over it.
- **`deck.json` wins over `fetch-cache.json`** when both hold the same key (`existing.setdefault`), and a cache entry without a `qr` is treated as no entry at all. Fixing a card means fixing both files, or removing the stale `deck.json` entry so the cache supplies it.
- **The GitHub to Vercel webhook did not fire for the `1eab2b8` merge.** GitHub was returning 502s during that merge (`gh pr merge` failed twice yet the squash landed, and PR #180 stayed OPEN with its commit already on `main`). No production deployment was created; Patrick deployed by hand with `npx vercel login; npx vercel --prod` from `website/`. The Vercel CLI in this checkout is authenticated as `przrms-projects` and deploys the working tree, not CI.
- **`git checkout <file>` discards an uncommitted change.** Restoring a deliberately sabotaged file that way also reverted the real edit sitting next to it, and it had to be re-applied. Copy the file aside before a bite test instead.

## 6. Open decisions waiting on Patrick
- Whether to re-pick the remaining 970 cards, and whether to do it in one long run or category by category.
- Chromecast: which model is on the TV (issue #15), and whether the TV should ever get a read-only display client rather than the authoritative host screen.
- Whether to remove the repo-local `credential.helper` line in the patrickrobelweb clone so the global `gh-personal` pin wins. Without that, `git push` there authenticates as `przrm` and a private `patr7257` repo answers "Repository not found".

## 7. Environment state
- No dev servers, containers or ports were started by this session. Docker was already running with `sg-lease-dev-postgres-1`, `sg-lease-dev-azurite-1` and `mw-postgres` from other projects; they were deliberately left alone.
- No cron jobs, scheduled tasks or wake timers were created.
- Branches deleted at close: `hotfix/specials-default-off`, `fix/pick-best-closest-release`, `docs/handover-christmas-deck` (MusicTimelineQuiz), and in the website repo `fix/music-timeline-quiz-specials-default-off`, `fix/music-timeline-quiz-closest-release` plus two merged August leftovers, `feat/todo-tinder-pwa` and `feat/todo-ux-integration`. Both repos are `main` only.
- PR #180 was closed by hand with a comment: its squash had already landed, GitHub just never updated the pull request.
