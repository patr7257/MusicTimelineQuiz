# HANDOVER

## 1. Date, branch, PR, CI
- Date: 2026-07-23
- Branch: `fix/steal-phase-privacy` (merged to `main` and deleted at session close)
- PR: MusicTimelineQuiz #9 (steal-phase privacy + pacing, docs, this handover), squash-merged
- CI: repo has no CI checks; verification was `node --check` on both inline scripts

## 2. TLDR of session outcome
Done (all in PR #9):
- Fix 1: steal presses are secret during the countdown. `buildStealBlob` sends an empty `presses` list until picking starts and never projects confirmed pick slots; host screen hides badge/count/names. A phone presser's seat looks untouched; an unclaimed seat that pressed on the shared screen shows a disabled "In!".
- Fix 2: the pick sub-phase is untimed. Removed the 12s `armPickBail` auto-skip; stealers pick one at a time in press order, claimed stealers pick privately on their own phone (shared screen shows only whose turn it is), host "Reveal now" is the manual escape.
- Fix 3: the 10s countdown holds at 10 for a 2s grace (`STEAL_HOLD_SECONDS`), hold baked into `windowEndsAt`, clients cap the shown number at 10 (never counts from 12).
- Docs: PROTOCOL.md + README.md updated to the new steal contract; CLAUDE.md website-sync section repointed to `pnpm sync:music-timeline-quiz` / `/music-timeline-quiz` (closed stale item 5 from the previous handover).

NOT done: the game was not live-tested with phones this session (merged on Patrick's "assume all works"), and the website repo copy is NOT synced yet, so production still serves the old steal behavior.

## 3. Prioritized next steps
1. Sync the game into the website repo and commit + push there (see command below); production only updates after that.
2. Live-test a full steal round with 2+ phones: press secrecy during countdown, one-at-a-time private picks with no timeout, hold-then-count 10s display, same-gap wheel.
3. Carry-over: confirm the PRODUCTION Spotify redirect URI is registered (game URL + Vercel production URL in the Spotify app), or Connect Spotify fails on the live domain.
4. Carry-over: decide on true server-side delete of finished games (needs a host-token delete-on-finish endpoint in patrickrobelweb) vs keeping the client-side list filter.

## 4. Verbatim resume commands (PowerShell)
Sync the merged game into the website repo (then commit both repos):
```
cd "C:\Users\pr\repos\1-Personal\patrickrobelweb\website"; pnpm sync:music-timeline-quiz
```
Syntax-check the inline scripts after any HTML edit:
```
cd "C:\Users\pr\repos\1-Personal\MusicTimelineQuiz"; node -e "const{readFileSync,writeFileSync}=require('fs');const{execFileSync}=require('child_process');for(const f of['index.html','guess.html']){const m=readFileSync(f,'utf8').match(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/i);writeFileSync('.chk.js',m[1]);execFileSync(process.execPath,['--check','.chk.js']);console.log(f+' OK')}"
```

## 5. Gotchas discovered this session
- Steal privacy contract (PROTOCOL.md updated): projected `presses` is EMPTY during the countdown sub-phase and `slot` is ALWAYS null; a presser's own phone shows "you are in" from its local `stealPressedRoundLocal` flag, not from the projection. Do not reintroduce presses/slots into the projection or players can read each other's moves out of the poll data.
- `windowEndsAt` includes the 2s hold, so it can sit up to 12s out; both clients cap the DISPLAYED number at 10 (`stealCountdownDisplay` in guess.html). Change `STEAL_SECONDS`/`STEAL_HOLD_SECONDS` in index.html and the cap in guess.html together.
- Picking is untimed by design: there is no bail timer anymore. If a picker's phone dies the round waits; the host's "Reveal now" (ghost button while a phone picker chooses) skips the remaining pickers.
- The website sync script default reads THIS clone (`C:\Users\pr\repos\1-Personal\MusicTimelineQuiz`); `GAME_DIR` overrides. The old `C:\Users\pr\repos\hitster` path in docs was stale and is now fixed in CLAUDE.md.

## 6. Open decisions waiting on Patrick
- Server-side delete of finished games: yes (build the endpoint in patrickrobelweb) or no (keep client filter)?
- After the website sync, do you want a quick two-phone live check of the new steal flow before the next games night, or is desk-testing enough?

## 7. Environment state
- No dev servers, Docker, or localhost ports were started this session; nothing left running.
- Branches cleaned at close: `chore/rename-repo-refs` (merged as #8), `fix/steal-phase-privacy` (merged as #9). Single worktree only.
- Website repo (`patrickrobelweb`) untouched this session: the sync in next-step 1 is pending there.
