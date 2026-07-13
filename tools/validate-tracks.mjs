// Validate candidate Spotify track IDs via the public oEmbed endpoint.
// oEmbed returns the real track title for a valid /track/<id>, 404s otherwise.
// Usage: node hitster/tools/validate-tracks.mjs
// Reads candidates from candidates.json (same folder), writes verified.json.

import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const inFile = process.argv[2] || "candidates.json";
const outFile = process.argv[3] || "verified.json";
const candidates = JSON.parse(await readFile(join(here, inFile), "utf8"));

async function check(track) {
  const url = `https://open.spotify.com/oembed?url=https://open.spotify.com/track/${track.id}`;
  try {
    const res = await fetch(url, { headers: { "User-Agent": "hitster-validator" } });
    if (!res.ok) return { ...track, ok: false, reason: `http ${res.status}` };
    const data = await res.json();
    return { ...track, ok: true, spotifyTitle: data.title || "", thumb: data.thumbnail_url || "" };
  } catch (e) {
    return { ...track, ok: false, reason: String(e.message || e) };
  }
}

const results = [];
for (const t of candidates) {
  // sequential with a tiny gap to stay polite to the endpoint
  const r = await check(t);
  results.push(r);
  const flag = r.ok ? "OK " : "XX ";
  console.log(`${flag}${String(t.year)}  ${t.artist} - ${t.title}` + (r.ok ? `   => spotify: "${r.spotifyTitle}"` : `   (${r.reason})`));
  await new Promise((res) => setTimeout(res, 120));
}

const verified = results.filter((r) => r.ok).map(({ ok, reason, ...keep }) => keep);
await writeFile(join(here, outFile), JSON.stringify(verified, null, 2));
console.log(`\n${verified.length}/${candidates.length} verified -> ${outFile}`);
