import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { view, DEFAULTS } from "../limit-rings.widget/lib/card.mjs"
import { ENGLISH as T } from "../../plasmoid/io.github.flexomatic81.limitrings/contents/code/core.mjs"

const STATS = readFileSync(new URL("./fixtures/stats.json", import.meta.url), "utf8")
const NOW_MS = Date.parse("2026-10-08T12:00:30+02:00")
const out = stats => ({exitCode: 0, stdout: JSON.stringify({envelope: 1, stats, notices: []})})
const ok = () => view(out(JSON.parse(STATS)), null, NOW_MS, DEFAULTS, T)

test("one card per shown provider with rings and rows", () => {
  const v = ok()
  assert.equal(v.status, "")
  assert.deepEqual(v.cards.map(c => c.key), ["claude", "codex"])
  const c = v.cards[0]
  assert.equal(c.name, "Claude")
  assert.equal(c.plan, "Max")
  assert.equal(c.rings.outer.percent, 18)
  assert.equal(c.rings.inner.percent, 42)
  assert.deepEqual(c.rows.map(r => [r.label, r.percentText, r.severity]), [["5 h", "42 %", "normal"], ["Week", "18 %", "normal"]])
  assert.equal(c.rows[0].countdown, "2 h 13 min")
  assert.deepEqual(c.tokens, [{label: "Today", value: "1.3 M"}, {label: "Week", value: "9.0 M"},
                              {label: "Month", value: "31.0 M"}])
  assert.deepEqual(c.series.map(s => s.height), [0.5, 1])
  assert.equal(c.footer, "Updated 1 min ago · OAuth")
})

test("provider without limits shows its hint and no rings", () => {
  const codex = ok().cards[1]
  assert.deepEqual(codex.rings, {outer: null, inner: null})
  assert.deepEqual(codex.rows, [])
  assert.match(codex.hint, /^No limits without login/)
  assert.deepEqual(codex.series, [])
})

test("hidden providers get no card; remaining mode flips the values", () => {
  const v = view(out(JSON.parse(STATS)), null, NOW_MS, {...DEFAULTS, providers: ["claude"], remaining: true}, T)
  assert.deepEqual(v.cards.map(c => c.key), ["claude"])
  assert.equal(v.cards[0].rows[0].percentText, "58 % left")
  assert.equal(v.cards[0].rings.inner.percent, 58)
})

test("keeps the last good cards when a pass fails", () => {
  const good = ok()
  const bad = view({exitCode: 1, stdout: "Traceback (most recent call last):"}, good, NOW_MS, DEFAULTS, T)
  assert.deepEqual(bad.cards, good.cards)
  assert.match(bad.status, /^The collector output is not readable/)
  const none = view({exitCode: 1, stdout: ""}, null, NOW_MS, DEFAULTS, T)
  assert.deepEqual(none.cards, [])
})

test("too old python names the version and the download page", () => {
  const v = view({exitCode: 3, stdout: JSON.stringify({envelope: 1, error: "python-too-old", version: "3.9.6"})},
                 null, NOW_MS, DEFAULTS, T)
  assert.match(v.status, /^Python 3\.9\.6 is too old.*python\.org/)
})

test("expired login and unreadable logs are both said on the card", () => {
  const stats = JSON.parse(STATS)
  stats.providers.claude.auth = {status: "expired", expires_at: null}
  stats.providers.claude.errors = [{code: "logs_unreadable", count: 7}]
  stats.providers.codex.errors = [{code: "logs_failed"}]
  const [claude, codex] = view(out(stats), null, NOW_MS, DEFAULTS, T).cards
  assert.equal(claude.hint, "Login expired – run claude in a terminal")
  assert.equal(claude.errors, "7 files unreadable – numbers incomplete")
  assert.match(codex.hint, /^No limits without login/)
  assert.equal(codex.errors, "Data could not be processed")
})
