# HANDOVER

## 1. Date, branch, PR, CI
- Date: 2026-08-08
- Branch: `feat/mgp-eurovision-categories` (squash-merged to `main` as `f86f15b`, local copy deleted at close, remote copy left in place)
- PR: MusicTimelineQuiz #11 (MGP + Eurovision categories), squash-merged; closes issue #10
- CI: repo has no CI checks; verification was `validate_seed.py`, `audit_deck.py`, and reading the built `songs.js` back through `window.HITSTER_DB`

## 2. TLDR of session outcome
Done (all in PR #11, and live on production):
- Two new filterable deck categories, both hand-curated: `mgp` "MGP (Børn)" 🎈 (50 cards, DR's children's Melodi Grand Prix) and `eurovision` "Eurovision" ✨ (75 cards, 1990 to 2026).
- MGP is weighted at the early seasons on purpose: 42 cards from 2000 to 2013, 8 from 2014 on.
- Eurovision is deliberately modern-only (1990 onwards): every winner in that window that Spotify DK carries, plus famous runner-ups (Cha Cha Cha, SloMo, SPACE MAN, Rim Tim Tagi Dim) and iconic entries (Dancing Lasha Tumbai, Run Away, Party For Everybody, Europapa, Espresso Macchiato).
- Deck goes 844 -> 970 songs, 12 -> 14 categories. `songs.js` 662 KB -> 758 KB.
- The frontend needed NO change: `renderCats()` in index.html is driven by `DB.categories`, and the 4-column tile grid just grew a row.
- Website repo synced, committed and PUSHED, deploy verified by fetching the live `songs.js`: patrickrobel.dk/music-timeline-quiz serves both new tiles.

NOT done: the two categories were never played in a real game, only verified at the data level plus an HTTP fetch of the built files. No phone/host round was run with an MGP-only or Eurovision-only deck.

## 3. Prioritized next steps
1. Play one MGP-only and one Eurovision-only round to sanity-check the feel. The Eurovision deck packs 75 cards into 37 years, so timeline placement is deliberately tight; if it plays badly, swap a few picks for pre-1990 classics.
2. MGP 2023 has NO card: the winner (Sophia, "Det' Bare Tanker") is not on Spotify DK. MGP 2005 (Nicolai Kielstrup) and 2009 (PelleB) winners are missing for the same reason, though those seasons are covered by other entries. If you want 2023 represented, pick a different song from that season.
3. Carry-over: confirm the PRODUCTION Spotify redirect URI is registered (game URL + Vercel production URL in the Spotify app), or Connect Spotify fails on the live domain.
4. Carry-over: decide on true server-side delete of finished games (needs a host-token delete-on-finish endpoint in patrickrobelweb) vs keeping the client-side list filter.

## 4. Verbatim resume commands (PowerShell)
Rebuild the deck from cache with no credentials and no API calls:
```
cd "C:\Users\pr\repos\1-Personal\MusicTimelineQuiz"; python tools\build_deck.py --no-fetch
```
Sync the merged game into the website repo (then commit and push there):
```
cd "C:\Users\pr\repos\1-Personal\patrickrobelweb\website"; pnpm sync:music-timeline-quiz
```
Audit only the new categories (no credentials needed):
```
cd "C:\Users\pr\repos\1-Personal\MusicTimelineQuiz"; python tools\audit_deck.py eurovision
```

## 5. Gotchas discovered this session
- A seed edit to `title`, `artist` or `year` does NOT reach `songs.js` for an already-resolved song. `build_deck.py`'s `try_reuse` returns the CACHED entry and only re-syncs `source`, and `deck.json` takes precedence over `fetch-cache.json` when both hold the key. Fixing the 2026 MGP title (a missing comma) meant patching BOTH `tools/deck.json` and `tools/fetch-cache.json`, then rebuilding. Cache keys are `"<cat>|<normalised title>"`, and norm strips punctuation, so a punctuation-only fix keeps the same key.
- `mgp` and `eurovision` carry the CONTEST year, not the Spotify release year. That is safe: `audit_deck.py` only flags a release EARLIER than the seed year, and these recordings sit on LATER compilations.
- Both blocks sit LAST in the seed's `songs` object, the opposite of `gentofte`. Order decides who wins a duplicate, and here the existing category should win: that is what keeps "Fly on the Wings of Love" and "Only Teardrops" in `danish`, with Eurovision carrying the other Danish entries (Rollo & King, Brinck, Basim, Rasmussen, Saba).
- Spotify credits most MGP tracks as "MGP, <first name>", so `audit_deck.py` reports ARTIST_WORD_ONLY for them. Those are the real MGP recordings, not wrong matches. Same class of harmless flag: "Katrina & The Waves", "Charlotte Perrelli" (she was Nilsson in 1999), "Buranovskie Babushki", "Joost".
- Search DOES resolve wrong recordings for generic titles: Emma's "Hater" (MGP 2022) matched an unrelated 2018 track by Emma and the Fragments and was dropped. Always run `audit_deck.py <category>` after adding one.
- The seed was deliberately over-provisioned (72 MGP, 104 Eurovision candidates) for one credentialed build, then trimmed to exactly 50 and 75 and rebuilt with `--no-fetch`. Candidates that never resolved were removed from the seed rather than left behind, so they do not force a credential prompt on every future build.
- `gh pr create` failed with "must be a collaborator" because the default gh config was active as `przrm`. `powershell -File "C:\Users\pr\.claude\scripts\gh-auth.ps1" -Mode fix` repaired it in one command.

## 6. Open decisions waiting on Patrick
- MGP 2023 has no card at all (see next-step 2): pick a substitute song from that season, or leave the gap?
- Server-side delete of finished games: yes (build the endpoint in patrickrobelweb) or no (keep client filter)?
- Carry-over from the July session: is a two-phone live check of the steal flow still wanted, or is desk-testing enough?

## 7. Environment state
- A local `python -m http.server 8099` was started to verify the built files over HTTP and was stopped in the same session. No Docker, no other ports, nothing left running.
- Branches cleaned at close: `feat/mgp-eurovision-categories` deleted locally only. The remote branch of the same name still exists on GitHub (this repo does not auto-delete merged branches).
- No scheduled jobs, cron entries, or background tasks were created.
- Website repo (`patrickrobelweb`): `main` is committed AND pushed this session (`94202c7`), production is up to date. Nothing pending there.
