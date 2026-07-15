#!/usr/bin/env node
// Interactive admin tool: lists every saved Hitster game in Upstash Redis
// (dry run), then deletes them after an explicit confirmation. Never accepts
// the Upstash REST URL or token as arguments or env vars: it always prompts,
// so nothing lands in shell history, and it never writes them to disk.
//
// Key pattern (must match website/src/lib/hitster-redis.ts):
//   hitster:games:index            hash, field = gameId, value = GamesIndexEntry JSON
//   hitster:game:<gameId>:meta     string, GameMeta JSON
//   hitster:game:<gameId>:state    string, FullGameState JSON
//   hitster:game:<gameId>:claims   hash
//   hitster:game:<gameId>:tent     string
//   hitster:game:<gameId>:intents:<round>  list, one per round
//
// Only keys starting with "hitster:" are ever read or deleted.
import { createInterface } from "node:readline";
import { Writable } from "node:stream";

const GAME_KEY_PREFIX = "hitster:game:";
const INDEX_KEY = "hitster:games:index";
const SCAN_MATCH = "hitster:game:*";
const SCAN_COUNT = 200;

// Prompt plumbing. Hard-won rules, do not regress:
// - ONE readline interface for the whole run, and ALL input goes through it.
//   An earlier version dropped to raw-mode stdin for the hidden token prompt
//   while the readline interface stayed attached; readline also processed
//   those keystrokes and buffered a spurious line, which the NEXT prompt
//   (the yes/no confirmation) instantly consumed, auto-cancelling the wipe
//   in a real interactive terminal.
// - Reads go through the interface's single async iterator, never repeated
//   rl.question() calls: on piped/non-TTY stdin a second rl.question() can
//   hang forever because lines that arrived between questions are dropped.
// - The token prompt is masked by muting readline's echo (output goes to a
//   discarding stream while muted), not by taking over stdin.
let muted = false;
const promptOutput = new Writable({
  write(chunk, encoding, callback) {
    if (!muted) process.stdout.write(chunk, encoding);
    callback();
  },
});
const rl = createInterface({
  input: process.stdin,
  output: promptOutput,
  terminal: process.stdin.isTTY,
});
rl.on("SIGINT", () => {
  process.stdout.write("\n");
  process.exitCode = 130;
  rl.close();
});
const lineIterator = rl[Symbol.asyncIterator]();

async function ask(query) {
  process.stdout.write(query);
  const { value, done } = await lineIterator.next();
  return done ? "" : value;
}

// Masked prompt for the token: echo is muted while the line is typed, so the
// token never appears on screen. Input still flows through the shared
// readline interface, so no stray buffered lines can leak into later prompts.
async function askSecret(query) {
  process.stdout.write(query);
  muted = true;
  try {
    const { value, done } = await lineIterator.next();
    return done ? "" : value;
  } finally {
    muted = false;
    process.stdout.write("\n");
  }
}

// Confirmation prompt that never treats silence as an answer: an empty line
// (e.g. a stray buffered Enter) re-prompts instead of cancelling.
async function askConfirm(query) {
  for (;;) {
    const answer = (await ask(query)).trim().toLowerCase();
    if (answer !== "") return answer;
    console.log('Empty answer ignored. Type "yes" to delete or "no" to cancel.');
  }
}

// Exit by setting the exit code and releasing stdin, never process.exit():
// hard-exiting while a piped stdin handle is still closing hits a libuv
// assertion on Windows (async.c UV_HANDLE_CLOSING) and corrupts the code.
function finish(code) {
  process.exitCode = code;
  rl.close();
}

function makeClient(baseUrl, token) {
  const url = baseUrl.replace(/\/+$/, "");
  return async function redisCmd(command) {
    let res;
    try {
      res = await fetch(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(command),
      });
    } catch (err) {
      throw new Error(`could not reach ${url}: ${err.message}`);
    }
    let payload;
    const text = await res.text();
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`non-JSON response (status ${res.status}): ${text.slice(0, 200)}`);
    }
    if (!res.ok) {
      const detail = payload && payload.error ? payload.error : text.slice(0, 200);
      throw new Error(`Upstash request failed (status ${res.status}): ${detail}`);
    }
    return payload.result;
  };
}

async function scanAll(redisCmd, match, count) {
  const keys = [];
  let cursor = "0";
  do {
    const result = await redisCmd(["SCAN", cursor, "MATCH", match, "COUNT", String(count)]);
    if (!Array.isArray(result) || result.length !== 2) {
      throw new Error("unexpected SCAN response shape");
    }
    cursor = result[0];
    const batch = Array.isArray(result[1]) ? result[1] : [];
    keys.push(...batch);
  } while (cursor !== "0");
  return keys;
}

function safeParse(raw) {
  if (raw === null || raw === undefined) return null;
  if (typeof raw !== "string") return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function fmtDate(ms) {
  if (typeof ms !== "number" || !Number.isFinite(ms)) return "(unknown)";
  return new Date(ms).toISOString();
}

async function main() {
  console.log("Hitster saved-games wipe");
  console.log("Only keys starting with 'hitster:' are ever touched.\n");

  const rawUrl = (await ask("Upstash REST URL (e.g. https://xxx.upstash.io): ")).trim();
  if (!rawUrl) {
    console.error("No URL entered, aborting. Nothing was read or deleted.");
    finish(1);
    return;
  }
  const token = (await askSecret("Upstash REST token (input hidden): ")).trim();
  if (!token) {
    console.error("No token entered, aborting. Nothing was read or deleted.");
    finish(1);
    return;
  }

  const redisCmd = makeClient(rawUrl, token);

  console.log("\nConnecting...");
  try {
    await redisCmd(["DBSIZE"]);
  } catch (err) {
    console.error(`\nCould not connect with those credentials: ${err.message}`);
    console.error("Nothing was read or deleted. Check the URL and token and try again.");
    finish(1);
    return;
  }
  console.log("Connected.\n");

  // Gather every hitster:game:* key, grouped by gameId.
  let scannedKeys;
  try {
    scannedKeys = await scanAll(redisCmd, SCAN_MATCH, SCAN_COUNT);
  } catch (err) {
    console.error(`\nFailed while scanning keys: ${err.message}`);
    console.error("Nothing was deleted.");
    finish(1);
    return;
  }

  const keysByGame = new Map(); // gameId -> Set(keys)
  const gameIdRe = new RegExp(`^${GAME_KEY_PREFIX}([^:]+):`);
  for (const key of scannedKeys) {
    const m = gameIdRe.exec(key);
    if (!m) continue;
    const gameId = m[1];
    if (!keysByGame.has(gameId)) keysByGame.set(gameId, new Set());
    keysByGame.get(gameId).add(key);
  }

  // Index hash gives us the friendly name/players/timestamps for games that
  // are (or were) listed as saved games.
  let indexRaw;
  try {
    indexRaw = await redisCmd(["HGETALL", INDEX_KEY]);
  } catch (err) {
    console.error(`\nFailed to read ${INDEX_KEY}: ${err.message}`);
    console.error("Nothing was deleted.");
    finish(1);
    return;
  }
  const indexEntries = new Map(); // gameId -> parsed entry
  if (Array.isArray(indexRaw)) {
    for (let i = 0; i + 1 < indexRaw.length; i += 2) {
      const gameId = indexRaw[i];
      const entry = safeParse(indexRaw[i + 1]);
      indexEntries.set(gameId, entry);
      if (!keysByGame.has(gameId)) keysByGame.set(gameId, new Set());
    }
  }

  const allGameIds = [...keysByGame.keys()];
  if (allGameIds.length === 0) {
    console.log("No hitster:game:* keys and no entries in the saved-games index. Nothing to do.");
    finish(0);
    return;
  }

  // Build the dry-run report, fetching meta for games not already described
  // by an index entry (e.g. E2E games, which are deliberately never indexed).
  const rows = [];
  for (const gameId of allGameIds) {
    const entry = indexEntries.get(gameId);
    if (entry) {
      rows.push({
        gameId,
        name: entry.name ?? "(unknown)",
        players: Array.isArray(entry.players) ? entry.players.join(", ") : "(unknown)",
        createdAt: fmtDate(entry.createdAt),
        updatedAt: fmtDate(entry.updatedAt),
      });
      continue;
    }

    const metaKey = `${GAME_KEY_PREFIX}${gameId}:meta`;
    let metaRaw = null;
    try {
      metaRaw = await redisCmd(["GET", metaKey]);
    } catch {
      // ignore, fall through to "unknown" row
    }
    if (metaRaw === "reserved") {
      rows.push({ gameId, name: "(reserved, mid-creation)", players: "-", createdAt: "-", updatedAt: "-" });
      continue;
    }
    const meta = safeParse(metaRaw);
    if (meta) {
      rows.push({
        gameId,
        name: meta.name ?? "(unknown)",
        players: "(not saved, no index entry)",
        createdAt: fmtDate(meta.createdAt),
        updatedAt: fmtDate(meta.updatedAt),
      });
    } else {
      rows.push({ gameId, name: "(unknown, meta expired or missing)", players: "-", createdAt: "-", updatedAt: "-" });
    }
  }

  console.log(`DRY RUN: ${rows.length} game(s) found\n`);
  for (const row of rows) {
    console.log(`  ${row.gameId}  ${row.name}`);
    console.log(`    players: ${row.players}`);
    console.log(`    created: ${row.createdAt}  updated: ${row.updatedAt}`);
  }
  const totalKeys = [...keysByGame.values()].reduce((sum, set) => sum + set.size, 0);
  console.log(`\nTotal underlying redis keys under "${GAME_KEY_PREFIX}*": ${totalKeys}`);
  console.log(`Index entries in "${INDEX_KEY}": ${indexEntries.size}`);

  console.log("\nNothing has been deleted yet.");
  const answer = await askConfirm(
    `Type "yes" to permanently delete all ${rows.length} game(s) above (anything else cancels): `
  );
  if (answer !== "yes") {
    console.log("Cancelled. Nothing was deleted.");
    finish(0);
    return;
  }

  const allKeys = [];
  for (const set of keysByGame.values()) allKeys.push(...set);

  let deletedKeys = 0;
  try {
    if (allKeys.length > 0) {
      deletedKeys = await redisCmd(["DEL", ...allKeys]);
    }
    if (allGameIds.length > 0) {
      await redisCmd(["HDEL", INDEX_KEY, ...allGameIds]);
    }
  } catch (err) {
    console.error(`\nDeletion failed partway through: ${err.message}`);
    console.error("Re-run the script to see what is left.");
    finish(1);
    return;
  }

  console.log(
    `\nDone. Deleted ${deletedKeys} redis key(s) across ${allGameIds.length} game(s), and removed them from the saved-games index.`
  );
  finish(0);
}

main().catch((err) => {
  console.error(`\nUnexpected error: ${err.message}`);
  console.error("Nothing further was deleted.");
  finish(1);
});
