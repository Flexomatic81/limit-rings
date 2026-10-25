.pragma library
// Invented numbers for the store and README images; times derive from one fixed "now".
const NOW = Date.parse("2026-10-22T13:20:00+02:00") / 1000
const H = 3600, D = 86400
function iso(sec) { return new Date(sec * 1000).toISOString() }
function tokens(today, week, month) {
    const t = n => ({input: Math.round(n * 0.1), output: Math.round(n * 0.05), cache_read: Math.round(n * 0.8),
                     cache_write: n - Math.round(n * 0.1) - Math.round(n * 0.05) - Math.round(n * 0.8), total: n})
    return {today: t(today), week: t(week), month: t(month)}
}
function daily(heights, scale) {
    return heights.map((h, i) => ({date: new Date((NOW - (heights.length - 1 - i) * D) * 1000).toISOString().slice(0, 10),
                                   total: Math.round(h * scale)}))
}
const SHAPE = [62, 50, 41, 6, 9, 50, 26, 11, 19, 38, 5, 4, 31, 50, 68, 67, 40, 2, 3, 41, 34, 21, 18, 39, 9, 7, 46, 38, 42, 54]
const SHAPE2 = [47, 41, 36, 5, 12, 46, 20, 14, 23, 34, 4, 3, 33, 50, 61, 70, 39, 2, 4, 41, 30, 21, 26, 50, 13, 7, 39, 40, 44, 41]
const SHAPE3 = [60, 50, 54, 9, 20, 48, 27, 22, 33, 57, 12, 11, 45, 57, 70, 72, 50, 8, 10, 60, 40, 31, 28, 64, 18, 14, 50, 54, 60, 52]
function lim(id, pct, resetIn, minutes, extra) {
    return Object.assign({id: id, used_percent: pct, resets_at: Math.round(NOW + resetIn), window_minutes: minutes}, extra || {})
}
function card(o) {
    return {limits: o.limits, limits_source: "oauth", limits_updated_at: iso(NOW - o.age), plan: o.plan,
            limits_next_request_at: null, limits_paused_until: null, extra: o.extra || null,
            tokens: o.tokens, daily: o.daily, weekly: [], monthly: [], errors: [], changes: [], login: true,
            auth: o.auth === undefined ? null : o.auth, breakdown: o.breakdown || null}
}
function breakdown(since, projects, models) {
    const total = projects.reduce((s, p) => s + p[1], 0)
    const list = a => a.map(p => p[0] === null ? {name: null, other: true, total: p[1]} : {name: p[0], total: p[1]})
    return {since: iso(since), basis: "window", total: total, projects: list(projects), models: list(models)}
}
function claude() {
    const weekReset = Date.parse("2026-10-19T05:30:00+02:00") / 1000 + 7 * D
    return card({age: 40, plan: "max", auth: {status: "ok", expires_at: iso(NOW + 5 * H)},
        limits: [lim("five_hour", 64, 1 * H + 50 * 60, 300, {forecast: {status: "full", eta: NOW + 40 * 60}}),
                 lim("seven_day", 41, weekReset - NOW, 10080, {forecast: {status: "enough"}}),
                 lim("seven_day_opus", 27, weekReset - NOW, 10080, {model: "Opus"})],
        extra: {kind: "extra_usage", used: 12.4, limit: 50, percent: 24.8, currency: "USD"},
        tokens: tokens(86.4e6, 412e6, 1.4e9), daily: daily(SHAPE, 86.4e6 / 54),
        breakdown: breakdown(weekReset - 7 * D,
            [["website", 420], ["api-server", 280], ["mobile-app", 150], ["docs", 90], [null, 60]],
            [["Opus 5.5", 640], ["Sonnet 5.5", 330], ["Haiku 4.5", 30]])})
}
function codex() {
    const weekReset = NOW + 5 * D + 2 * H
    return card({age: 55, plan: "plus",
        limits: [lim("primary", 18, 3 * H + 20 * 60, 300), lim("secondary", 33, weekReset - NOW, 10080)],
        extra: {kind: "credits", balance: 120, unlimited: false},
        tokens: tokens(9.4e6, 61e6, 214e6), daily: daily(SHAPE2, 9.4e6 / 41),
        breakdown: breakdown(weekReset - 7 * D,
            [["api-server", 410], ["cli-tool", 260], ["website", 190], ["infra", 90], [null, 50]],
            [["gpt-6-astra", 720], ["gpt-6-mini", 280]])})
}
function work() {
    const weekReset = Date.parse("2026-10-19T05:30:00+02:00") / 1000 + 7 * D
    const c = card({age: 40, plan: "pro", auth: {status: "ok", expires_at: iso(NOW + 5 * H)},
        limits: [lim("five_hour", 23, 1 * H + 50 * 60, 300), lim("seven_day", 58, weekReset - NOW, 10080),
                 lim("seven_day_opus", 12, weekReset - NOW, 10080, {model: "Opus"})],
        tokens: tokens(21e6, 190e6, 702e6), daily: daily(SHAPE3, 21e6 / 52),
        breakdown: breakdown(weekReset - 7 * D, [["backend", 610], ["dashboard", 270], ["infra-tools", 120]],
                             [["Opus 5.5", 580], ["Sonnet 5.5", 420]])})
    return Object.assign(c, {provider: "claude", name: "Work", dir: "~/.claude-work"})
}
function stats(withAccount) {
    const s = {schema: 2, generated_at: iso(NOW - 30), providers: {claude: claude(), codex: codex()}, accounts: {}}
    if (withAccount) s.accounts.w0rk01 = work()
    return s
}
