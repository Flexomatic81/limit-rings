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

// ---- Texts: every function takes the translator `tr` ----

function _subst(text, args) {
    return text.replace(/%(\d)/g, (m, d) => args[d - 1] !== undefined ? String(args[d - 1]) : m)
}

// English texts and en-US numbers: the fallback without a catalog, and the translator of the tests
export const ENGLISH = {
    i18n: (text, ...args) => _subst(text, args),
    i18nc: (context, text, ...args) => _subst(text, args),
    i18np: (singular, plural, n, ...args) => _subst(n === 1 ? singular : plural, [n].concat(args)),
    decimal: x => x.toFixed(1),
    integer: n => Math.round(n).toLocaleString("en-US"),
    weekday: d => ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d]
}

export function compactNumber(n, tr) {
    if (n < 1000) return String(Math.round(n))
    if (n < 999500) return Math.round(n / 1000) + " k"
    if (n < 999950000) return tr.decimal(n / 1e6) + " M"
    return tr.decimal(n / 1e9) + " " + tr.i18nc("billion abbreviation", "B")
}

export function ageText(iso, nowMs, tr) {
    if (!iso) return "—"
    const s = Math.max(0, Math.round((nowMs - Date.parse(iso)) / 1000))
    if (s < 60) return tr.i18nc("time ago", "%1 s ago", s)
    if (s < 3600) return tr.i18nc("time ago", "%1 min ago", Math.floor(s / 60))
    if (s < 86400) return tr.i18nc("time ago", "%1 h ago", Math.floor(s / 3600))
    return tr.i18nc("time ago", "%1 d ago", Math.floor(s / 86400))
}

export function sourceText(src, tr) {
    if (src === "oauth") return "OAuth"
    if (src === "statusline") return tr.i18nc("limit data source", "Status line")
    if (src === "session_log") return tr.i18nc("limit data source", "Session log")
    return "—"
}

export function limitPercentText(limit, nowSec, remaining, tr) {
    const pct = Math.round(shownPercent(limit, nowSec, remaining))
    return remaining ? tr.i18nc("%1 = percent of a limit that is still available", "%1 % left", pct) : pct + " %"
}

export function timeOfDay(d) {
    return (d.getHours() < 10 ? "0" : "") + d.getHours() + ":" + (d.getMinutes() < 10 ? "0" : "") + d.getMinutes()
}

// Clock time, with the weekday once it is a day or more away
export function clock(epochSec, nowSec, tr) {
    const d = new Date(epochSec * 1000)
    return epochSec - nowSec >= 86400 ? tr.weekday(d.getDay()) + " " + timeOfDay(d) : timeOfDay(d)
}

function _forecastParts(limit, nowSec) {
    const f = limit.forecast
    if (!f || isReset(limit, nowSec)) return null
    if (f.status === "enough") return {full: false}
    return {full: true, rest: countdownLong(f.eta, nowSec), eta: f.eta}
}

export function forecastText(limit, nowSec, tr) {
    const f = _forecastParts(limit, nowSec)
    if (!f) return ""
    if (!f.full) return tr.i18n("Lasts until reset at current pace")
    if (!f.rest) return tr.i18n("Full soon at current pace")
    return tr.i18n("Full in ~%1 at current pace (%2)", f.rest, clock(f.eta, nowSec, tr))
}

// Line below a bar: only what needs attention – a limit that runs out before its reset, or a window that has reset
export function barNote(limit, nowSec, tr) {
    if (isReset(limit, nowSec))
        return tr.i18nc("limit window has reset, shown below the bar", "Reset – starts again from 0 %")
    const f = _forecastParts(limit, nowSec)
    return f && f.full ? forecastText(limit, nowSec, tr) : ""
}

export function forecastShort(limit, nowSec, tr) {
    const f = _forecastParts(limit, nowSec)
    if (!f) return ""
    if (!f.full) return tr.i18n("lasts until reset")
    return f.rest ? tr.i18n("full in ~%1", f.rest) : tr.i18n("full soon")
}

function _windowText(minutes) {
    if (minutes % 1440 === 0) return (minutes / 1440) + " d"
    if (minutes % 60 === 0) return (minutes / 60) + " h"
    return minutes + " min"
}

// Plan as the providers spell it in their login or usage data → product name (not translated);
// an unknown plan is shown as it comes, so a new one never disappears
const _PLAN_NAMES = {free: "Free", plus: "Plus", pro: "Pro", prolite: "Pro Lite", max: "Max", team: "Team",
                     business: "Business", enterprise: "Enterprise", edu: "Edu"}

export function planName(plan) {
    if (!plan) return ""
    return _PLAN_NAMES[String(plan).toLowerCase()] || String(plan)
}

// Display name of a limit (stats.json carries only window and model)
export function limitName(limit, tr) {
    const m = limit.window_minutes
    if (m === 10080)
        return limit.model ? tr.i18nc("limit name: weekly window of one model, %1 = model", "Week %1", limit.model)
                           : tr.i18nc("limit name: weekly window", "Week")
    if (m === 300 && !limit.model) return tr.i18nc("limit name: 5-hour window", "5 h")
    if (!m) return limit.id
    return _windowText(m) + (limit.model ? " " + limit.model : "")
}

export function errorText(errors, tr) {
    if (!errors) return ""
    return errors.map(e => {
        if (e.code === "logs_unreadable")
            return tr.i18np("%1 file unreadable – numbers incomplete", "%1 files unreadable – numbers incomplete", e.count)
        if (e.code === "logs_failed") return tr.i18n("Data could not be processed")
        if (e.code === "limits_unavailable") return tr.i18n("Limits unavailable")
        if (e.code === "account_invalid") return tr.i18n("Account settings are invalid – check the directory")
        return e.code
    }).join("; ")
}

export function authHint(auth, entry, tr) {
    if (!auth || auth.status === "ok") return ""
    if (entry && entry.account) {
        const how = entry.provider === "codex" ? tr.i18n("start codex with this CODEX_HOME")
                                               : tr.i18n("start claude with this config directory")
        return auth.status === "expired" ? tr.i18n("Login in %1 expired – %2", entry.dir, how)
                                         : tr.i18n("No login in %1 – %2", entry.dir, how)
    }
    if (auth.status === "expired") return tr.i18n("Login expired – run claude in a terminal")
    return tr.i18n("No login found – run claude in a terminal")
}

// Without login a provider gets its limits only from local copies: say where they come from while there are none
export function loginHint(provider, entry, tr) {
    if (!provider || provider.login !== false || (provider.limits && provider.limits.length)) return ""
    const key = entry && entry.account ? entry.provider : (entry ? entry.key : "")
    if (key === "codex")
        return tr.i18n("No limits without login – they come from the session logs once you use codex in a terminal")
    if (entry && entry.account) return tr.i18n("No limits without login for additional accounts")
    return tr.i18n("No limits without login – they come from the status line while claude runs in a terminal")
}

export const REFRESH_HINT_MS = 60000  // how long the hint stays after "Refresh now"

// After "Refresh now": when the limits will be asked for again (the collector keeps its 5-minute interval
// and any pause); empty when no refresh happened lately or the limits were just asked for.
export function refreshHint(provider, nowMs, refreshedAtMs, tr) {
    if (!provider || !refreshedAtMs || nowMs - refreshedAtMs > REFRESH_HINT_MS) return ""
    const next = provider.limits_next_request_at ? Date.parse(provider.limits_next_request_at) : NaN
    if (!(next > nowMs)) return ""
    return tr.i18nc("%1 = clock time; shown after a manual refresh", "limits again from %1",
                    clock(next / 1000, nowMs / 1000, tr))
}

// After a rate limit (HTTP 429) the collector stops asking until the provider allows it again.
function _pauseText(iso, nowMs, tr) {
    const until = iso ? Date.parse(iso) : NaN
    if (!(until > nowMs)) return ""
    return " · " + tr.i18nc("%1 = clock time; the provider asked to wait before the next request",
                            "paused by the provider until %1", clock(until / 1000, nowMs / 1000, tr))
}

export function footerText(provider, nowMs, refreshedAtMs, tr) {
    if (!provider) return ""
    const hint = refreshHint(provider, nowMs, refreshedAtMs, tr)
    return tr.i18nc("%1 = age such as '5 min ago', %2 = data source", "Updated %1 · %2",
                    ageText(provider.limits_updated_at, nowMs, tr), sourceText(provider.limits_source, tr))
        + (limitsStale(provider, nowMs) ? " · " + tr.i18nc("limit data is outdated", "stale") : "")
        + _pauseText(provider.limits_paused_until, nowMs, tr)
        + (hint ? " · " + hint : "")
}

// ---- Collector output and status messages ----

export const ENVELOPE = 1   // version of the collector output this widget understands (collector/limit_rings/widget.py)
export const LOG_PATH = "~/.cache/limit-rings/collector.log"
// stop waits for a running pass of the service; only then may the unit files (the collector's guard) go.
export const LEGACY_COMMAND = "systemctl --user stop limit-rings.timer limit-rings.service && systemctl --user disable limit-rings.timer && rm ~/.config/systemd/user/limit-rings.timer ~/.config/systemd/user/limit-rings.service"

// One collector pass as the widget sees it: exit code and stdout of run.py.
export function readCollectorOutput(exitCode, stdout) {
    const out = {stats: null, notices: [], error: "", pythonVersion: ""}
    if (exitCode === 127) {
        out.error = "nopython"
        return out
    }
    let env
    try {
        env = JSON.parse(stdout)
    } catch (e) {
        env = null
    }
    if (!env || typeof env !== "object" || typeof env.envelope !== "number") {
        out.error = "parse"
        return out
    }
    if (env.error === "python-too-old") {
        out.error = "oldpython"
        out.pythonVersion = String(env.version || "")
        return out
    }
    // A newer collector than this QML: the package was updated, Plasma still runs the old widget code.
    if (env.envelope > ENVELOPE || (env.stats && env.stats.schema !== 2)) {
        out.error = "restart"
        return out
    }
    out.stats = env.stats && typeof env.stats === "object" ? env.stats : null
    out.notices = Array.isArray(env.notices)
        ? env.notices.filter(n => n && typeof n === "object" && typeof n.summary === "string") : []
    if (env.error === "legacy-timer") out.error = "legacy"
    else if (exitCode !== 0) out.error = "failed"
    else if (!out.stats) out.error = "nodata"
    return out
}

export function statusMessage(loadError, stats, nowMs, info, tr) {
    const install = info && info.installCommand ? " " + tr.i18n("Install it with: %1", info.installCommand)
                  : info && info.installUrl ? " " + tr.i18n("Download it from %1", info.installUrl) : ""
    switch (loadError) {
    case "nopython":
        return tr.i18n("Python 3 not found – Limit Rings needs Python 3.10 or newer.") + install
    case "oldpython":
        return tr.i18n("Python %1 is too old – Limit Rings needs 3.10 or newer.", info ? info.pythonVersion : "") + install
    case "restart":
        return tr.i18n("Limit Rings was updated – restart Plasma or log out and back in to load the new version.")
    case "parse":
        return tr.i18n("The collector output is not readable. Log: %1", LOG_PATH)
    case "failed":
        return tr.i18n("The last collector run failed. Log: %1", LOG_PATH)
    case "nodata":
        return tr.i18n("No data yet – the first collector run is still in progress.")
    case "legacy":
        return tr.i18n("An older Limit Rings installation still collects in the background. Remove it with: %1", LEGACY_COMMAND)
    }
    if (stats && nowMs - Date.parse(stats.generated_at) > STALE_MS)
        return tr.i18n("Data from %1 – the collector has not run since. Log: %2", ageText(stats.generated_at, nowMs, tr), LOG_PATH)
    return ""
}
