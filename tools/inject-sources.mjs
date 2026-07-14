#!/usr/bin/env node
/*
  One-off (but reusable) patch script: reads deck-seed.json and adds any
  "source" field found there onto the matching entries already baked into
  the committed songs.js, without needing Spotify credentials to fully
  rebuild the deck. Matches by normalized title + artist (mirrors the
  norm() helper in build_deck.py).

  Usage: node tools/inject-sources.mjs
  Run again any time deck-seed.json gains new "source" annotations.
*/
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SEED_PATH = join(HERE, "deck-seed.json");
const SONGS_JS_PATH = join(HERE, "..", "songs.js");

function norm(s) {
  s = String(s == null ? "" : s);
  if (s.normalize) s = s.normalize("NFD");
  s = s.replace(/[\u0300-\u036f]/g, ""); // strip combining diacritics
  s = s.toLowerCase();
  s = s.replace(/\(.*?\)|\[.*?\]/g, " "); // drop parentheticals
  s = s.replace(/\bfeat\.?\b.*$/, " "); // drop featuring tails
  s = s.replace(/[^a-z0-9]+/g, " ");
  return s.trim();
}

const seed = JSON.parse(readFileSync(SEED_PATH, "utf8"));
const sourceByKey = new Map();
for (const cat of Object.keys(seed.songs)) {
  for (const e of seed.songs[cat]) {
    if (e.source) {
      sourceByKey.set(norm(e.title) + "|" + norm(e.artist), e.source);
    }
  }
}

const songsJsText = readFileSync(SONGS_JS_PATH, "utf8");
const bannerMatch = songsJsText.match(/^(\/\/[^\n]*\n)/);
const banner = bannerMatch ? bannerMatch[1] : "";
const assignMatch = songsJsText.match(/window\.HITSTER_DB\s*=\s*([\s\S]*?);\s*$/);
if (!assignMatch) {
  console.error("ERROR: could not find `window.HITSTER_DB = ...;` in songs.js; layout changed?");
  process.exit(1);
}
const db = JSON.parse(assignMatch[1]);

let patched = 0;
for (const song of db.songs) {
  const key = norm(song.title) + "|" + norm(song.artist);
  const source = sourceByKey.get(key);
  if (source) {
    song.source = source;
    patched++;
  }
}

const newText = banner + "window.HITSTER_DB = " + JSON.stringify(db) + ";\n";
writeFileSync(SONGS_JS_PATH, newText, "utf8");

console.log(`Patched ${patched} song(s) with source metadata out of ${sourceByKey.size} seed entries carrying "source".`);
console.log(`Wrote ${SONGS_JS_PATH}`);
