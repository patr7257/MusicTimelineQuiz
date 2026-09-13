#!/usr/bin/env node
// Checks the setup screen's category picker: the Standard / Specials split, and
// that a new game opens on the Standard group only.
//
// It does NOT reimplement the picker. It slices the real category block straight
// out of index.html, runs it in a vm against a small DOM stub and the real built
// deck from songs.js, then drives it the way a player would: tick a tile, use a
// group's All and None buttons. So a regression in the shipped file fails here.
//
// Usage (from the repo root):  node scripts/check-picker.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import vm from "node:vm";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const BLOCK_START = "    // Category groups come from the deck data";
const BLOCK_END = "    function validateSetup()";

const html = readFileSync(join(ROOT, "index.html"), "utf8");
const start = html.indexOf(BLOCK_START);
const end = html.indexOf(BLOCK_END);
assert.ok(start > 0 && end > start,
  "could not find the category block in index.html; update BLOCK_START / BLOCK_END");
const src = html.slice(start, end);

const js = readFileSync(join(ROOT, "songs.js"), "utf8");
const DB = JSON.parse(js.slice(js.indexOf("{"), js.lastIndexOf("}") + 1));

// Minimal DOM stub: only what renderCats() actually touches.
function makeEl(tag) {
  const el = {
    tag, className: "", innerHTML: "", textContent: "", type: "", onclick: null,
    attrs: {}, styles: {}, children: [],
    setAttribute(k, v) { this.attrs[k] = v; },
    appendChild(c) { this.children.push(c); return c; },
  };
  el.style = { setProperty(k, v) { el.styles[k] = v; } };
  return el;
}

const catsHost = makeEl("div");
const sandbox = {
  DB,
  setup: { cats: new Set() },
  Set,
  document: { createElement: makeEl },
  $: (id) => (id === "cats" ? catsHost : makeEl("div")),
  escapeHtml: (s) => String(s),
  songsForCat: (key) => DB.songs.filter((s) => s.cat === key),
  validateSetup: () => {},
  console,
};
vm.createContext(sandbox);
vm.runInContext(src, sandbox);

const standard = DB.categories.filter((c) => (c.group || "standard") === "standard");
const specials = DB.categories.filter((c) => c.group === "specials");
assert.ok(specials.length > 0, "no category carries group: specials in songs.js");

const sizeOf = (keys) => DB.songs.filter((s) => keys.has(s.cat)).length;
const tilesOf = (box) => box.children[2].children;
const groupButtons = (box) => box.children[1].children.filter((c) => c.tag === "button");

// 1. A new game opens on Standard only.
sandbox.setup.cats = sandbox.defaultCats();
assert.equal(sandbox.setup.cats.size, standard.length,
  "a new game should tick every Standard category and nothing else");
for (const c of specials) {
  assert.ok(!sandbox.setup.cats.has(c.key), `${c.key} must be OFF when a game starts`);
}
const defaultDeck = sizeOf(sandbox.setup.cats);

// 2. The picker renders one framed box per group.
sandbox.renderCats();
assert.equal(catsHost.children.length, 2, "expected a Standard box and a Specials box");
const [stdBox, specBox] = catsHost.children;
assert.equal(stdBox.children[0].textContent, "Standard");
assert.equal(specBox.children[0].textContent, "Specials");
assert.ok(specBox.className.includes("specials"), "the Specials box needs its modifier class");
assert.equal(tilesOf(stdBox).length, standard.length);
assert.equal(tilesOf(specBox).length, specials.length);
assert.equal(tilesOf(stdBox).filter((t) => t.className.includes("on")).length, standard.length);
assert.equal(tilesOf(specBox).filter((t) => t.className.includes("on")).length, 0);

// 3. A tile click toggles exactly one category.
const firstSpecial = specials[0];
tilesOf(specBox)[0].onclick();
assert.ok(sandbox.setup.cats.has(firstSpecial.key), "clicking a Specials tile should tick it");
assert.equal(sandbox.setup.cats.size, standard.length + 1);
tilesOf(specBox)[0].onclick();
assert.ok(!sandbox.setup.cats.has(firstSpecial.key), "clicking it again should untick it");

// 4. All and None act on their own group only.
groupButtons(specBox)[0].onclick();
assert.equal(sandbox.setup.cats.size, DB.categories.length, "Specials > All should tick all five");
groupButtons(stdBox)[1].onclick();
assert.equal(sandbox.setup.cats.size, specials.length,
  "Standard > None must leave the Specials ticked");
groupButtons(specBox)[1].onclick();
assert.equal(sandbox.setup.cats.size, 0);

console.log(
  `picker OK: ${standard.length} Standard (${defaultDeck} songs) on by default, ` +
  `${specials.length} Specials (${sizeOf(new Set(specials.map((c) => c.key)))} songs) off, ` +
  "tile toggle and per-group All/None scoped correctly"
);
