.pragma library

// Translation: main.qml hands over KDE's i18n functions and the system locale via init();
// without that (e.g. in tests) the English source texts and an English locale are used.
function _subst(text, args) {
    return text.replace(/%(\d)/g, (m, d) => args[d - 1] !== undefined ? String(args[d - 1]) : m)
}

const _fallback = {
    i18n: (text, ...args) => _subst(text, args),
    i18nc: (context, text, ...args) => _subst(text, args),
    i18np: (singular, plural, n, ...args) => _subst(n === 1 ? singular : plural, [n].concat(args)),
    locale: Qt.locale("en_US")
}
let _tr = _fallback

function init(tr) {
    _tr = tr ? Object.assign({}, _fallback, tr) : _fallback
    return true
}

// The translator of a removed widget instance may throw or return nothing: fall back to English then.
function _call(name, args) {
    try {
        const out = _tr[name].apply(null, args)
        if (typeof out === "string") return out
    } catch (e) {
    }
    return _fallback[name].apply(null, args)
}

function i18n(...args) { return _call("i18n", args) }
function i18nc(...args) { return _call("i18nc", args) }
function i18np(...args) { return _call("i18np", args) }

const _SHORT_FORMAT = 1  // Locale.ShortFormat (QML enums are not visible in a .pragma library)

function formatInt(n) {
    return _tr.locale.toString(Math.round(n), "f", 0)
}

function _decimal(x) {
    return _tr.locale.toString(x, "f", 1)
}

function compactNumber(n) {
    if (n < 1000) return String(Math.round(n))
    if (n < 999500) return Math.round(n / 1000) + " k"
    if (n < 999950000) return _decimal(n / 1e6) + " M"
    return _decimal(n / 1e9) + " " + i18nc("billion abbreviation", "B")
}

function isReset(limit, nowSec) {
    return limit.resets_at !== null && limit.resets_at !== undefined && limit.resets_at <= nowSec
}

function effectivePercent(limit, nowSec) {
    return isReset(limit, nowSec) ? 0 : limit.used_percent
}

function severity(pct, warn, crit) {
    if (pct >= crit) return "critical"
    if (pct >= warn) return "warning"
    return "normal"
}

function maxPercent(limits, nowSec) {
    if (!limits || limits.length === 0) return null
    let best = 0
    for (let i = 0; i < limits.length; i++)
        best = Math.max(best, effectivePercent(limits[i], nowSec))
    return best
}

// Values for the panel ring: outer is the highest weekly limit, inner the 5 h limit
function ringValues(limits, nowSec) {
    let outer = null, inner = null
    for (let i = 0; i < (limits ? limits.length : 0); i++) {
        const l = limits[i], pct = effectivePercent(l, nowSec)
        if (l.window_minutes === 300) inner = inner === null ? pct : Math.max(inner, pct)
        else if (l.window_minutes === 10080) outer = outer === null ? pct : Math.max(outer, pct)
    }
    if (outer === null && inner === null) outer = maxPercent(limits, nowSec)
    return {outer: outer, inner: inner}
}

function _parts(resetsAt, nowSec) {
    if (resetsAt === null || resetsAt === undefined) return null
    const s = resetsAt - nowSec
    if (s <= 0) return null
    const totalMin = Math.max(1, Math.ceil(s / 60))
    return {d: Math.floor(totalMin / 1440), h: Math.floor((totalMin % 1440) / 60), m: totalMin % 60}
}

function countdownShort(resetsAt, nowSec) {
    const p = _parts(resetsAt, nowSec)
    if (!p) return ""
    if (p.d > 0) return p.d + "d " + p.h + "h"
    if (p.h > 0) return p.h + "h" + (p.m < 10 ? "0" : "") + p.m + "m"
    return p.m + "m"
}

function countdownLong(resetsAt, nowSec) {
    const p = _parts(resetsAt, nowSec)
    if (!p) return ""
    if (p.d > 0) return p.d + " d " + p.h + " h"
    if (p.h > 0) return p.h + " h " + p.m + " min"
    return p.m + " min"
}

function ageText(iso, nowMs) {
    if (!iso) return "—"
    const s = Math.max(0, Math.round((nowMs - Date.parse(iso)) / 1000))
    if (s < 60) return i18nc("time ago", "%1 s ago", s)
    if (s < 3600) return i18nc("time ago", "%1 min ago", Math.floor(s / 60))
    if (s < 86400) return i18nc("time ago", "%1 h ago", Math.floor(s / 3600))
    return i18nc("time ago", "%1 d ago", Math.floor(s / 86400))
}

function sourceText(src) {
    if (src === "oauth") return "OAuth"
    if (src === "statusline") return i18nc("limit data source", "Status line")
    if (src === "session_log") return i18nc("limit data source", "Session log")
    return "—"
}

function tokenBreakdown(t) {
    return i18n("Input: %1\nOutput: %2\nCache read: %3\nCache write: %4", formatInt(t.input), formatInt(t.output),
                formatInt(t.cache_read), formatInt(t.cache_write))
}

function dayTooltip(entry) {
    const p = entry.date.split("-")
    const date = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]))
    const format = i18nc("Qt date format for the daily chart tooltip (day and month)", "MMM d")
    return i18nc("daily chart tooltip: %1 date, %2 token count", "%1: %2 tokens",
                 date.toLocaleDateString(_tr.locale, format), formatInt(entry.total))
}

const STALE_MS = 300000
const _STATUS_COMMAND = "systemctl --user status agent-stats.timer"
const LIMITS_STALE_MS = 6 * 3600 * 1000

// Limit data older than 6 h (e.g. a Codex log from days ago) is shown as "stale"
function limitsStale(provider, nowMs) {
    if (!provider || !provider.limits_updated_at || !provider.limits || provider.limits.length === 0)
        return false
    const t = Date.parse(provider.limits_updated_at)
    return !isNaN(t) && nowMs - t > LIMITS_STALE_MS
}

function footerText(provider, nowMs) {
    if (!provider) return ""
    return i18nc("%1 = age such as '5 min ago', %2 = data source", "Updated %1 · %2",
                 ageText(provider.limits_updated_at, nowMs), sourceText(provider.limits_source))
        + (limitsStale(provider, nowMs) ? " · " + i18nc("limit data is outdated", "stale") : "")
}

function statusMessage(loadError, stats, nowMs) {
    if (loadError === "nofile")
        return i18n("No data yet – is the collector running? %1", _STATUS_COMMAND)
    if (loadError === "schema")
        return i18n("Unknown data format – plasmoid and collector don't match. Run install.sh again.")
    if (loadError === "parse")
        return i18n("stats.json is not readable.")
    if (stats && nowMs - Date.parse(stats.generated_at) > STALE_MS)
        return i18n("Collector not running – data from %1. Check: %2", ageText(stats.generated_at, nowMs), _STATUS_COMMAND)
    return ""
}

function _time(d) {
    return (d.getHours() < 10 ? "0" : "") + d.getHours() + ":" + (d.getMinutes() < 10 ? "0" : "") + d.getMinutes()
}

// "Sat 14:00"
function _weekdayClock(epochSec) {
    const d = new Date(epochSec * 1000)
    return _tr.locale.standaloneDayName(d.getDay(), _SHORT_FORMAT) + " " + _time(d)
}

// Clock time, with the weekday once it is a day or more away
function _clock(epochSec, nowSec) {
    return epochSec - nowSec >= 86400 ? _weekdayClock(epochSec) : _time(new Date(epochSec * 1000))
}

function _forecastParts(limit, nowSec) {
    const f = limit.forecast
    if (!f || isReset(limit, nowSec)) return null
    if (f.status === "enough") return {full: false}
    return {full: true, rest: countdownLong(f.eta, nowSec), eta: f.eta}
}

function forecastText(limit, nowSec) {
    const f = _forecastParts(limit, nowSec)
    if (!f) return ""
    if (!f.full) return i18n("Lasts until reset at current pace")
    if (!f.rest) return i18n("Full soon at current pace")
    return i18n("Full in ~%1 at current pace (%2)", f.rest, _clock(f.eta, nowSec))
}

function forecastShort(limit, nowSec) {
    const f = _forecastParts(limit, nowSec)
    if (!f) return ""
    if (!f.full) return i18n("lasts until reset")
    return f.rest ? i18n("full in ~%1", f.rest) : i18n("full soon")
}

function _windowText(minutes) {
    if (minutes % 1440 === 0) return (minutes / 1440) + " d"
    if (minutes % 60 === 0) return (minutes / 60) + " h"
    return minutes + " min"
}

// Display name of a limit (stats.json carries only window and model)
function limitName(limit) {
    const m = limit.window_minutes
    if (m === 10080)
        return limit.model ? i18nc("limit name: weekly window of one model, %1 = model", "Week %1", limit.model)
                           : i18nc("limit name: weekly window", "Week")
    if (m === 300 && !limit.model) return i18nc("limit name: 5-hour window", "5 h")
    if (!m) return limit.id
    return _windowText(m) + (limit.model ? " " + limit.model : "")
}

function errorText(errors) {
    if (!errors) return ""
    return errors.map(e => {
        if (e.code === "logs_unreadable")
            return i18np("%1 file unreadable – numbers incomplete", "%1 files unreadable – numbers incomplete", e.count)
        if (e.code === "logs_failed") return i18n("Data could not be processed")
        if (e.code === "limits_unavailable") return i18n("Limits unavailable")
        return e.code
    }).join("; ")
}

function limitLine(name, limit, nowSec) {
    const head = name + " · " + limitName(limit) + ": "
    if (isReset(limit, nowSec)) return head + i18nc("limit state", "reset")
    const rest = countdownLong(limit.resets_at, nowSec)
    const fc = forecastShort(limit, nowSec)
    return head + Math.round(limit.used_percent) + " %" + (rest ? " · " + i18n("Reset in %1", rest) : "") + (fc ? " · " + fc : "")
}

function authHint(auth) {
    if (!auth || auth.status === "ok") return ""
    if (auth.status === "expired") return i18n("Login expired – run claude in a terminal")
    return i18n("No login found – run claude in a terminal")
}

function tooltipText(stats, providers, nowSec) {
    if (!stats) return i18n("No data")
    const lines = []
    for (let i = 0; i < providers.length; i++) {
        const p = stats.providers[providers[i].key]
        if (!p || !p.limits || p.limits.length === 0)
            lines.push(providers[i].name + ": " + i18n("no limit data"))
        else {
            const stale = limitsStale(p, nowSec * 1000) ? " (" + i18nc("limit data is outdated", "stale") + ")" : ""
            for (let j = 0; j < p.limits.length; j++)
                lines.push(limitLine(providers[i].name, p.limits[j], nowSec) + stale)
        }
        const hint = p ? authHint(p.auth) : ""
        if (hint) lines.push(providers[i].name + ": " + hint)
    }
    return lines.join("\n")
}

// Breakdown by project/model (stats.json: providers.claude.breakdown)
function breakdownTitle(b) {
    if (!b) return ""
    if (b.basis !== "window") return i18n("Last 7 days")
    return i18n("Since weekly reset (%1)", _weekdayClock(Date.parse(b.since) / 1000))
}

function breakdownRows(list, total) {
    if (!list) return []
    return list.map(item => ({
        name: item.other ? i18nc("breakdown entry for all remaining projects or models", "Other") : item.name,
        total: item.total, other: !!item.other, pct: total > 0 ? item.total / total * 100 : 0}))
}

function percentText(pct) {
    if (pct > 0 && pct < 1) return "<1 %"
    return Math.round(pct) + " %"
}

function breakdownTooltip(row) {
    return i18n("%1 tokens", formatInt(row.total))
}
