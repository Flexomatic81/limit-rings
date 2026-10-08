import QtQuick
import QtTest
import "../io.github.flexomatic81.limitrings/contents/code/format.js" as F

TestCase {
    name: "Format"

    function cleanup() { F.init(null) }

    function test_fallback_without_init() {
        compare(F.i18n("Hello %1", "x"), "Hello x")
        compare(F.i18nc("ctx", "Week"), "Week")
        compare(F.i18np("%1 file", "%1 files", 1), "1 file")
        compare(F.i18np("%1 file", "%1 files", 3), "3 files")
    }

    function test_throwing_translator_falls_back() {
        F.init({i18n: () => { throw new Error("context gone") }, i18nc: () => { throw new Error("x") },
                i18np: () => { throw new Error("x") }, locale: Qt.locale("en_US")})
        compare(F.i18n("Hello %1", "x"), "Hello x")
        compare(F.i18np("%1 file", "%1 files", 2), "2 files")
        F.init({i18n: () => undefined, i18nc: () => undefined, i18np: () => undefined})
        compare(F.i18nc("ctx", "Week"), "Week")
    }

    // Panel and desktop instance share format.js: removing the newer one must leave the older one
    // with its translation, not with English.
    function test_remaining_instance_keeps_its_translation() {
        const first = Qt.createQmlObject('import QtQuick; Item { function tr(t) { return "first:" + t } }', this)
        const second = Qt.createQmlObject('import QtQuick; Item { function tr(t) { return "second:" + t } }', this)
        const h1 = F.init({i18n: t => first.tr(t), i18nc: (c, t) => first.tr(t), i18np: (s, p, n) => first.tr(s)})
        const h2 = F.init({i18n: t => second.tr(t), i18nc: (c, t) => second.tr(t), i18np: (s, p, n) => second.tr(s)})
        verify(h1 && h2 && h1 !== h2)
        compare(F.i18n("Week"), "second:Week")
        second.destroy()
        wait(0)
        compare(F.i18n("Week"), "first:Week")
        F.release(h1)
        compare(F.i18n("Week"), "Week")
        first.destroy()
    }

    function test_release_removes_a_live_translator() {
        const h1 = F.init({i18n: t => "one:" + t})
        const h2 = F.init({i18n: t => "two:" + t})
        F.release(h2)
        compare(F.i18n("Week"), "one:Week")
        F.release(h1)
        compare(F.i18n("Week"), "Week")
    }

    // Plasma shares format.js between widget instances: removing the instance whose callbacks were
    // handed over must not blank the texts of the others.
    function test_translator_of_destroyed_object_falls_back() {
        const owner = Qt.createQmlObject(
            'import QtQuick; Item { function tr(t) { return "x" + t } }', this)
        F.init({i18n: t => owner.tr(t), i18nc: (c, t) => owner.tr(t), i18np: (s, p, n) => owner.tr(s)})
        compare(F.i18n("Week"), "xWeek")
        owner.destroy()
        wait(0)
        compare(F.i18n("Week"), "Week")
    }

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
        const t = Date.parse("2026-10-04T13:30:00+02:00")
        const fresh = {generated_at: "2026-10-04T13:29:30+02:00"}
        const old = {generated_at: "2026-10-04T13:00:00+02:00"}
        const info = {pythonVersion: "3.8.10", installCommand: "sudo apt install python3"}
        compare(F.statusMessage("", fresh, t, info), "")
        verify(F.statusMessage("", old, t, info).indexOf("collector.log") >= 0)
        compare(F.statusMessage("nopython", null, t, info),
                "Python 3 not found – Limit Rings needs Python 3.10 or newer. Install it with: sudo apt install python3")
        verify(F.statusMessage("oldpython", null, t, info).indexOf("Python 3.8.10 is too old") === 0)
        compare(F.statusMessage("oldpython", null, t, {pythonVersion: "3.9.2", installCommand: ""}),
                "Python 3.9.2 is too old – Limit Rings needs 3.10 or newer.")
        verify(F.statusMessage("restart", null, t, info).indexOf("restart Plasma") >= 0)
        verify(F.statusMessage("failed", fresh, t, info).indexOf("collector.log") >= 0)
        verify(F.statusMessage("parse", null, t, info).length > 0)
        verify(F.statusMessage("nodata", null, t, info).indexOf("No data yet") === 0)
        verify(F.statusMessage("legacy", fresh, t, info).indexOf("systemctl --user stop limit-rings.timer limit-rings.service && ") >= 0)
    }

    function test_collectorCommand_quotes_the_path() {
        compare(F.collectorCommand("file:///home/a/.local/share/plasma/plasmoids/x/contents/collector/run.py", 7, true),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 python3 '/home/a/.local/share/plasma/plasmoids/x/contents/collector/run.py'")
        compare(F.collectorCommand("file:///home/my%20dir/it's/run.py", 7, false),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=0 python3 '/home/my dir/it'\\''s/run.py'")
    }

    function test_collectorCommand_passes_the_shown_providers() {
        compare(F.collectorCommand("file:///p/run.py", 7, true, ["claude", "codex"]),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 LIMIT_RINGS_PROVIDERS=claude,codex python3 '/p/run.py'")
        compare(F.collectorCommand("file:///p/run.py", 7, true, ["codex"]),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 LIMIT_RINGS_PROVIDERS=codex python3 '/p/run.py'")
        compare(F.collectorCommand("file:///p/run.py", 7, true, []),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 LIMIT_RINGS_PROVIDERS= python3 '/p/run.py'")
    }

    function test_collectorCommand_passes_the_notice_settings() {
        compare(F.collectorCommand("file:///p/run.py", 7, true, ["claude"], {thresholds: [60, 85], reset: true}),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 LIMIT_RINGS_PROVIDERS=claude"
                + " LIMIT_RINGS_THRESHOLDS=60,85 LIMIT_RINGS_RESET_NOTICE=1 python3 '/p/run.py'")
        compare(F.collectorCommand("file:///p/run.py", 7, true, ["claude"], {thresholds: [80, 95], reset: false}),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 LIMIT_RINGS_PROVIDERS=claude"
                + " LIMIT_RINGS_THRESHOLDS=80,95 LIMIT_RINGS_RESET_NOTICE=0 python3 '/p/run.py'")
    }

    // The executable engine shares a source between all widgets that connect the same command and hands
    // every one of them the output – each instance needs its own command, or notifications come twice.
    function test_collectorCommand_differs_per_instance() {
        verify(F.collectorCommand("file:///p/run.py", 7, true) !== F.collectorCommand("file:///p/run.py", 8, true))
    }

    function test_readCollectorOutput() {
        const ok = F.readCollectorOutput(0, '{"envelope": 1, "stats": {"schema": 2}, "notices": [{"summary": "s", "body": "b", "urgent": true}]}')
        compare(ok.error, "")
        compare(ok.stats.schema, 2)
        compare(ok.notices.length, 1)
        compare(F.readCollectorOutput(127, "").error, "nopython")
        const tooOld = F.readCollectorOutput(3, '{"envelope": 1, "error": "python-too-old", "version": "3.8.10"}')
        compare(tooOld.error, "oldpython")
        compare(tooOld.pythonVersion, "3.8.10")
        compare(F.readCollectorOutput(0, '{"envelope": 2, "stats": {"schema": 2}}').error, "restart")
        compare(F.readCollectorOutput(0, '{"envelope": 1, "stats": {"schema": 3}}').error, "restart")
        compare(F.readCollectorOutput(0, "garbage").error, "parse")
        compare(F.readCollectorOutput(2, "").error, "parse")           // e.g. run.py missing after an uninstall
        compare(F.readCollectorOutput(0, '{"envelope": 1, "stats": null, "notices": []}').error, "nodata")
        const legacy = F.readCollectorOutput(0, '{"envelope": 1, "error": "legacy-timer", "stats": {"schema": 2}, "notices": []}')
        compare(legacy.error, "legacy")
        compare(legacy.stats.schema, 2)
        const failed = F.readCollectorOutput(1, '{"envelope": 1, "stats": {"schema": 2}, "notices": []}')
        compare(failed.error, "failed")
        compare(failed.stats.schema, 2)
        compare(F.readCollectorOutput(0, '{"envelope": 1, "stats": null, "notices": [1, {"summary": 2}]}').notices.length, 0)
    }

    function test_pythonInstallCommand() {
        compare(F.pythonInstallCommand('NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\n'), "sudo apt install python3")
        compare(F.pythonInstallCommand('ID=cachyos\nID_LIKE="arch"\n'), "sudo pacman -S python")
        compare(F.pythonInstallCommand('ID=fedora\n'), "sudo dnf install python3")
        compare(F.pythonInstallCommand('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n'), "sudo zypper install python3")
        compare(F.pythonInstallCommand('ID=gentoo\n'), "")
        compare(F.pythonInstallCommand(""), "")
        compare(F.pythonInstallCommand(undefined), "")
    }

    function test_isNewerVersion() {
        verify(F.isNewerVersion("0.3.0", "0.2.0"))
        verify(F.isNewerVersion("0.10.0", "0.9.0"))
        verify(F.isNewerVersion("1.0.0", "0.99.99"))
        verify(!F.isNewerVersion("0.2.0", "0.2.0"))
        verify(!F.isNewerVersion("0.1.9", "0.2.0"))
        for (const bad of ["v0.3.0", "0.3", "0.4.0-rc1", "latest", "", null, undefined])
            verify(!F.isNewerVersion(bad, "0.2.0"), String(bad))
        verify(!F.isNewerVersion("0.3.0", ""))
    }

    function test_updateCommand() {
        compare(F.updateCommand("/home/a/limit rings"), "cd '/home/a/limit rings' && git pull && ./install.sh")
    }

    function test_tooltip() {
        const now = 0
        const stats = {providers: {
            claude: {limits: [{window_minutes: 300, used_percent: 42, resets_at: 2 * 3600 + 13 * 60},
                              {window_minutes: 10080, used_percent: 18, resets_at: null}]},
            codex: {limits: []}}}
        const providers = [{key: "claude", name: "Claude"}, {key: "codex", name: "Codex"}]
        compare(F.tooltipText(stats, providers, now),
                "Claude · 5 h: 42 % · Reset in 2 h 13 min\nClaude · Week: 18 %\nCodex: no limit data")
        compare(F.limitLine("Codex", {window_minutes: 10080, used_percent: 8, resets_at: -1}, now),
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
        const stats = {providers: {claude: {limits: [{window_minutes: 10080, used_percent: 18, resets_at: null}],
                                            auth: {status: "expired", expires_at: null}}}}
        compare(F.tooltipText(stats, [{key: "claude", name: "Claude"}], 0),
                "Claude · Week: 18 %\nClaude: Login expired – run claude in a terminal")
        const empty = {providers: {claude: {limits: [], auth: {status: "missing", expires_at: null}}}}
        compare(F.tooltipText(empty, [{key: "claude", name: "Claude"}], 0),
                "Claude: no limit data\nClaude: No login found – run claude in a terminal")
    }

    function test_forecastText() {
        const now = 1000
        const base = {window_minutes: 300, used_percent: 40, resets_at: now + 4 * 3600}
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
        const l = {window_minutes: 300, used_percent: 40, resets_at: 4 * 3600,
                   forecast: {status: "full", eta: 80 * 60}}
        compare(F.limitLine("Claude", l, now), "Claude · 5 h: 40 % · Reset in 4 h 0 min · full in ~1 h 20 min")
        l.forecast = {status: "enough"}
        compare(F.limitLine("Claude", l, now), "Claude · 5 h: 40 % · Reset in 4 h 0 min · lasts until reset")
    }

    function test_forecastText_far_away_shows_weekday() {
        const now = Date.parse("2026-10-01T08:00:00Z") / 1000   // eta: Saturday 12:00 UTC
        const week = {window_minutes: 10080, used_percent: 40, resets_at: now + 6 * 86400,
                      forecast: {status: "full", eta: now + 2 * 86400 + 4 * 3600}}
        const text = F.forecastText(week, now)
        verify(text.indexOf("Full in ~2 d 4 h at current pace (") === 0, text)
        verify(/\(Sat \d\d:\d\d\)$/.test(text), text)
        compare(F.forecastShort(week, now), "full in ~2 d 4 h")
    }

    function test_limitsStale() {
        const t = Date.parse("2026-10-04T18:00:00+02:00")
        const prov = (iso, limits) => ({limits_updated_at: iso, limits: limits, limits_source: "session_log"})
        const one = [{window_minutes: 10080, used_percent: 8, resets_at: null}]
        verify(!F.limitsStale(prov("2026-10-04T12:00:00+02:00", one), t))          // exactly 6 h
        verify(F.limitsStale(prov("2026-10-04T11:59:59+02:00", one), t))           // just over
        verify(!F.limitsStale(prov("2026-09-29T21:30:00+02:00", []), t))           // no limits
        verify(!F.limitsStale(prov(null, one), t))
        verify(!F.limitsStale(undefined, t))
    }

    function test_footerText() {
        const t = Date.parse("2026-10-04T18:00:00+02:00")
        const lim = [{window_minutes: 10080, used_percent: 8, resets_at: null}]
        compare(F.footerText({limits_updated_at: "2026-10-04T17:59:30+02:00", limits_source: "oauth", limits: lim}, t),
                "Updated 30 s ago · OAuth")
        compare(F.footerText({limits_updated_at: "2026-09-30T18:00:00+02:00", limits_source: "session_log", limits: lim}, t),
                "Updated 4 d ago · Session log · stale")
        compare(F.footerText(undefined, t), "")
    }

    function test_extra_usage_and_credits() {
        const limited = {kind: "extra_usage", used: 12.34, limit: 50, percent: 24.68, currency: "USD"}
        compare(F.extraName(limited), "Extra usage")
        compare(F.extraText(limited), "$12.34 of $50.00")
        compare(F.extraText({kind: "extra_usage", used: 2.5, limit: null, percent: null, currency: "USD"}),
                "$2.50 spent")
        compare(F.extraText({kind: "extra_usage", used: 1, limit: 10, percent: 10, currency: "EUR"}), "€1.00 of €10.00")
        compare(F.extraText({kind: "extra_usage", used: 1, limit: null, percent: null, currency: "CHF"}), "CHF1.00 spent")
        const credits = {kind: "credits", balance: 120, unlimited: false}
        compare(F.extraName(credits), "Credits")
        compare(F.extraText(credits), "120")
        compare(F.extraText({kind: "credits", balance: 12.5, unlimited: false}), "12.50")
        compare(F.extraText({kind: "credits", balance: 0, unlimited: true}), "unlimited")
        compare(F.extraText(null), "")
        compare(F.extraText({}), "")
    }

    function test_refreshHint_after_a_manual_refresh() {
        const t = Date.parse("2026-10-04T18:00:00+02:00")
        const next = new Date(t + 4 * 60000)
        const clock = (next.getHours() < 10 ? "0" : "") + next.getHours() + ":"
            + (next.getMinutes() < 10 ? "0" : "") + next.getMinutes()
        const p = {limits_updated_at: "2026-10-04T17:59:00+02:00", limits_source: "oauth", limits: [],
                   limits_next_request_at: next.toISOString()}
        compare(F.refreshHint(p, t, t - 5000), "limits again from " + clock)
        compare(F.refreshHint(p, t, t - 61000), "")                    // refreshed too long ago
        compare(F.refreshHint(p, t, 0), "")                            // never refreshed by hand
        compare(F.refreshHint(Object.assign({}, p, {limits_next_request_at: "2026-10-04T17:59:00+02:00"}), t, t), "")
        compare(F.refreshHint(Object.assign({}, p, {limits_next_request_at: null}), t, t), "")
        compare(F.footerText(p, t, t - 5000), "Updated 1 min ago · OAuth · limits again from " + clock)
        const stats = {providers: {claude: Object.assign({}, p, {limits: [{window_minutes: 300, used_percent: 5,
                                                                           resets_at: null}]})}}
        compare(F.tooltipText(stats, [{key: "claude", name: "Claude"}], t / 1000, t - 5000),
                "Claude · 5 h: 5 %\nClaude: limits again from " + clock)
    }

    function test_footerText_names_a_running_pause() {
        const t = Date.parse("2026-10-04T18:00:00+02:00")
        const until = new Date(t + 30 * 60000)
        const clock = (until.getHours() < 10 ? "0" : "") + until.getHours() + ":"
            + (until.getMinutes() < 10 ? "0" : "") + until.getMinutes()
        const p = {limits_updated_at: "2026-10-04T17:55:00+02:00", limits_source: "oauth", limits: [],
                   limits_paused_until: until.toISOString()}
        compare(F.footerText(p, t), "Updated 5 min ago · OAuth · paused by the provider until " + clock)
        // pause over or not set: no hint
        compare(F.footerText(Object.assign({}, p, {limits_paused_until: "2026-10-04T17:59:00+02:00"}), t),
                "Updated 5 min ago · OAuth")
        compare(F.footerText(Object.assign({}, p, {limits_paused_until: null}), t), "Updated 5 min ago · OAuth")
    }

    function test_tooltip_marks_stale_limits() {
        const nowSec = Date.parse("2026-10-04T18:00:00+02:00") / 1000
        const stats = {providers: {codex: {limits_updated_at: "2026-09-30T18:00:00+02:00",
                                           limits: [{window_minutes: 10080, used_percent: 8, resets_at: null}]}}}
        compare(F.tooltipText(stats, [{key: "codex", name: "Codex"}], nowSec), "Codex · Week: 8 % (stale)")
    }

    function test_breakdownTitle() {
        // 12:00 UTC: a Tuesday in every common timezone
        const title = F.breakdownTitle({basis: "window", since: "2026-09-29T12:00:00Z"})
        verify(/^Since weekly reset \(Tue \d\d:\d\d\)$/.test(title), title)
        compare(F.breakdownTitle({basis: "7d", since: "2026-09-27T12:00:00+02:00"}), "Last 7 days")
        compare(F.breakdownTitle(null), "")
    }

    function test_breakdownRows_and_percent() {
        const rows = F.breakdownRows([{name: "website", total: 880}, {name: null, other: true, total: 4}, {name: "x", total: 116}], 1000)
        compare(rows.length, 3)
        compare(rows[0].name, "website")
        compare(rows[0].pct, 88)
        compare(F.percentText(rows[0].pct), "88 %")
        compare(F.percentText(rows[1].pct), "<1 %")
        compare(F.percentText(0), "0 %")
        compare(F.breakdownRows([{name: "a", total: 5}], 0)[0].pct, 0)
        compare(F.breakdownRows(undefined, 10).length, 0)
        compare(F.breakdownTooltip(rows[0]), "880 tokens")
        compare(rows[1].name, "Other")
        verify(rows[1].other)
        verify(!rows[0].other)
    }

    function test_ringValues() {
        const now = 1000
        const five = (pct, reset) => ({used_percent: pct, resets_at: reset === undefined ? null : reset,
                                       window_minutes: 300})
        const week = (pct, model) => ({used_percent: pct, resets_at: null, window_minutes: 10080, model: model})
        compare(F.ringValues([five(8), week(36), week(9, "Fable")], now), {outer: 36, inner: 8})
        compare(F.ringValues([week(7)], now), {outer: 7, inner: null})          // Codex: week only
        compare(F.ringValues([five(40)], now), {outer: null, inner: 40})
        compare(F.ringValues([five(90, 999), week(20), week(60, "Fable")], now), {outer: 60, inner: 0})  // reset has passed
        compare(F.ringValues([week(12, "Fable")], now), {outer: 12, inner: null})  // only a model's weekly limit
        compare(F.ringValues([week(7), five(40)], now), {outer: 7, inner: 40})     // Codex: week moved to "primary"
        compare(F.ringValues([], now), {outer: null, inner: null})
        compare(F.ringValues(null, now), {outer: null, inner: null})
        // only a window of another length: highest value on the outer ring, as before
        compare(F.ringValues([{used_percent: 15, resets_at: null, window_minutes: 2880}], now),
                {outer: 15, inner: null})
    }

    function test_elapsedShare() {
        const now = 100000
        const five = (resetsIn, minutes) => ({used_percent: 10, resets_at: resetsIn === null ? null : now + resetsIn,
                                              window_minutes: minutes === undefined ? 300 : minutes})
        compare(F.elapsedShare(five(3600), now), 0.8)          // 4 of 5 hours gone
        compare(F.elapsedShare(five(5 * 3600), now), 0)        // window just started
        compare(F.elapsedShare(five(6 * 3600), now), 0)        // reset further away than the window: clamp
        compare(F.elapsedShare(five(-10), now), null)          // reset has passed
        compare(F.elapsedShare(five(null), now), null)
        compare(F.elapsedShare(five(3600, null), now), null)
        compare(F.elapsedShare(null, now), null)
    }

    function test_limitSeverity_adds_the_pace_to_the_thresholds() {
        const now = 100000
        const lim = (pct, status) => ({used_percent: pct, resets_at: now + 3600, window_minutes: 300,
                                       forecast: status ? {status: status, eta: now + 600} : undefined})
        compare(F.limitSeverity(lim(45), now, 70, 90), "normal")
        compare(F.limitSeverity(lim(45, "full"), now, 70, 90), "warning")     // full before the reset
        compare(F.limitSeverity(lim(45, "enough"), now, 70, 90), "normal")
        compare(F.limitSeverity(lim(75, "enough"), now, 70, 90), "warning")
        compare(F.limitSeverity(lim(95, "full"), now, 70, 90), "critical")
        const reset = {used_percent: 99, resets_at: now - 1, window_minutes: 300, forecast: {status: "full", eta: now}}
        compare(F.limitSeverity(reset, now, 70, 90), "normal")
        compare(F.limitSeverity(null, now, 70, 90), "normal")
    }

    function test_worstSeverity_for_the_number_style() {
        const now = 100000
        const lim = (pct, status) => ({used_percent: pct, resets_at: now + 3600, window_minutes: 300,
                                       forecast: status ? {status: status, eta: now + 600} : undefined})
        compare(F.worstSeverity([lim(20), lim(40, "full")], now, 70, 90), "warning")
        compare(F.worstSeverity([lim(95), lim(40, "full")], now, 70, 90), "critical")
        compare(F.worstSeverity([lim(20)], now, 70, 90), "normal")
        compare(F.worstSeverity(null, now, 70, 90), "normal")
    }

    function test_ringLimits_picks_the_limits_behind_the_rings() {
        const now = 1000
        const five = {id: "five_hour", used_percent: 8, resets_at: null, window_minutes: 300}
        const week = {id: "seven_day", used_percent: 36, resets_at: null, window_minutes: 10080}
        const fable = {id: "weekly_scoped:fable", used_percent: 50, resets_at: null, window_minutes: 10080, model: "Fable"}
        let r = F.ringLimits([five, week, fable], now)
        compare(r.outer.id, "weekly_scoped:fable")
        compare(r.inner.id, "five_hour")
        r = F.ringLimits([week], now)
        compare(r.outer.id, "seven_day")
        compare(r.inner, null)
        const twoDays = {id: "x", used_percent: 15, resets_at: null, window_minutes: 2880}
        compare(F.ringLimits([twoDays], now).outer.id, "x")
        compare(F.ringLimits([], now), {outer: null, inner: null})
    }

    function test_normalColor_avoids_the_warning_and_critical_colours() {
        const rgb = (r, g, b) => Qt.rgba(r / 255, g / 255, b / 255, 1)
        const theme = (accent, positive, neutral) => ({
            highlightColor: accent, positiveTextColor: positive || rgb(39, 174, 96),
            neutralTextColor: neutral || rgb(246, 116, 0), negativeTextColor: rgb(218, 68, 83),
            textColor: rgb(252, 252, 252)})
        const blue = rgb(61, 174, 233), orange = rgb(254, 128, 25), green = rgb(104, 157, 106)
        compare(F.normalColor(theme(blue)), blue)                          // Breeze: unchanged
        compare(F.normalColor(theme(orange, green)), green)                // Gruvbox: accent too close to warning
        compare(F.normalColor(theme(rgb(230, 70, 80))), rgb(39, 174, 96))  // accent close to critical
        const grey = F.normalColor(theme(orange, rgb(240, 110, 10)))       // positive too close as well
        compare(Qt.rgba(grey.r, grey.g, grey.b, 1), rgb(252, 252, 252))
        verify(grey.a < 1)
        compare(F.normalColor(theme(rgb(128, 128, 128))), rgb(128, 128, 128))  // grey accent stays
    }

    function test_toneFor_by_severity() {
        const rgb = (r, g, b) => Qt.rgba(r / 255, g / 255, b / 255, 1)
        const theme = {highlightColor: rgb(61, 174, 233), positiveTextColor: rgb(39, 174, 96),
                       neutralTextColor: rgb(246, 116, 0), negativeTextColor: rgb(218, 68, 83),
                       textColor: rgb(252, 252, 252)}
        compare(F.toneFor("critical", theme), theme.negativeTextColor)
        compare(F.toneFor("warning", theme), theme.neutralTextColor)
        compare(F.toneFor("normal", theme), theme.highlightColor)
    }

    function test_accounts_round_trip_and_sanitising() {
        const list = [{id: "k7f3a2", provider: "claude", dir: "~/.claude-a", name: "Work", short: "A", show: true},
                      {id: "c0d3x1", provider: "codex", dir: "/srv/x", name: "Team", short: "T", show: false}]
        compare(F.parseAccounts(F.serializeAccounts(list)), list)
        compare(F.parseAccounts(""), [])
        compare(F.parseAccounts("not json"), [])
        compare(F.parseAccounts('{"id": 1}'), [])
        compare(F.parseAccounts('[{"id": "BAD!", "provider": "claude"}, {"id": "ok1", "provider": "gemini"}]'), [])
        const many = []
        for (let i = 0; i < 12; i++) many.push({id: "a" + i, provider: "claude", dir: "~/.c" + i, name: "N", short: "N"})
        compare(F.parseAccounts(JSON.stringify(many)).length, F.MAX_ACCOUNTS)
        // missing optional fields get defaults
        compare(F.parseAccounts('[{"id": "a1", "provider": "codex"}]'),
                [{id: "a1", provider: "codex", dir: "", name: "", short: "X", show: true}])
    }

    function test_newAccount_gets_a_free_id_and_defaults() {
        const a = F.newAccount("claude", [])
        verify(/^[a-z0-9]{6}$/.test(a.id))
        compare([a.provider, a.dir, a.name, a.short, a.show], ["claude", "~/.claude-", "Claude 2", "C2", true])
        const b = F.newAccount("codex", [a])
        verify(b.id !== a.id)
        compare([b.dir, b.name, b.short], ["~/.codex-", "Codex 2", "X2"])
    }

    function test_accountsEnv_and_command_quote_safely() {
        const list = [{id: "k7f3a2", provider: "claude", dir: "/home/a b/.claude-x", name: "Bü'ro \"2\"", short: "B", show: true},
                      {id: "hid123", provider: "codex", dir: "/x", name: "H", short: "H", show: false}]
        const env = F.accountsEnv(list)
        compare(JSON.parse(env), [{id: "k7f3a2", provider: "claude", dir: "/home/a b/.claude-x", name: "Bü'ro \"2\""}])
        compare(F.accountsEnv([list[1]]), "")
        compare(F.collectorCommand("file:///p/run.py", 7, true, ["claude"], null, env),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 LIMIT_RINGS_PROVIDERS=claude LIMIT_RINGS_ACCOUNTS="
                + F.shellQuote(env) + " python3 '/p/run.py'")
        compare(F.collectorCommand("file:///p/run.py", 7, true, ["claude"], null, ""),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 LIMIT_RINGS_PROVIDERS=claude python3 '/p/run.py'")
    }

    function test_displayEntries_and_entryData() {
        const main = [{key: "claude", name: "Claude", short: "C"}]
        const list = [{id: "k7f3a2", provider: "claude", dir: "~/.c", name: "Work", short: "A", show: true},
                      {id: "hid123", provider: "codex", dir: "/x", name: "H", short: "H", show: false}]
        const entries = F.displayEntries(main, list)
        compare(entries, [{key: "claude", name: "Claude", short: "C"},
                          {key: "k7f3a2", account: true, provider: "claude", name: "Claude (Work)", short: "A",
                           dir: "~/.c"}])
        const stats = {providers: {claude: {limits: [1]}},
                       accounts: {k7f3a2: {provider: "claude", dir: "~/.c", limits: [2]}}}
        compare(F.entryData(stats, entries[0]).limits, [1])
        compare(F.entryData(stats, entries[1]).limits, [2])
        // settings changed, the output still describes the old directory or provider: no data yet
        compare(F.entryData(stats, Object.assign({}, entries[1], {dir: "~/.other"})), undefined)
        compare(F.entryData(stats, Object.assign({}, entries[1], {provider: "codex"})), undefined)
        compare(F.entryData({providers: {}}, entries[1]), undefined)   // older stats.json without accounts
        compare(F.entryData(null, entries[0]), undefined)
    }

    function test_displayEntries_falls_back_for_an_empty_name() {
        const list = [{id: "a1", provider: "claude", dir: "~/.c", name: "", short: "A", show: true},
                      {id: "a2", provider: "codex", dir: "~/.x", name: "  ", short: "B", show: true}]
        const names = F.displayEntries([], list).map(e => e.name)
        compare(names, ["Claude (Claude 2)", "Codex (Codex 2)"])
    }

    function test_authHint_for_accounts_names_the_directory() {
        compare(F.authHint({status: "missing"}, {account: true, provider: "claude", dir: "~/.claude-a"}),
                "No login in ~/.claude-a – start claude with this config directory")
        compare(F.authHint({status: "expired"}, {account: true, provider: "claude", dir: "~/.claude-a"}),
                "Login in ~/.claude-a expired – start claude with this config directory")
        compare(F.authHint({status: "missing"}, {account: true, provider: "codex", dir: "~/.codex-b"}),
                "No login in ~/.codex-b – start codex with this CODEX_HOME")
        compare(F.authHint({status: "ok"}, {account: true, provider: "codex", dir: "~/.codex-b"}), "")
        compare(F.authHint({status: "missing"}), "No login found – run claude in a terminal")   // main account
        compare(F.errorText([{code: "account_invalid"}]), "Account settings are invalid – check the directory")
    }

    function test_tooltip_names_additional_accounts() {
        const stats = {providers: {}, accounts: {k7f3a2: {provider: "claude", dir: "~/.c",
                                                          limits: [{window_minutes: 300, used_percent: 42, resets_at: null}],
                                                          limits_updated_at: new Date().toISOString()}}}
        compare(F.tooltipText(stats, [{key: "k7f3a2", account: true, provider: "claude", dir: "~/.c",
                                       name: "Claude (Work)"}], Date.now() / 1000),
                "Claude (Work) · 5 h: 42 %")
    }

    function test_limitName() {
        compare(F.limitName({id: "five_hour", window_minutes: 300}), "5 h")
        compare(F.limitName({id: "seven_day", window_minutes: 10080}), "Week")
        compare(F.limitName({id: "weekly_scoped:fable", window_minutes: 10080, model: "Fable"}), "Week Fable")
        compare(F.limitName({id: "x", window_minutes: 2880}), "2 d")
        compare(F.limitName({id: "x", window_minutes: 90}), "90 min")
        compare(F.limitName({id: "primary", window_minutes: null}), "primary")
    }

    function test_errorText() {
        compare(F.errorText([]), "")
        compare(F.errorText(undefined), "")
        compare(F.errorText([{code: "logs_unreadable", count: 1}]), "1 file unreadable – numbers incomplete")
        compare(F.errorText([{code: "logs_unreadable", count: 3}, {code: "limits_unavailable"}]),
                "3 files unreadable – numbers incomplete; Limits unavailable")
        compare(F.errorText([{code: "logs_failed"}, {code: "something_new"}]),
                "Data could not be processed; something_new")
    }

    function test_changesText_names_each_change() {
        const at = "2026-10-02T14:30:00+02:00"
        const local = new Date(at)
        const day = local.toLocaleDateString(Qt.locale("en_US"), "MMM d")
        const clock = (local.getHours() < 10 ? "0" : "") + local.getHours() + ":" +
                      (local.getMinutes() < 10 ? "0" : "") + local.getMinutes()
        compare(F.changesText(undefined), "")
        compare(F.changesText([]), "")
        compare(F.changesText([
            {kind: "new", limit: {id: "seven_day_opus", window_minutes: 10080, model: "Opus"}, at: at},
            {kind: "back", limit: {id: "five_hour", window_minutes: 300}, at: at},
            {kind: "gone", limit: {id: "seven_day_sonnet", window_minutes: 10080, model: "Sonnet"}, at: at},
            {kind: "length", limit: {id: "primary", window_minutes: 10080}, previous_minutes: 300, at: at},
            {kind: "early_reset", limit: {id: "seven_day", window_minutes: 10080}, at: at},
            {kind: "unknown", limit: {id: "x", window_minutes: 60}, at: at}
        ]), ["Week Opus: new limit (since " + day + ")",
             "5 h: limit is back (since " + day + ")",
             "Week Sonnet: no longer reported (since " + day + ")",
             "Window changed: Week instead of 5 h (since " + day + ")",
             "Week: reset early (" + day + ", " + clock + ")"].join("\n"))
    }

    function test_collectorCommand_passes_the_login_providers() {
        compare(F.collectorCommand("file:///p/run.py", 7, true, ["claude", "codex"], null, "", ["codex"]),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 LIMIT_RINGS_PROVIDERS=claude,codex"
                + " LIMIT_RINGS_LOGIN=codex python3 '/p/run.py'")
        compare(F.collectorCommand("file:///p/run.py", 7, true, ["claude"], null, "", []),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 LIMIT_RINGS_PROVIDERS=claude LIMIT_RINGS_LOGIN= python3 '/p/run.py'")
        compare(F.collectorCommand("file:///p/run.py", 7, true, ["claude"], null, "", ["claude; rm -rf ~"]),
                "LIMIT_RINGS_INSTANCE=7 LIMIT_RINGS_NOTIFY=1 LIMIT_RINGS_PROVIDERS=claude LIMIT_RINGS_LOGIN= python3 '/p/run.py'")
    }

    function test_loginHint_only_without_login_and_limits() {
        const claude = {key: "claude", name: "Claude", short: "C"}
        const codex = {key: "codex", name: "Codex", short: "X"}
        const work = {key: "k7f3a2", account: true, provider: "claude", name: "Claude (Work)", dir: "~/.claude-w"}
        const team = {key: "c0d3x1", account: true, provider: "codex", name: "Codex (Team)", dir: "~/.codex-t"}
        compare(F.loginHint(null, claude), "")
        compare(F.loginHint({login: true, limits: []}, claude), "")
        compare(F.loginHint({limits: []}, claude), "")   // older collector without the field
        compare(F.loginHint({login: false, limits: [{window_minutes: 300, used_percent: 5}]}, claude), "")
        compare(F.loginHint({login: false, limits: []}, claude),
                "No limits without login – they come from the status line while claude runs in a terminal")
        compare(F.loginHint({login: false, limits: []}, work), "No limits without login for additional accounts")
        compare(F.loginHint({login: false, limits: []}, codex),
                "No limits without login – they come from the session logs once you use codex in a terminal")
        compare(F.loginHint({login: false, limits: []}, team),
                "No limits without login – they come from the session logs once you use codex in a terminal")
    }

    // Below the bar only what needs attention; the rest is in the bar's tooltip
    function test_barNote_shows_only_warnings_and_resets() {
        const now = 1000
        const base = {window_minutes: 300, used_percent: 40, resets_at: now + 4 * 3600}
        compare(F.barNote(base, now), "")
        compare(F.barNote(Object.assign({}, base, {forecast: {status: "enough"}}), now), "")
        const note = F.barNote(Object.assign({}, base, {forecast: {status: "full", eta: now + 80 * 60}}), now)
        verify(note.indexOf("Full in ~1 h 20 min at current pace (") === 0, note)
        compare(F.barNote(Object.assign({}, base, {resets_at: now - 1}), now), "Reset – starts again from 0 %")
    }

    function test_barTooltip_names_forecast_and_reset_time() {
        const now = Date.parse("2026-10-01T08:00:00Z") / 1000
        const enough = {window_minutes: 300, used_percent: 40, resets_at: now + 4 * 3600, forecast: {status: "enough"}}
        const tip = F.barTooltip(enough, now)
        verify(/^Lasts until reset at current pace\nResets at \d\d:\d\d$/.test(tip), tip)
        const week = {window_minutes: 10080, used_percent: 9, resets_at: now + 3 * 86400}
        verify(/^Resets at Sun \d\d:\d\d$/.test(F.barTooltip(week, now)), F.barTooltip(week, now))
        compare(F.barTooltip(Object.assign({}, enough, {resets_at: now - 1}), now), "")
        compare(F.barTooltip({window_minutes: 300, used_percent: 1, resets_at: null}, now), "")
    }
}
