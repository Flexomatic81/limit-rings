import QtQuick
import QtTest
import "../io.github.flexomatic81.agentstats/contents/code/format.js" as F

TestCase {
    name: "Format"

    function test_formatInt() {
        compare(F.formatInt(0), "0")
        compare(F.formatInt(999), "999")
        compare(F.formatInt(1234567), "1,234,567")
    }

    function test_compactNumber() {
        compare(F.compactNumber(999), "999")
        compare(F.compactNumber(15000), "15 k")
        compare(F.compactNumber(999499), "999 k")
        compare(F.compactNumber(999500), "1.0 M")
        compare(F.compactNumber(1234567), "1.2 M")
        compare(F.compactNumber(31000000), "31.0 M")
        compare(F.compactNumber(2500000000), "2.5 B")
    }

    function test_effectivePercent_and_reset() {
        const now = 1000
        compare(F.effectivePercent({used_percent: 42, resets_at: 2000}, now), 42)
        compare(F.effectivePercent({used_percent: 42, resets_at: 1000}, now), 0)
        compare(F.effectivePercent({used_percent: 42, resets_at: null}, now), 42)
        verify(F.isReset({used_percent: 42, resets_at: 999}, now))
        verify(!F.isReset({used_percent: 42, resets_at: null}, now))
    }

    function test_severity() {
        compare(F.severity(69.9, 70, 90), "normal")
        compare(F.severity(70, 70, 90), "warning")
        compare(F.severity(90, 70, 90), "critical")
    }

    function test_maxPercent() {
        compare(F.maxPercent([], 0), null)
        compare(F.maxPercent(null, 0), null)
        compare(F.maxPercent([{used_percent: 10, resets_at: null}, {used_percent: 80, resets_at: 5}], 10), 10)
        compare(F.maxPercent([{used_percent: 10, resets_at: null}, {used_percent: 80, resets_at: 50}], 10), 80)
    }

    function test_countdowns() {
        const now = 0
        compare(F.countdownShort(6 * 86400 + 4 * 3600 + 59, now), "6d 4h")
        compare(F.countdownShort(2 * 3600 + 13 * 60, now), "2h13m")
        compare(F.countdownShort(45 * 60, now), "45m")
        compare(F.countdownShort(30, now), "1m")
        compare(F.countdownShort(null, now), "")
        compare(F.countdownShort(-5, now), "")
        compare(F.countdownLong(2 * 3600 + 13 * 60, now), "2 h 13 min")
        compare(F.countdownLong(6 * 86400 + 4 * 3600, now), "6 d 4 h")
    }

    function test_ageText() {
        const t = Date.parse("2026-10-03T19:42:00+02:00")
        compare(F.ageText("2026-10-03T19:41:30+02:00", t), "30 s ago")
        compare(F.ageText("2026-10-03T19:37:00+02:00", t), "5 min ago")
        compare(F.ageText("2026-10-03T17:42:00+02:00", t), "2 h ago")
        compare(F.ageText("2026-09-30T19:42:00+02:00", t), "3 d ago")
        compare(F.ageText(null, t), "—")
    }

    function test_texts() {
        compare(F.sourceText("oauth"), "OAuth")
        compare(F.sourceText("statusline"), "Status line")
        compare(F.sourceText("session_log"), "Session log")
        compare(F.sourceText(null), "—")
        compare(F.tokenBreakdown({input: 1000, output: 2, cache_read: 3, cache_write: 4, total: 1009}),
                "Input: 1,000\nOutput: 2\nCache read: 3\nCache write: 4")
        compare(F.dayTooltip({date: "2026-09-04", total: 123456}), "Sep 4: 123,456 tokens")
        compare(F.dayTooltip({date: "2026-10-04", total: 1234}), "Oct 4: 1,234 tokens")
    }

    function test_statusMessage() {
        const t = Date.parse("2026-10-03T19:42:00+02:00")
        const fresh = {generated_at: "2026-10-03T19:41:00+02:00"}
        const old = {generated_at: "2026-10-03T19:30:00+02:00"}
        compare(F.statusMessage("", fresh, t), "")
        verify(F.statusMessage("", old, t).indexOf("systemctl --user status agent-stats.timer") >= 0)
        verify(F.statusMessage("nofile", null, t).indexOf("No data yet") === 0)
        verify(F.statusMessage("schema", null, t).indexOf("install.sh") >= 0)
        verify(F.statusMessage("parse", null, t).length > 0)
    }

    function test_tooltip() {
        const now = 0
        const stats = {providers: {
            claude: {limits: [{label: "5 h", used_percent: 42, resets_at: 2 * 3600 + 13 * 60},
                              {label: "Week", used_percent: 18, resets_at: null}]},
            codex: {limits: []}}}
        const providers = [{key: "claude", name: "Claude"}, {key: "codex", name: "Codex"}]
        compare(F.tooltipText(stats, providers, now),
                "Claude · 5 h: 42 % · Reset in 2 h 13 min\nClaude · Week: 18 %\nCodex: no limit data")
        compare(F.limitLine("Codex", {label: "Week", used_percent: 8, resets_at: -1}, now),
                "Codex · Week: reset")
        compare(F.tooltipText(null, providers, now), "No data")
    }

    function test_authHint() {
        compare(F.authHint(undefined), "")
        compare(F.authHint(null), "")
        compare(F.authHint({status: "ok", expires_at: "2026-10-04T19:29:15+02:00"}), "")
        compare(F.authHint({status: "expired", expires_at: "2026-10-04T03:13:02+02:00"}),
                "Login expired – run claude in a terminal")
        compare(F.authHint({status: "missing", expires_at: null}),
                "No login found – run claude in a terminal")
    }

    function test_tooltip_with_auth_hint() {
        const stats = {providers: {claude: {limits: [{label: "Week", used_percent: 18, resets_at: null}],
                                            auth: {status: "expired", expires_at: null}}}}
        compare(F.tooltipText(stats, [{key: "claude", name: "Claude"}], 0),
                "Claude · Week: 18 %\nClaude: Login expired – run claude in a terminal")
        const empty = {providers: {claude: {limits: [], auth: {status: "missing", expires_at: null}}}}
        compare(F.tooltipText(empty, [{key: "claude", name: "Claude"}], 0),
                "Claude: no limit data\nClaude: No login found – run claude in a terminal")
    }

    function test_forecastText() {
        const now = 1000
        const base = {label: "5 h", used_percent: 40, resets_at: now + 4 * 3600}
        compare(F.forecastText(base, now), "")
        compare(F.forecastText(Object.assign({}, base, {forecast: {status: "enough"}}), now),
                "Lasts until reset at current pace")
        const full = Object.assign({}, base, {forecast: {status: "full", eta: now + 80 * 60}})
        const text = F.forecastText(full, now)
        verify(text.indexOf("Full in ~1 h 20 min at current pace (") === 0, text)
        verify(/\(\d\d:\d\d\)$/.test(text), text)
        compare(F.forecastText(Object.assign({}, full, {forecast: {status: "full", eta: now - 5}}), now),
                "Full soon at current pace")
        compare(F.forecastText(Object.assign({}, full, {resets_at: now - 1}), now), "")
    }

    function test_limitLine_with_forecast() {
        const now = 0
        const l = {label: "5 h", used_percent: 40, resets_at: 4 * 3600,
                   forecast: {status: "full", eta: 80 * 60}}
        compare(F.limitLine("Claude", l, now), "Claude · 5 h: 40 % · Reset in 4 h 0 min · full in ~1 h 20 min")
        l.forecast = {status: "enough"}
        compare(F.limitLine("Claude", l, now), "Claude · 5 h: 40 % · Reset in 4 h 0 min · lasts until reset")
    }

    function test_forecastText_far_away_shows_weekday() {
        const now = 1000
        const week = {label: "Week", used_percent: 40, resets_at: now + 6 * 86400,
                      forecast: {status: "full", eta: now + 2 * 86400 + 4 * 3600}}
        const text = F.forecastText(week, now)
        verify(text.indexOf("Full in ~2 d 4 h at current pace (") === 0, text)
        verify(/\((Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d\d:\d\d\)$/.test(text), text)
        compare(F.forecastShort(week, now), "full in ~2 d 4 h")
    }

    function test_limitsStale() {
        const t = Date.parse("2026-10-04T18:00:00+02:00")
        const prov = (iso, limits) => ({limits_updated_at: iso, limits: limits, limits_source: "session_log"})
        const one = [{label: "Week", used_percent: 8, resets_at: null}]
        verify(!F.limitsStale(prov("2026-10-04T12:00:00+02:00", one), t))          // exactly 6 h
        verify(F.limitsStale(prov("2026-10-04T11:59:59+02:00", one), t))           // just over
        verify(!F.limitsStale(prov("2026-09-29T21:30:00+02:00", []), t))           // no limits
        verify(!F.limitsStale(prov(null, one), t))
        verify(!F.limitsStale(undefined, t))
    }

    function test_footerText() {
        const t = Date.parse("2026-10-04T18:00:00+02:00")
        const lim = [{label: "Week", used_percent: 8, resets_at: null}]
        compare(F.footerText({limits_updated_at: "2026-10-04T17:59:30+02:00", limits_source: "oauth", limits: lim}, t),
                "Updated 30 s ago · OAuth")
        compare(F.footerText({limits_updated_at: "2026-09-30T18:00:00+02:00", limits_source: "session_log", limits: lim}, t),
                "Updated 4 d ago · Session log · stale")
        compare(F.footerText(undefined, t), "")
    }

    function test_tooltip_marks_stale_limits() {
        const nowSec = Date.parse("2026-10-04T18:00:00+02:00") / 1000
        const stats = {providers: {codex: {limits_updated_at: "2026-09-30T18:00:00+02:00",
                                           limits: [{label: "Week", used_percent: 8, resets_at: null}]}}}
        compare(F.tooltipText(stats, [{key: "codex", name: "Codex"}], nowSec), "Codex · Week: 8 % (stale)")
    }

    function test_breakdownTitle() {
        const title = F.breakdownTitle({basis: "window", since: "2026-09-29T06:00:00+02:00"})
        verify(/^Since weekly reset \((Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d\d:\d\d\)$/.test(title), title)
        compare(F.breakdownTitle({basis: "7d", since: "2026-09-27T12:00:00+02:00"}), "Last 7 days")
        compare(F.breakdownTitle(null), "")
    }

    function test_breakdownRows_and_percent() {
        const rows = F.breakdownRows([{name: "website", total: 880}, {name: "Other", total: 4}, {name: "x", total: 116}], 1000)
        compare(rows.length, 3)
        compare(rows[0].name, "website")
        compare(rows[0].pct, 88)
        compare(F.percentText(rows[0].pct), "88 %")
        compare(F.percentText(rows[1].pct), "<1 %")
        compare(F.percentText(0), "0 %")
        compare(F.breakdownRows([{name: "a", total: 5}], 0)[0].pct, 0)
        compare(F.breakdownRows(undefined, 10).length, 0)
        compare(F.breakdownTooltip(rows[0]), "880 tokens")
    }

    function test_ringValues() {
        const now = 1000
        const five = (pct, reset) => ({label: "5 h", used_percent: pct, resets_at: reset === undefined ? null : reset,
                                       window_minutes: 300})
        const week = (pct, label) => ({label: label || "Week", used_percent: pct, resets_at: null, window_minutes: 10080})
        compare(F.ringValues([five(8), week(36), week(9, "Week Fable")], now), {outer: 36, inner: 8})
        compare(F.ringValues([week(7)], now), {outer: 7, inner: null})          // Codex: week only
        compare(F.ringValues([five(40)], now), {outer: null, inner: 40})
        compare(F.ringValues([five(90, 999), week(20), week(60, "Week Fable")], now), {outer: 60, inner: 0})  // reset has passed
        compare(F.ringValues([], now), {outer: null, inner: null})
        compare(F.ringValues(null, now), {outer: null, inner: null})
        // only a window of another length: highest value on the outer ring, as before
        compare(F.ringValues([{label: "2 d", used_percent: 15, resets_at: null, window_minutes: 2880}], now),
                {outer: 15, inner: null})
    }
}
