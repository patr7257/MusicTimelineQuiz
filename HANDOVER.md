# HANDOVER

## 1. Date, branch, PR, CI
- Date: 2026-07-17
- Branch: `main` (all work merged, worktrees removed)
- PRs (all MERGED): music-timeline-quiz #5 (frontend), music-timeline-quiz #6 (deck), patrickrobelweb #82 (server + game sync)
- CI: music-timeline-quiz has no CI checks; patrickrobelweb #82 Vercel deploy was green before merge. Production auto-deploys from patrickrobelweb `main`.

## 2. TLDR of session outcome
Done and shipped (a large overhaul across both repos, merged to `main`):
- Deck (#80 / #4): corrected the Christopher card to "CPH Girls" (2014) plus 7 audit-driven Danish year fixes, and hardened `pick_best` so a short seed title cannot bind a different recording. IMPORTANT: `songs.js` is NOT rebuilt yet, so the in-game deck still shows the old data until the rebuild runs.
- Frontend (#3 and many refinement rounds): mobile placement (chronological order, single-tap lock-in, drag ghost is the "?" card), steal fixes (countdown vs pick sub-phase, same-gap steal, own timeline only on own placement turn), reveal panel (square, left of QR, right/wrong, coin on correct), shuffled start wheel, phone centering, boot straight to menu with `?g=` deep-link resume, settings restructure (Display button, uniform dialogs, Save and exit with one shared confirm), and full-track Spotify Web Playback SDK playback (embed preview removed).
- State propagation (#2): the real fix was client resilience. On a 409 version race the host now adopts the server version and re-pushes (last-write-wins) instead of halting; time-critical transitions push immediately; the phone polls fast (1.5s) during the steal window. The server already bumped `rev` on every mobile write (confirmed), so no server change was needed for #2 itself.
- Server (#81): `projectForPhone` now forwards the steal `phase` and `pickerIdx` fields.

## 3. Prioritized next steps
1. Rebuild the deck so the corrected songs show in-game: run `build_deck.py` (prompts for Spotify creds), then `audit_deck.py danish` (expect 0 flags), commit `songs.js` + `deck.json`, then re-sync the game into the website.
2. Register the PRODUCTION Spotify redirect URI so Connect Spotify works on the live domain (only the preview branch-alias URL was registered). Add the production game URL (for example `https://www.patrickrobel.dk/music-timeline-quiz` and the Vercel production URL) to the same Spotify app's Redirect URIs.
3. Live-verify in production: mobile steal propagation, full Spotify playback with a Premium account, and that finished games no longer appear in the saved list.
4. Optional: true server-side delete of finished games. Today they are only filtered out of the client saved list; fully wiping them needs a host-token delete-on-finish endpoint in patrickrobelweb.
5. Fix stale `music-timeline-quiz/CLAUDE.md`: `pnpm sync:hitster` is now `pnpm sync:music-timeline-quiz`, the deploy path is `/music-timeline-quiz` (not `/hitster`), and the sibling clone note should point at `C:\Users\pr\repos\1-Personal\music-timeline-quiz` (the website sync script default already resolves there).

## 4. Verbatim resume commands (PowerShell)
Rebuild the deck (prompts for Spotify creds):
```
cd "C:\Users\pr\repos\1-Personal\music-timeline-quiz"; python tools/build_deck.py
```
Audit the Danish category after rebuild (no creds needed):
```
cd "C:\Users\pr\repos\1-Personal\music-timeline-quiz"; python tools/audit_deck.py danish
```
Re-sync the updated game into the website after any game change:
```
cd "C:\Users\pr\repos\1-Personal\patrickrobelweb\website"; pnpm sync:music-timeline-quiz
```

## 5. Gotchas discovered this session
- The game is TWO static files (`index.html` = PC host, `guess.html` = phone). It is deployed only via patrickrobelweb (`website/public/music-timeline-quiz/`), synced with `pnpm sync:music-timeline-quiz` (its default source path already resolves to this 1-Personal clone).
- Spotify full playback uses the Web Playback SDK plus Authorization Code + PKCE, all client-side. The Client ID (`d45bb37318d243cdb0b5dbb4411a7783`) is public and lives in `index.html`. `redirect_uri` is computed as `location.origin + location.pathname`, so EVERY origin the game runs on must be registered in the Spotify app. Premium is required for full tracks.
- Preview testing for OAuth must use the stable branch-alias URL, not the per-deploy hash URL, or the redirect will not match.
- State model: the PC host is the sole writer. A 409 now reconciles (last-write-wins), it does not halt. Do not reintroduce a hard stop on 409.
- The text-lint hook blocks em and en dashes everywhere and requires real Danish letters. Inline scripts were syntax-checked with a `new Function(body)` harness (CRLF line endings are used in both HTML files).

## 6. Open decisions waiting on Patrick
- Do you want true server-side deletion of finished games (yes = I add a host-token delete-on-finish to patrickrobelweb), or is the client-side list filter enough (no)?
- The 7 Danish year changes were audit-driven from Spotify release dates; a few (notably "Om Lidt", which dropped "and Kjukken" and moved to 1986) may be compilation artifacts. Do you want to spot-check and keep or revert any before/at the rebuild?

## 7. Environment state
- No dev servers or Docker were started this session; all verification ran on Vercel previews. Nothing left running.
- Removed worktrees: `music-timeline-quiz-3`, `music-timeline-quiz-4`, `patrickrobelweb-81`. Deleted merged branches: `feat/mobile-visuals`, `fix/danish-deck`, `fix/hitster-mobile-sync`.
- Left untouched (not this session's work): `patrickrobelweb-75` (feat/web-todolist) and the patrickrobelweb main checkout on `feat/robot-rally-racer`.
- Both repos' `main` are up to date locally.
