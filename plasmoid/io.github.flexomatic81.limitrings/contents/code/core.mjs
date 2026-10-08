// Display logic shared by the Plasma widget (through format.js) and the macOS Übersicht widget.
// Plain ECMAScript: no Qt, no DOM. Texts take a translator `tr` (see format.js _tr() and macos/…/i18n.mjs).

export function isReset(limit, nowSec) {
    return limit.resets_at !== null && limit.resets_at !== undefined && limit.resets_at <= nowSec
}

export function effectivePercent(limit, nowSec) {
    return isReset(limit, nowSec) ? 0 : limit.used_percent
}

// The "Percentages: Remaining" setting shows what is left instead of what is used. Only the shown values
// change: colours, severity, thresholds and notifications keep going by the usage.
export function shownPercent(limit, nowSec, remaining) {
    const used = effectivePercent(limit, nowSec)
    return remaining ? Math.max(0, 100 - used) : used
}

// The value of the "Number" panel style: the highest usage, or the least that is left
export function shownMax(limits, nowSec, remaining) {
    const used = maxPercent(limits, nowSec)
    return used === null || !remaining ? used : Math.max(0, 100 - used)
}

// The time mark beside a shown value: the share of the window passed, or the share still to come
export function shownShare(elapsed, remaining) {
    return elapsed === null || !remaining ? elapsed : 1 - elapsed
}

export function severity(pct, warn, crit) {
    if (pct >= crit) return "critical"
    if (pct >= warn) return "warning"
    return "normal"
}

export function maxPercent(limits, nowSec) {
    if (!limits || limits.length === 0) return null
    let best = 0
    for (let i = 0; i < limits.length; i++)
        best = Math.max(best, effectivePercent(limits[i], nowSec))
    return best
}

// Severity of one limit: the fixed thresholds, and at least "warning" while the forecast sees it full
// before the reset at the current pace (the same forecast the popup shows)
export function limitSeverity(limit, nowSec, warn, crit) {
    if (!limit) return "normal"
    const sev = severity(effectivePercent(limit, nowSec), warn, crit)
    const full = !isReset(limit, nowSec) && !!limit.forecast && limit.forecast.status === "full"
    return sev === "normal" && full ? "warning" : sev
}

// Most severe of several limits (the "Number" panel style shows one value for all of them)
export function worstSeverity(limits, nowSec, warn, crit) {
    const order = ["normal", "warning", "critical"]
    let worst = 0
    for (let i = 0; i < (limits ? limits.length : 0); i++)
        worst = Math.max(worst, order.indexOf(limitSeverity(limits[i], nowSec, warn, crit)))
    return order[worst]
}

// Share of the window that has passed (0–1), for the time mark on rings and bars; null if unknown
export function elapsedShare(limit, nowSec) {
    if (!limit || !limit.window_minutes || limit.resets_at === null || limit.resets_at === undefined) return null
    const left = limit.resets_at - nowSec
    if (left <= 0) return null
    return Math.min(1, Math.max(0, 1 - left / (limit.window_minutes * 60)))
}

// The limits behind the panel ring: outer is the highest weekly limit, inner the 5 h limit; with
// neither, the highest limit of any other length goes on the outer ring
export function ringLimits(limits, nowSec) {
    let outer = null, inner = null, any = null
    const higher = (a, b) => a === null || effectivePercent(b, nowSec) > effectivePercent(a, nowSec) ? b : a
    for (let i = 0; i < (limits ? limits.length : 0); i++) {
        const l = limits[i]
        if (l.window_minutes === 300) inner = higher(inner, l)
        else if (l.window_minutes === 10080) outer = higher(outer, l)
        any = higher(any, l)
    }
    return {outer: outer === null && inner === null ? any : outer, inner: inner}
}

// Values for the panel ring (percent per ring, null = no ring)
export function ringValues(limits, nowSec) {
    const r = ringLimits(limits, nowSec)
    return {outer: r.outer ? effectivePercent(r.outer, nowSec) : null,
            inner: r.inner ? effectivePercent(r.inner, nowSec) : null}
}

function _parts(resetsAt, nowSec) {
    if (resetsAt === null || resetsAt === undefined) return null
    const s = resetsAt - nowSec
    if (s <= 0) return null
    const totalMin = Math.max(1, Math.ceil(s / 60))
    return {d: Math.floor(totalMin / 1440), h: Math.floor((totalMin % 1440) / 60), m: totalMin % 60}
}

export function countdownShort(resetsAt, nowSec) {
    const p = _parts(resetsAt, nowSec)
    if (!p) return ""
    if (p.d > 0) return p.d + "d " + p.h + "h"
    if (p.h > 0) return p.h + "h" + (p.m < 10 ? "0" : "") + p.m + "m"
    return p.m + "m"
}

export function countdownLong(resetsAt, nowSec) {
    const p = _parts(resetsAt, nowSec)
    if (!p) return ""
    if (p.d > 0) return p.d + " d " + p.h + " h"
    if (p.h > 0) return p.h + " h " + p.m + " min"
    return p.m + " min"
}

// The chart's ranges; the collector writes one series per range (daily, weekly, monthly)
export const CHART_SERIES = {days: "daily", weeks: "weekly", months: "monthly"}

export function chartSeries(provider, range) {
    return (provider && provider[CHART_SERIES[range] || "daily"]) || []
}

export const STALE_MS = 300000

export const LIMITS_STALE_MS = 6 * 3600 * 1000

// Limit data older than 6 h (e.g. a Codex log from days ago) is shown as "stale"
export function limitsStale(provider, nowMs) {
    if (!provider || !provider.limits_updated_at || !provider.limits || provider.limits.length === 0)
        return false
    const t = Date.parse(provider.limits_updated_at)
    return !isNaN(t) && nowMs - t > LIMITS_STALE_MS
}
