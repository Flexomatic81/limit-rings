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

const T = C.ENGLISH

test("compact numbers and ages", () => {
  assert.equal(C.compactNumber(999, T), "999")
  assert.equal(C.compactNumber(12_400, T), "12 k")
  assert.equal(C.compactNumber(1_250_000, T), "1.3 M")
  assert.equal(C.compactNumber(2_000_000_000, T), "2.0 B")
  assert.equal(C.ageText(new Date((NOW - 125) * 1000).toISOString(), NOW * 1000, T), "2 min ago")
  assert.equal(C.ageText(null, NOW * 1000, T), "—")
})

test("limit names, plans and percent texts", () => {
  assert.equal(C.limitName({window_minutes: 300}, T), "5 h")
  assert.equal(C.limitName({window_minutes: 10080, model: "Opus"}, T), "Week Opus")
  assert.equal(C.limitName({window_minutes: 1440}, T), "1 d")
  assert.equal(C.planName("max"), "Max")
  assert.equal(C.planName("newtier"), "newtier")
  assert.equal(C.limitPercentText({used_percent: 30.4, resets_at: null}, NOW, true, T), "70 % left")
})

test("forecast notes use the weekday from the translator", () => {
  const tr = {...T, weekday: d => ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"][d]}
  const limit = {used_percent: 50, resets_at: NOW + 5 * 86400, forecast: {status: "full", eta: NOW + 2 * 86400}}
  assert.match(C.forecastText(limit, NOW, tr), /^Full in ~2 d 0 h at current pace \((Su|Mo|Tu|We|Th|Fr|Sa) \d\d:\d\d\)$/)
  assert.equal(C.barNote({...limit, forecast: {status: "enough"}}, NOW, tr), "")
})

test("footer names source, staleness and pause", () => {
  const p = {limits: [{}], limits_source: "oauth", limits_updated_at: new Date((NOW - 60) * 1000).toISOString(),
             limits_paused_until: null}
  assert.equal(C.footerText(p, NOW * 1000, 0, T), "Updated 1 min ago · OAuth")
})

test("auth and login hints", () => {
  assert.equal(C.authHint({status: "expired"}, null, T), "Login expired – run claude in a terminal")
  assert.equal(C.authHint({status: "ok"}, null, T), "")
  assert.match(C.loginHint({login: false, limits: []}, {key: "claude"}, T), /status line/)
})

test("collector output", () => {
  assert.equal(C.readCollectorOutput(127, "").error, "nopython")
  assert.equal(C.readCollectorOutput(0, "Traceback (most recent call last):").error, "parse")
  const old = C.readCollectorOutput(3, JSON.stringify({envelope: 1, error: "python-too-old", version: "3.9.6"}))
  assert.deepEqual([old.error, old.pythonVersion], ["oldpython", "3.9.6"])
  assert.equal(C.readCollectorOutput(124, "").error, "timeout")
  assert.equal(C.readCollectorOutput(0, JSON.stringify({envelope: 1, error: "widget-folder"})).error, "folder")
  const ok = C.readCollectorOutput(0, JSON.stringify({envelope: 1, stats: {schema: 2}, notices: []}))
  assert.equal(ok.error, "")
  assert.deepEqual(ok.stats, {schema: 2})
})

test("status message with a download link", () => {
  const msg = C.statusMessage("oldpython", null, NOW * 1000,
                              {pythonVersion: "3.9.6", installUrl: "https://www.python.org/downloads/macos/"}, T)
  assert.equal(msg, "Python 3.9.6 is too old – Limit Rings needs 3.10 or newer. " +
                    "Download it from https://www.python.org/downloads/macos/")
  assert.equal(C.statusMessage("", {generated_at: new Date(NOW * 1000).toISOString()}, NOW * 1000, {}, T), "")
})

test("status messages for a wrong folder name and a timed-out pass", () => {
  assert.equal(C.statusMessage("folder", null, NOW * 1000, {}, T),
               "The widget folder must be named limit-rings.widget – rename it in Übersicht's widgets folder.")
  assert.match(C.statusMessage("timeout", null, NOW * 1000, {}, T), /^The last collector run took too long and was stopped\. Log: /)
})
