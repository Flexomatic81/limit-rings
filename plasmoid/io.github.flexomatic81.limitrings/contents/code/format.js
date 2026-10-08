.pragma library

// Translation: every widget instance hands over KDE's i18n functions and the system locale via
// init() and gives them back via release(); this library is shared by all instances of the widget.
// Without a translator (e.g. in tests) the English source texts and an English locale are used.
function _subst(text, args) {
    return text.replace(/%(\d)/g, (m, d) => args[d - 1] !== undefined ? String(args[d - 1]) : m)
}

const _fallback = {
    i18n: (text, ...args) => _subst(text, args),
    i18nc: (context, text, ...args) => _subst(text, args),
    i18np: (singular, plural, n, ...args) => _subst(n === 1 ? singular : plural, [n].concat(args)),
    locale: Qt.locale("en_US")
}
let _translators = []  // [{handle, tr}], newest last
let _nextHandle = 1

// Registers a translator and returns its handle for release(); init(null) drops all of them.
function init(tr) {
    if (!tr) {
        _translators = []
        return 0
    }
    const handle = _nextHandle++
    _translators.push({handle: handle, tr: Object.assign({}, _fallback, tr)})
    return handle
}

function release(handle) {
    _translators = _translators.filter(t => t.handle !== handle)
}

function _current() {
    return _translators.length > 0 ? _translators[_translators.length - 1].tr : _fallback
}

// The translator of a removed widget instance may throw or return nothing: drop it and use the
// next one, English only when none is left.
function _call(name, args) {
    for (let i = _translators.length - 1; i >= 0; i--) {
        try {
            const out = _translators[i].tr[name].apply(null, args)
            if (typeof out === "string") return out
        } catch (e) {
        }
        _translators.splice(i, 1)
    }
    return _fallback[name].apply(null, args)
}

function i18n(...args) { return _call("i18n", args) }
function i18nc(...args) { return _call("i18nc", args) }
function i18np(...args) { return _call("i18np", args) }

const _SHORT_FORMAT = 1  // Locale.ShortFormat (QML enums are not visible in a .pragma library)

function formatInt(n) {
    return _current().locale.toString(Math.round(n), "f", 0)
}

function _decimal(x) {
    return _current().locale.toString(x, "f", 1)
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

// The "Percentages: Remaining" setting shows what is left instead of what is used. Only the shown values
// change: colours, severity, thresholds and notifications keep going by the usage.
function shownPercent(limit, nowSec, remaining) {
    const used = effectivePercent(limit, nowSec)
    return remaining ? Math.max(0, 100 - used) : used
}

// The value of the "Number" panel style: the highest usage, or the least that is left
function shownMax(limits, nowSec, remaining) {
    const used = maxPercent(limits, nowSec)
    return used === null || !remaining ? used : Math.max(0, 100 - used)
}

// The time mark beside a shown value: the share of the window passed, or the share still to come
function shownShare(elapsed, remaining) {
    return elapsed === null || !remaining ? elapsed : 1 - elapsed
}

function limitPercentText(limit, nowSec, remaining) {
    const pct = Math.round(shownPercent(limit, nowSec, remaining))
    return remaining ? i18nc("%1 = percent of a limit that is still available", "%1 % left", pct) : pct + " %"
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

// Do two colours look different enough to tell states apart? Greyish colours always do.
function _distinct(a, b) {
    if (a.hsvSaturation < 0.25 || b.hsvSaturation < 0.25 || a.hsvHue < 0 || b.hsvHue < 0) return true
    const d = Math.abs(a.hsvHue - b.hsvHue)
    return Math.min(d, 1 - d) >= 30 / 360
}

// Colour for the "normal" state: the accent colour, unless it is too close to the warning or critical
// colour (e.g. an orange accent next to the orange warning colour); then the positive colour, else grey.
// theme: Kirigami.Theme or an object with the same colour properties
function normalColor(theme) {
    const apart = c => _distinct(c, theme.neutralTextColor) && _distinct(c, theme.negativeTextColor)
    if (apart(theme.highlightColor)) return theme.highlightColor
    if (apart(theme.positiveTextColor)) return theme.positiveTextColor
    const t = theme.textColor
    return Qt.rgba(t.r, t.g, t.b, 0.6)
}

// Colour of a ring or bar by severity ("normal" | "warning" | "critical")
function toneFor(sev, theme) {
    return sev === "critical" ? theme.negativeTextColor
         : sev === "warning" ? theme.neutralTextColor
         : normalColor(theme)
}

// Severity of one limit: the fixed thresholds, and at least "warning" while the forecast sees it full
// before the reset at the current pace (the same forecast the popup shows)
function limitSeverity(limit, nowSec, warn, crit) {
    if (!limit) return "normal"
    const sev = severity(effectivePercent(limit, nowSec), warn, crit)
    const full = !isReset(limit, nowSec) && !!limit.forecast && limit.forecast.status === "full"
    return sev === "normal" && full ? "warning" : sev
}

// Most severe of several limits (the "Number" panel style shows one value for all of them)
function worstSeverity(limits, nowSec, warn, crit) {
    const order = ["normal", "warning", "critical"]
    let worst = 0
    for (let i = 0; i < (limits ? limits.length : 0); i++)
        worst = Math.max(worst, order.indexOf(limitSeverity(limits[i], nowSec, warn, crit)))
    return order[worst]
}

// Share of the window that has passed (0–1), for the time mark on rings and bars; null if unknown
function elapsedShare(limit, nowSec) {
    if (!limit || !limit.window_minutes || limit.resets_at === null || limit.resets_at === undefined) return null
    const left = limit.resets_at - nowSec
    if (left <= 0) return null
    return Math.min(1, Math.max(0, 1 - left / (limit.window_minutes * 60)))
}

// The limits behind the panel ring: outer is the highest weekly limit, inner the 5 h limit; with
// neither, the highest limit of any other length goes on the outer ring
function ringLimits(limits, nowSec) {
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
function ringValues(limits, nowSec) {
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
                 date.toLocaleDateString(_current().locale, format), formatInt(entry.total))
}

const STALE_MS = 300000
const LIMITS_STALE_MS = 6 * 3600 * 1000

// Limit data older than 6 h (e.g. a Codex log from days ago) is shown as "stale"
function limitsStale(provider, nowMs) {
    if (!provider || !provider.limits_updated_at || !provider.limits || provider.limits.length === 0)
        return false
    const t = Date.parse(provider.limits_updated_at)
    return !isNaN(t) && nowMs - t > LIMITS_STALE_MS
}

const REFRESH_HINT_MS = 60000  // how long the hint stays after "Refresh now"

// After "Refresh now": when the limits will be asked for again (the collector keeps its 5-minute interval
// and any pause); empty when no refresh happened lately or the limits were just asked for.
function refreshHint(provider, nowMs, refreshedAtMs) {
    if (!provider || !refreshedAtMs || nowMs - refreshedAtMs > REFRESH_HINT_MS) return ""
    const next = provider.limits_next_request_at ? Date.parse(provider.limits_next_request_at) : NaN
    if (!(next > nowMs)) return ""
    return i18nc("%1 = clock time; shown after a manual refresh", "limits again from %1",
                 _clock(next / 1000, nowMs / 1000))
}

function footerText(provider, nowMs, refreshedAtMs) {
    if (!provider) return ""
    const hint = refreshHint(provider, nowMs, refreshedAtMs)
    return i18nc("%1 = age such as '5 min ago', %2 = data source", "Updated %1 · %2",
                 ageText(provider.limits_updated_at, nowMs), sourceText(provider.limits_source))
        + (limitsStale(provider, nowMs) ? " · " + i18nc("limit data is outdated", "stale") : "")
        + _pauseText(provider.limits_paused_until, nowMs)
        + (hint ? " · " + hint : "")
}

// After a rate limit (HTTP 429) the collector stops asking until the provider allows it again.
function _pauseText(iso, nowMs) {
    const until = iso ? Date.parse(iso) : NaN
    if (!(until > nowMs)) return ""
    return " · " + i18nc("%1 = clock time; the provider asked to wait before the next request",
                         "paused by the provider until %1", _clock(until / 1000, nowMs / 1000))
}

const ENVELOPE = 1   // version of the collector output this widget understands (collector/limit_rings/widget.py)
const LOG_PATH = "~/.cache/limit-rings/collector.log"
// stop waits for a running pass of the service; only then may the unit files (the collector's guard) go.
const LEGACY_COMMAND = "systemctl --user stop limit-rings.timer limit-rings.service && systemctl --user disable limit-rings.timer && rm ~/.config/systemd/user/limit-rings.timer ~/.config/systemd/user/limit-rings.service"

function shellQuote(s) {
    return "'" + String(s).replace(/'/g, "'\\''") + "'"
}

// The widget package brings its collector; run.py checks the Python version before importing it.
// The executable engine shares one source among all widgets that connect the same command and gives each
// of them the output, so the command carries the applet id: every instance gets only its own pass.
// notify=false: the collector leaves due notices for another instance instead of using them up.
// providers: keys of the shown providers; the collector neither reads nor queries the others.
// notice: {thresholds: [first, second], reset: bool} – when to notify, and whether to tell about resets.
// accountsJson: accountsEnv() of the additional accounts, "" or undefined for none.
// loginProviders: keys of the providers whose login may be used for live limits; undefined: leave it to the collector (all).
function collectorCommand(runPyUrl, instanceId, notify, providers, notice, accountsJson, loginProviders) {
    const s = String(runPyUrl)
    const keys = list => list.filter(k => /^[a-z]+$/.test(k)).join(",")
    const shown = providers ? " LIMIT_RINGS_PROVIDERS=" + keys(providers) : ""
    const settings = notice ? " LIMIT_RINGS_THRESHOLDS=" + notice.thresholds.map(n => Math.round(Number(n))).join(",")
                              + " LIMIT_RINGS_RESET_NOTICE=" + (notice.reset ? "1" : "0") : ""
    const accounts = accountsJson ? " LIMIT_RINGS_ACCOUNTS=" + shellQuote(accountsJson) : ""
    const login = loginProviders ? " LIMIT_RINGS_LOGIN=" + keys(loginProviders) : ""
    return "LIMIT_RINGS_INSTANCE=" + Number(instanceId) + " LIMIT_RINGS_NOTIFY=" + (notify ? "1" : "0") + shown
        + settings + accounts + login + " python3 " + shellQuote(s.startsWith("file://") ? decodeURIComponent(s.slice(7)) : s)
}

// Additional accounts (own CLAUDE_CONFIG_DIR / CODEX_HOME), stored as JSON in the setting extraAccounts
const MAX_ACCOUNTS = 8
const _PROVIDERS = {claude: {name: "Claude", short: "C", dir: "~/.claude-"},
                    codex: {name: "Codex", short: "X", dir: "~/.codex-"}}

function parseAccounts(text) {
    let raw
    try { raw = JSON.parse(text || "[]") } catch (e) { return [] }
    if (!Array.isArray(raw)) return []
    const out = []
    for (let i = 0; i < raw.length && out.length < MAX_ACCOUNTS; i++) {
        const a = raw[i]
        if (!a || typeof a.id !== "string" || !/^[a-z0-9]{1,16}$/.test(a.id) || !_PROVIDERS[a.provider]) continue
        out.push({id: a.id, provider: a.provider, dir: typeof a.dir === "string" ? a.dir : "",
                  name: typeof a.name === "string" ? a.name : "",
                  short: typeof a.short === "string" && a.short ? a.short.slice(0, 2) : _PROVIDERS[a.provider].short,
                  show: a.show !== false})
    }
    return out
}

function serializeAccounts(list) {
    return JSON.stringify(list)
}

function newAccount(provider, list) {
    const taken = list.map(a => a.id)
    let id
    do {
        id = ""
        for (let i = 0; i < 6; i++) id += "abcdefghijklmnopqrstuvwxyz0123456789"[Math.floor(Math.random() * 36)]
    } while (taken.indexOf(id) >= 0)
    const p = _PROVIDERS[provider]
    return {id: id, provider: provider, dir: p.dir, name: p.name + " 2", short: p.short + "2", show: true}
}

// JSON for LIMIT_RINGS_ACCOUNTS: only the shown accounts, "" when there are none
function accountsEnv(list) {
    const shown = list.filter(a => a.show).map(a => ({id: a.id, provider: a.provider, dir: a.dir, name: a.name}))
    return shown.length ? JSON.stringify(shown) : ""
}

function displayEntries(mainEntries, list) {
    const out = mainEntries.slice()
    for (const a of list) {
        if (!a.show) continue
        const provider = _PROVIDERS[a.provider].name
        // same fallback as the collector for an empty name
        const name = String(a.name).trim() || provider + " 2"
        out.push({key: a.id, account: true, provider: a.provider, name: provider + " (" + name + ")",
                  short: a.short, dir: a.dir})
    }
    return out
}

function entryData(stats, entry) {
    if (!stats || !entry) return undefined
    if (!entry.account) return stats.providers ? stats.providers[entry.key] : undefined
    const data = stats.accounts ? stats.accounts[entry.key] : undefined
    // after an edit in the settings the last output may still describe the old directory or provider
    return data && data.provider === entry.provider && data.dir === entry.dir ? data : undefined
}

// One collector pass as the widget sees it: exit code and stdout of run.py.
function readCollectorOutput(exitCode, stdout) {
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

function statusMessage(loadError, stats, nowMs, info) {
    const install = info && info.installCommand ? " " + i18n("Install it with: %1", info.installCommand) : ""
    switch (loadError) {
    case "nopython":
        return i18n("Python 3 not found – Limit Rings needs Python 3.10 or newer.") + install
    case "oldpython":
        return i18n("Python %1 is too old – Limit Rings needs 3.10 or newer.", info ? info.pythonVersion : "") + install
    case "restart":
        return i18n("Limit Rings was updated – restart Plasma or log out and back in to load the new version.")
    case "parse":
        return i18n("The collector output is not readable. Log: %1", LOG_PATH)
    case "failed":
        return i18n("The last collector run failed. Log: %1", LOG_PATH)
    case "nodata":
        return i18n("No data yet – the first collector run is still in progress.")
    case "legacy":
        return i18n("An older Limit Rings installation still collects in the background. Remove it with: %1", LEGACY_COMMAND)
    }
    if (stats && nowMs - Date.parse(stats.generated_at) > STALE_MS)
        return i18n("Data from %1 – the collector has not run since. Log: %2", ageText(stats.generated_at, nowMs), LOG_PATH)
    return ""
}

function _osIds(osRelease) {
    const ids = []
    String(osRelease || "").split("\n").forEach(line => {
        const m = /^(ID|ID_LIKE)=(.*)$/.exec(line.trim())
        if (m) ids.push(...m[2].replace(/^["']|["']$/g, "").split(/\s+/))
    })
    return ids
}

// The command that installs Python 3 on this distribution (from /etc/os-release), or "" if unknown.
function pythonInstallCommand(osRelease) {
    const ids = _osIds(osRelease)
    if (ids.includes("debian") || ids.includes("ubuntu")) return "sudo apt install python3"
    if (ids.includes("arch")) return "sudo pacman -S python"
    if (ids.includes("fedora") || ids.includes("rhel")) return "sudo dnf install python3"
    if (ids.includes("suse") || ids.includes("opensuse")) return "sudo zypper install python3"
    return ""
}

function _version(v) {
    const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(String(v))
    return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null
}

// True only if both are plain X.Y.Z and candidate is higher – anything unexpected means "no update".
function isNewerVersion(candidate, current) {
    const a = _version(candidate)
    const b = _version(current)
    if (!a || !b) return false
    for (let i = 0; i < 3; i++)
        if (a[i] !== b[i]) return a[i] > b[i]
    return false
}

function updateCommand(repoDir) {
    return "cd " + shellQuote(repoDir) + " && git pull && ./install.sh"
}

function _time(d) {
    return (d.getHours() < 10 ? "0" : "") + d.getHours() + ":" + (d.getMinutes() < 10 ? "0" : "") + d.getMinutes()
}

// "Sat 14:00"
function _weekdayClock(epochSec) {
    const d = new Date(epochSec * 1000)
    return _current().locale.standaloneDayName(d.getDay(), _SHORT_FORMAT) + " " + _time(d)
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

// Line below a bar: only what needs attention – a limit that runs out before its reset, or a window that has reset
function barNote(limit, nowSec) {
    if (isReset(limit, nowSec))
        return i18nc("limit window has reset, shown below the bar", "Reset – starts again from 0 %")
    const f = _forecastParts(limit, nowSec)
    return f && f.full ? forecastText(limit, nowSec) : ""
}

// Tooltip of a bar: the forecast and when the window resets
function barTooltip(limit, nowSec) {
    if (isReset(limit, nowSec)) return ""
    const lines = []
    const fc = forecastText(limit, nowSec)
    if (fc) lines.push(fc)
    if (limit.resets_at)
        lines.push(i18nc("%1 = clock time of the reset, with the weekday once it is a day or more away", "Resets at %1",
                         _clock(limit.resets_at, nowSec)))
    return lines.join("\n")
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

// Plan as the providers spell it in their login or usage data → product name (not translated);
// an unknown plan is shown as it comes, so a new one never disappears
const _PLAN_NAMES = {free: "Free", plus: "Plus", pro: "Pro", prolite: "Pro Lite", max: "Max", team: "Team",
                     business: "Business", enterprise: "Enterprise", edu: "Edu"}

function planName(plan) {
    if (!plan) return ""
    return _PLAN_NAMES[String(plan).toLowerCase()] || String(plan)
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

// Claude's extra usage (amounts in currency units) or Codex credits, see "extra" in the collector output
const _CURRENCY_SYMBOLS = {USD: "$", EUR: "€", GBP: "£"}

function _money(amount, currency) {
    return Number(amount).toLocaleCurrencyString(_current().locale, _CURRENCY_SYMBOLS[currency] || currency)
}

function extraName(extra) {
    if (extra && extra.kind === "credits") return i18nc("Codex credit balance", "Credits")
    return i18nc("Claude's paid usage beyond the plan limits", "Extra usage")
}

function extraText(extra) {
    if (!extra || !extra.kind) return ""
    if (extra.kind === "credits") {
        if (extra.unlimited) return i18nc("Codex credit balance", "unlimited")
        return _current().locale.toString(extra.balance, "f", extra.balance % 1 ? 2 : 0)
    }
    if (extra.limit === null || extra.limit === undefined)
        return i18nc("%1 = amount spent; extra usage without a monthly limit", "%1 spent",
                     _money(extra.used, extra.currency))
    return i18nc("%1 = amount spent, %2 = monthly spending limit", "%1 of %2",
                 _money(extra.used, extra.currency), _money(extra.limit, extra.currency))
}

function errorText(errors) {
    if (!errors) return ""
    return errors.map(e => {
        if (e.code === "logs_unreadable")
            return i18np("%1 file unreadable – numbers incomplete", "%1 files unreadable – numbers incomplete", e.count)
        if (e.code === "logs_failed") return i18n("Data could not be processed")
        if (e.code === "limits_unavailable") return i18n("Limits unavailable")
        if (e.code === "account_invalid") return i18n("Account settings are invalid – check the directory")
        return e.code
    }).join("; ")
}

function limitLine(name, limit, nowSec, remaining) {
    const head = name + " · " + limitName(limit) + ": "
    if (isReset(limit, nowSec)) return head + i18nc("limit state", "reset")
    const rest = countdownLong(limit.resets_at, nowSec)
    const fc = forecastShort(limit, nowSec)
    return head + limitPercentText(limit, nowSec, remaining) + (rest ? " · " + i18n("Reset in %1", rest) : "")
        + (fc ? " · " + fc : "")
}

function authHint(auth, entry) {
    if (!auth || auth.status === "ok") return ""
    if (entry && entry.account) {
        const how = entry.provider === "codex" ? i18n("start codex with this CODEX_HOME")
                                               : i18n("start claude with this config directory")
        return auth.status === "expired" ? i18n("Login in %1 expired – %2", entry.dir, how)
                                         : i18n("No login in %1 – %2", entry.dir, how)
    }
    if (auth.status === "expired") return i18n("Login expired – run claude in a terminal")
    return i18n("No login found – run claude in a terminal")
}

// Without login a provider gets its limits only from local copies: say where they come from while there are none
function loginHint(provider, entry) {
    if (!provider || provider.login !== false || (provider.limits && provider.limits.length)) return ""
    const key = entry && entry.account ? entry.provider : (entry ? entry.key : "")
    if (key === "codex")
        return i18n("No limits without login – they come from the session logs once you use codex in a terminal")
    if (entry && entry.account) return i18n("No limits without login for additional accounts")
    return i18n("No limits without login – they come from the status line while claude runs in a terminal")
}

// Changes to the limit structure of the last days ("changes" in the collector output), one line each
function _changeText(change) {
    const at = new Date(change.at)
    const day = at.toLocaleDateString(_current().locale,
                                      i18nc("Qt date format for the daily chart tooltip (day and month)", "MMM d"))
    const name = limitName(change.limit)
    switch (change.kind) {
    case "new":
        return i18nc("limit structure change: %1 limit name, %2 date", "%1: new limit (since %2)", name, day)
    case "back":
        return i18nc("limit structure change: %1 limit name, %2 date", "%1: limit is back (since %2)", name, day)
    case "gone":
        return i18nc("limit structure change: %1 limit name, %2 date", "%1: no longer reported (since %2)", name, day)
    case "length":
        return i18nc("limit structure change: %1 new limit name, %2 previous limit name, %3 date",
                     "Window changed: %1 instead of %2 (since %3)", name,
                     limitName(Object.assign({}, change.limit, {window_minutes: change.previous_minutes})), day)
    case "early_reset":
        return i18nc("limit structure change: %1 limit name, %2 date, %3 clock time", "%1: reset early (%2, %3)",
                     name, day, _time(at))
    }
    return ""
}

function changesText(changes) {
    return (changes || []).map(_changeText).filter(t => t !== "").join("\n")
}

function tooltipText(stats, providers, nowSec, refreshedAtMs, remaining) {
    if (!stats) return i18n("No data")
    const lines = []
    for (let i = 0; i < providers.length; i++) {
        const p = entryData(stats, providers[i])
        if (!p || !p.limits || p.limits.length === 0)
            lines.push(providers[i].name + ": " + i18n("no limit data"))
        else {
            const stale = limitsStale(p, nowSec * 1000) ? " (" + i18nc("limit data is outdated", "stale") + ")" : ""
            for (let j = 0; j < p.limits.length; j++)
                lines.push(limitLine(providers[i].name, p.limits[j], nowSec, remaining) + stale)
        }
        const hint = p ? authHint(p.auth, providers[i]) : ""
        if (hint) lines.push(providers[i].name + ": " + hint)
        const again = refreshHint(p, nowSec * 1000, refreshedAtMs)
        if (again) lines.push(providers[i].name + ": " + again)
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
