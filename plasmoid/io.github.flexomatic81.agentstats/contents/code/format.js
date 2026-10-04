.pragma library

function germanInt(n) {
    const s = String(Math.round(Math.abs(n)))
    const grouped = s.replace(/\B(?=(\d{3})+(?!\d))/g, ".")
    return (n < 0 ? "-" : "") + grouped
}

function _decimal(x) {
    return x.toFixed(1).replace(".", ",")
}

function compactNumber(n) {
    if (n < 1000) return String(Math.round(n))
    if (n < 999500) return Math.round(n / 1000) + " k"
    if (n < 999950000) return _decimal(n / 1e6) + " M"
    return _decimal(n / 1e9) + " Mrd"
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

// Werte für den Ring in der Leiste: außen das höchste Wochenlimit, innen das 5-h-Limit
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
    if (s < 60) return "vor " + s + " s"
    if (s < 3600) return "vor " + Math.floor(s / 60) + " min"
    if (s < 86400) return "vor " + Math.floor(s / 3600) + " h"
    return "vor " + Math.floor(s / 86400) + " d"
}

function sourceText(src) {
    if (src === "oauth") return "OAuth"
    if (src === "statusline") return "Statuszeile"
    if (src === "session_log") return "Sitzungslog"
    return "—"
}

function tokenBreakdown(t) {
    return "Input: " + germanInt(t.input) + "\nOutput: " + germanInt(t.output)
        + "\nCache lesen: " + germanInt(t.cache_read) + "\nCache schreiben: " + germanInt(t.cache_write)
}

function dayTooltip(entry) {
    const p = entry.date.split("-")
    return p[2] + "." + p[1] + ".: " + germanInt(entry.total) + " Tokens"
}

const STALE_MS = 300000
const LIMITS_STALE_MS = 6 * 3600 * 1000

// Limit-Daten älter als 6 h (z. B. Codex-Log von vor Tagen): Anzeige als „veraltet“
function limitsStale(provider, nowMs) {
    if (!provider || !provider.limits_updated_at || !provider.limits || provider.limits.length === 0)
        return false
    const t = Date.parse(provider.limits_updated_at)
    return !isNaN(t) && nowMs - t > LIMITS_STALE_MS
}

function footerText(provider, nowMs) {
    if (!provider) return ""
    return "Stand " + ageText(provider.limits_updated_at, nowMs) + " · " + sourceText(provider.limits_source)
        + (limitsStale(provider, nowMs) ? " · veraltet" : "")
}

function statusMessage(loadError, stats, nowMs) {
    if (loadError === "nofile")
        return "Noch keine Daten – läuft der Collector? systemctl --user status agent-stats.timer"
    if (loadError === "schema")
        return "Unbekanntes Datenformat – Plasmoid und Collector passen nicht zusammen. install.sh erneut ausführen."
    if (loadError === "parse")
        return "stats.json ist nicht lesbar."
    if (stats && nowMs - Date.parse(stats.generated_at) > STALE_MS)
        return "Collector läuft nicht – Daten " + ageText(stats.generated_at, nowMs)
            + ". Prüfen: systemctl --user status agent-stats.timer"
    return ""
}

const _WEEKDAYS = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"]

function _time(d) {
    return (d.getHours() < 10 ? "0" : "") + d.getHours() + ":" + (d.getMinutes() < 10 ? "0" : "") + d.getMinutes()
}

// „Sa 14:00“
function _weekdayClock(epochSec) {
    const d = new Date(epochSec * 1000)
    return _WEEKDAYS[d.getDay()] + " " + _time(d)
}

// Uhrzeit, ab einem Tag Abstand mit Wochentag
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
    if (!f.full) return "Reicht bei aktuellem Tempo bis zum Reset"
    if (!f.rest) return "Bei aktuellem Tempo gleich voll"
    return "Bei aktuellem Tempo voll in ~" + f.rest + " (" + _clock(f.eta, nowSec) + ")"
}

function forecastShort(limit, nowSec) {
    const f = _forecastParts(limit, nowSec)
    if (!f) return ""
    if (!f.full) return "reicht bis Reset"
    return f.rest ? "voll in ~" + f.rest : "gleich voll"
}

function limitLine(name, limit, nowSec) {
    const head = name + " · " + limit.label + ": "
    if (isReset(limit, nowSec)) return head + "zurückgesetzt"
    const rest = countdownLong(limit.resets_at, nowSec)
    const fc = forecastShort(limit, nowSec)
    return head + Math.round(limit.used_percent) + " %" + (rest ? " · Reset in " + rest : "") + (fc ? " · " + fc : "")
}

function authHint(auth) {
    if (!auth || auth.status === "ok") return ""
    if (auth.status === "expired") return "Anmeldung abgelaufen – claude im Terminal starten"
    return "Keine Anmeldung gefunden – claude im Terminal starten"
}

function tooltipText(stats, providers, nowSec) {
    if (!stats) return "Keine Daten"
    const lines = []
    for (let i = 0; i < providers.length; i++) {
        const p = stats.providers[providers[i].key]
        if (!p || !p.limits || p.limits.length === 0)
            lines.push(providers[i].name + ": keine Limit-Daten")
        else {
            const stale = limitsStale(p, nowSec * 1000) ? " (veraltet)" : ""
            for (let j = 0; j < p.limits.length; j++)
                lines.push(limitLine(providers[i].name, p.limits[j], nowSec) + stale)
        }
        const hint = p ? authHint(p.auth) : ""
        if (hint) lines.push(providers[i].name + ": " + hint)
    }
    return lines.join("\n")
}

// Aufschlüsselung nach Projekt/Modell (stats.json: providers.claude.breakdown)
function breakdownTitle(b) {
    if (!b) return ""
    if (b.basis !== "window") return "Letzte 7 Tage"
    return "Seit Wochen-Reset (" + _weekdayClock(Date.parse(b.since) / 1000) + ")"
}

function breakdownRows(list, total) {
    if (!list) return []
    return list.map(item => ({name: item.name, total: item.total, pct: total > 0 ? item.total / total * 100 : 0}))
}

function percentText(pct) {
    if (pct > 0 && pct < 1) return "<1 %"
    return Math.round(pct) + " %"
}

function breakdownTooltip(row) {
    return germanInt(row.total) + " Tokens"
}
