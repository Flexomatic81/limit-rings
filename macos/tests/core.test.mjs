import test from "node:test"
import assert from "node:assert/strict"
import * as C from "../../plasmoid/io.github.flexomatic81.limitrings/contents/code/core.mjs"

const NOW = 1_791_300_000

test("effectivePercent is 0 after the reset", () => {
  assert.equal(C.effectivePercent({used_percent: 40, resets_at: NOW - 1}, NOW), 0)
  assert.equal(C.effectivePercent({used_percent: 40, resets_at: NOW + 60}, NOW), 40)
  assert.equal(C.effectivePercent({used_percent: 40, resets_at: null}, NOW), 40)
})

test("shown values in remaining mode", () => {
  const l = {used_percent: 30, resets_at: NOW + 60}
  assert.equal(C.shownPercent(l, NOW, false), 30)
  assert.equal(C.shownPercent(l, NOW, true), 70)
  assert.equal(C.shownPercent({used_percent: 130, resets_at: null}, NOW, true), 0)
  assert.equal(C.shownShare(0.25, true), 0.75)
  assert.equal(C.shownShare(null, true), null)
})

test("severity by thresholds and pace", () => {
  assert.equal(C.severity(69, 70, 90), "normal")
  assert.equal(C.severity(70, 70, 90), "warning")
  assert.equal(C.severity(90, 70, 90), "critical")
  const full = {used_percent: 20, resets_at: NOW + 3600, forecast: {status: "full", eta: NOW + 600}}
  assert.equal(C.limitSeverity(full, NOW, 70, 90), "warning")
  assert.equal(C.worstSeverity([full, {used_percent: 95, resets_at: null}], NOW, 70, 90), "critical")
})

test("elapsed share of the window", () => {
  assert.equal(C.elapsedShare({window_minutes: 300, resets_at: NOW + 150 * 60}, NOW), 0.5)
  assert.equal(C.elapsedShare({window_minutes: 300, resets_at: NOW - 1}, NOW), null)
  assert.equal(C.elapsedShare({window_minutes: null, resets_at: NOW + 60}, NOW), null)
})

test("ring limits: outer weekly, inner 5 h, otherwise the highest", () => {
  const five = {window_minutes: 300, used_percent: 10, resets_at: null}
  const week = {window_minutes: 10080, used_percent: 30, resets_at: null}
  const day = {window_minutes: 1440, used_percent: 50, resets_at: null}
  assert.deepEqual(C.ringValues([five, week], NOW), {outer: 30, inner: 10})
  assert.deepEqual(C.ringValues([day], NOW), {outer: 50, inner: null})
  assert.deepEqual(C.ringValues([], NOW), {outer: null, inner: null})
})

test("countdowns", () => {
  assert.equal(C.countdownShort(NOW + 2 * 86400 + 3 * 3600, NOW), "2d 3h")
  assert.equal(C.countdownShort(NOW + 3600 + 5 * 60, NOW), "1h05m")
  assert.equal(C.countdownLong(NOW + 3600 + 5 * 60, NOW), "1 h 5 min")
  assert.equal(C.countdownLong(NOW - 1, NOW), "")
})

test("stale limits after 6 h", () => {
  const p = {limits: [{}], limits_updated_at: new Date((NOW - 7 * 3600) * 1000).toISOString()}
  assert.equal(C.limitsStale(p, NOW * 1000), true)
  assert.equal(C.limitsStale({...p, limits: []}, NOW * 1000), false)
})

test("chart series by range", () => {
  assert.deepEqual(C.chartSeries({daily: [1], weekly: [2]}, "weeks"), [2])
  assert.deepEqual(C.chartSeries({daily: [1]}, "unknown"), [1])
  assert.deepEqual(C.chartSeries(null, "days"), [])
})
