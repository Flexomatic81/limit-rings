// The macOS widget's view model: collector output → one card per shown provider, built with core.mjs.

// From its place in the plasmoid; the build (tools/build_uebersicht.py) points this at the copy beside it.
import * as C from "../../../plasmoid/io.github.flexomatic81.limitrings/contents/code/core.mjs"

export const DEFAULTS = {providers: ["claude", "codex"], login: ["claude", "codex"], remaining: false,
                         thresholds: [70, 90]}
const NAMES = {claude: "Claude", codex: "Codex"}
const INSTALL_URL = "https://www.python.org/downloads/macos/"

// Two whole percentages, 1-100, warning below critical – anything else is the default, as in the collector.
function _thresholds(value) {
    const ok = Array.isArray(value) && value.length === 2 && value.every(Number.isInteger)
               && value[0] >= 1 && value[0] < value[1] && value[1] <= 100
    return ok ? value : DEFAULTS.thresholds
}

const KNOWN = Object.keys(NAMES)
const _known = list => [...new Set(list.filter(k => KNOWN.includes(k)))]
const _pixels = v => (typeof v === "number" && Number.isFinite(v) ? Math.round(v) : 40)

// Clean settings from hand-edited JSON: nothing malformed reaches the shell command or the CSS.
// A broken "login" means no login at all, never all of them.
export function settingsFrom(raw) {
    const r = raw && typeof raw === "object" ? raw : {}
    return {providers: Array.isArray(r.providers) ? _known(r.providers) : DEFAULTS.providers,
            login: Array.isArray(r.login) ? _known(r.login) : [],
            remaining: r.remaining === true, thresholds: _thresholds(r.thresholds),
            top: _pixels(r.top), left: _pixels(r.left)}
}

function _ring(limit, nowSec, s) {
    if (!limit) return null
    return {percent: C.shownPercent(limit, nowSec, s.remaining),
            share: C.shownShare(C.elapsedShare(limit, nowSec), s.remaining),
            severity: C.limitSeverity(limit, nowSec, s.thresholds[0], s.thresholds[1])}
}

function _row(limit, nowSec, s, tr) {
    return {label: C.limitName(limit, tr), percentText: C.limitPercentText(limit, nowSec, s.remaining, tr),
            percent: C.shownPercent(limit, nowSec, s.remaining),
            countdown: C.countdownLong(limit.resets_at, nowSec),
            severity: C.limitSeverity(limit, nowSec, s.thresholds[0], s.thresholds[1]),
            share: C.shownShare(C.elapsedShare(limit, nowSec), s.remaining), note: C.barNote(limit, nowSec, tr)}
}

function _card(key, p, nowMs, s, tr) {
    const nowSec = nowMs / 1000
    const limits = Array.isArray(p.limits) ? p.limits : []
    const r = C.ringLimits(limits, nowSec)
    const series = C.chartSeries(p, "days")
    const top = Math.max(0, ...series.map(e => e.total))
    const tokens = p.tokens || {}
    const total = name => C.compactNumber((tokens[name] && tokens[name].total) || 0, tr)
    // the plasmoid's labels (ProviderCard.qml), so de.json already has them
    const labels = {today: tr.i18nc("token totals", "Today"), week: tr.i18nc("token totals", "Week"),
                    month: tr.i18nc("token totals", "Month")}
    return {
        key, name: NAMES[key] || key, plan: C.planName(p.plan),
        hint: C.authHint(p.auth, null, tr) || C.loginHint(p, {key}, tr) || (limits.length ? "" : tr.i18n("No limit data")),
        errors: C.errorText(p.errors, tr),   // own line: a login hint must not hide that the numbers are incomplete
        rings: {outer: _ring(r.outer, nowSec, s), inner: _ring(r.inner, nowSec, s)},
        rows: limits.map(l => _row(l, nowSec, s, tr)),
        tokens: ["today", "week", "month"].map(name => ({label: labels[name], value: total(name)})),
        series: series.map(e => ({date: e.date, total: e.total, height: top > 0 ? e.total / top : 0,
                                  tip: tr.i18nc("daily chart tooltip: %1 date, %2 token count", "%1: %2 tokens",
                                                e.date, tr.integer(e.total))})),
        footer: limits.length ? C.footerText(p, nowMs, 0, tr) : "",
        stale: C.limitsStale(p, nowMs)
    }
}

export function view(output, previous, nowMs, settings, tr) {
    const s = Object.assign({}, DEFAULTS, settings)
    s.thresholds = _thresholds(s.thresholds)
    const read = C.readCollectorOutput(output.exitCode, output.stdout)
    const stats = read.stats || (previous ? previous.stats : null)
    const status = C.statusMessage(read.error, stats, nowMs, {pythonVersion: read.pythonVersion, installUrl: INSTALL_URL}, tr)
    const providers = stats && stats.providers ? stats.providers : {}
    const cards = s.providers.filter(k => providers[k]).map(k => _card(k, providers[k], nowMs, s, tr))
    return {cards, status, stats}
}
