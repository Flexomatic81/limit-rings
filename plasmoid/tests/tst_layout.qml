import QtQuick
import QtQuick.Layouts
import QtTest
import "../io.github.flexomatic81.limitrings/contents/ui" as UI

TestCase {
    name: "Layout"
    when: windowShown
    visible: true   // TestCase defaults to invisible, which would hide every child item
    width: 700
    height: 200

    UI.FullRepresentation {
        id: full
        width: 684
        height: 180   // like the saved popup size that used to cut off the content
        providers: [{key: "claude", name: "Claude", short: "C"}]
        nowMs: Date.parse("2026-10-04T13:30:00+02:00")
        warn: 70
        crit: 90
        installSource: "git"
        updateCommand: "cd '/x' && git pull && ./install.sh"
        stats: ({schema: 2, generated_at: "2026-10-04T13:29:30+02:00", providers: {claude: {
            limits: [{id: "five_hour", used_percent: 6, resets_at: null, window_minutes: 300}],
            limits_source: "oauth", limits_updated_at: "2026-10-04T13:29:00+02:00", plan: "pro",
            tokens: {today: {input: 1, output: 1, cache_read: 1, cache_write: 1, total: 4},
                     week: {input: 1, output: 1, cache_read: 1, cache_write: 1, total: 4},
                     month: {input: 1, output: 1, cache_read: 1, cache_write: 1, total: 4}},
            daily: [{date: "2026-10-04", total: 4}], errors: [],
            breakdown: {since: "2026-09-29T06:00:00+02:00", basis: "window", total: 110,
                        projects: [{name: "website", total: 67}, {name: "limit-rings", total: 33},
                                   {name: null, other: true, total: 10}],
                        models: [{name: "Opus 5.5", total: 100}]}}}})
    }

    function test_update_message_appears_only_with_a_version() {
        const msg = findChild(full, "updateMessage")
        verify(msg !== null)
        verify(!msg.visible)
        full.updateVersion = "0.4.0"
        verify(msg.visible)
        verify(msg.text.indexOf("0.4.0") >= 0 && msg.text.indexOf("git pull") >= 0)
        full.updateVersion = ""
    }

    function test_minimum_height_covers_content() {
        waitForRendering(full)
        verify(full.Layout.preferredHeight > 200, "content should be taller than the old popup")
        verify(full.Layout.minimumHeight >= full.Layout.preferredHeight,
               "minimumHeight " + full.Layout.minimumHeight + " < content " + full.Layout.preferredHeight)
    }

    function test_extra_usage_line_appears_and_takes_space() {
        waitForRendering(full)
        const row = findChild(full, "extraUsage")
        verify(row !== null)
        verify(!row.visible)
        const before = full.Layout.preferredHeight
        const stats = JSON.parse(JSON.stringify(full.stats))
        stats.providers.claude.extra = {kind: "extra_usage", used: 12.34, limit: 50, percent: 24.68, currency: "USD"}
        full.stats = stats
        waitForRendering(full)
        verify(row.visible)
        verify(full.Layout.preferredHeight > before, full.Layout.preferredHeight + " <= " + before)
        verify(full.Layout.minimumHeight >= full.Layout.preferredHeight)
        stats.providers.claude.extra = null
        full.stats = stats
    }

    function test_limit_changes_appear_and_take_space() {
        waitForRendering(full)
        const line = findChild(full, "limitChanges")
        verify(line !== null)
        verify(!line.visible)
        full.stats = JSON.parse(JSON.stringify(full.stats))   // settle the layout left by earlier tests
        waitForRendering(full)
        const before = full.Layout.preferredHeight
        const stats = JSON.parse(JSON.stringify(full.stats))
        stats.providers.claude.changes = [{kind: "new", at: "2026-10-04T12:00:00+02:00",
                                           limit: {id: "seven_day_opus", window_minutes: 10080, model: "Opus"}}]
        full.stats = stats
        waitForRendering(full)
        verify(line.visible)
        verify(line.text.indexOf("Week Opus: new limit") === 0, line.text)
        verify(full.Layout.preferredHeight > before, full.Layout.preferredHeight + " <= " + before)
        stats.providers.claude.changes = []
        full.stats = JSON.parse(JSON.stringify(stats))
    }

    function test_bars_mark_the_elapsed_time() {
        const original = full.stats
        const stats = JSON.parse(JSON.stringify(original))
        const nowSec = full.nowMs / 1000
        stats.providers.claude.limits = [{id: "five_hour", used_percent: 6, resets_at: nowSec + 3600, window_minutes: 300}]
        full.stats = stats
        waitForRendering(full)
        const mark = findChild(full, "elapsedMark")
        verify(mark !== null && mark.visible)
        fuzzyCompare(mark.x + mark.width / 2, mark.parent.width * 0.8, 1.5)
        stats.providers.claude.limits[0].resets_at = null
        full.stats = JSON.parse(JSON.stringify(stats))
        tryVerify(() => !findChild(full, "elapsedMark").visible)
        full.stats = original
    }

    function test_percentage_is_bold_while_not_normal() {
        const original = full.stats
        const stats = JSON.parse(JSON.stringify(original))
        stats.providers.claude.limits = [{id: "five_hour", used_percent: 75, resets_at: null, window_minutes: 300}]
        full.stats = stats
        tryVerify(() => { const l = findChild(full, "percentLabel"); return l && l.text === "75 %" })
        verify(findChild(full, "percentLabel").font.bold)
        stats.providers.claude.limits[0].used_percent = 20
        full.stats = JSON.parse(JSON.stringify(stats))
        tryVerify(() => findChild(full, "percentLabel").text === "20 %")
        verify(!findChild(full, "percentLabel").font.bold)
        full.stats = original
    }

    function test_additional_accounts_get_their_own_cards() {
        const comp = Qt.createComponent("../io.github.flexomatic81.limitrings/contents/ui/FullRepresentation.qml")
        const stats = JSON.parse(JSON.stringify(full.stats))
        stats.accounts = {k7f3a2: JSON.parse(JSON.stringify(stats.providers.claude))}
        stats.accounts.k7f3a2.limits[0].used_percent = 77
        stats.accounts.k7f3a2.provider = "claude"
        stats.accounts.k7f3a2.dir = "~/.c"
        const entries = [{key: "claude", name: "Claude", short: "C"},
                         {key: "k7f3a2", account: true, provider: "claude", name: "Claude (Work)", short: "A", dir: "~/.c"},
                         {key: "gone12", account: true, provider: "codex", name: "Codex (Old)", short: "X", dir: "~/.x"}]
        const obj = comp.createObject(this, {providers: entries, nowMs: full.nowMs, warn: 70, crit: 90, stats: stats,
                                             width: 684, height: 600})
        waitForRendering(obj)
        const titles = [], percents = []
        const walk = item => {
            for (let i = 0; i < item.children.length; i++) {
                const c = item.children[i]
                if (c.title !== undefined && c.provider !== undefined && c.visible) titles.push(c.title)
                if (c.objectName === "percentLabel" && c.visible) percents.push(c.text)
                walk(c)
            }
        }
        walk(obj)
        compare(titles, ["Claude", "Claude (Work)", "Codex (Old)"])
        verify(percents.indexOf("77 %") >= 0)
        obj.destroy()
    }

    // "reset" goes below the bar: the percentage column keeps its width and the bars stay aligned
    function test_reset_window_keeps_the_columns_aligned() {
        const original = full.stats
        const stats = JSON.parse(JSON.stringify(original))
        const nowSec = full.nowMs / 1000
        stats.providers.claude.limits = [{id: "five_hour", used_percent: 40, resets_at: nowSec - 60, window_minutes: 300}]
        full.stats = stats
        tryVerify(() => { const l = findChild(full, "percentLabel"); return l && l.text === "0 %" })
        const below = findChild(full, "forecastLabel")
        verify(below.visible)
        compare(below.text, "Reset – starts again from 0 %")
        full.stats = original
    }

    // "lasts until reset" is the normal case: it goes to the tooltip, a warning stays below the bar
    function test_only_a_warning_forecast_shows_below_the_bar() {
        const original = full.stats
        const nowSec = full.nowMs / 1000
        const stats = JSON.parse(JSON.stringify(original))
        stats.providers.claude.limits = [{id: "five_hour", used_percent: 40, resets_at: nowSec + 3600,
                                          window_minutes: 300, forecast: {status: "enough"}}]
        full.stats = stats
        tryVerify(() => { const l = findChild(full, "percentLabel"); return l && l.text === "40 %" })
        verify(!findChild(full, "forecastLabel").visible)
        const warning = JSON.parse(JSON.stringify(stats))
        warning.providers.claude.limits[0].forecast = {status: "full", eta: nowSec + 600}
        full.stats = warning
        tryVerify(() => findChild(full, "forecastLabel").visible)
        verify(findChild(full, "forecastLabel").text.indexOf("Full in ~10 min") === 0)
        full.stats = original
    }

    function test_vanished_limit_leaves_no_bar_behind() {
        const bars = () => {
            const found = []
            const walk = item => {
                for (let i = 0; i < item.children.length; i++) {
                    const c = item.children[i]
                    if (c.limit !== undefined && c.nowSec !== undefined && c.visible) found.push(c)
                    walk(c)
                }
            }
            walk(full)
            return found
        }
        const original = full.stats
        const stats = JSON.parse(JSON.stringify(original))
        stats.providers.claude.limits = [{id: "five_hour", used_percent: 6, resets_at: null, window_minutes: 300},
                                         {id: "seven_day", used_percent: 30, resets_at: null, window_minutes: 10080}]
        full.stats = stats
        waitForRendering(full)
        compare(bars().length, 2)
        const fewer = JSON.parse(JSON.stringify(stats))
        fewer.providers.claude.limits = [{id: "seven_day", used_percent: 31, resets_at: null, window_minutes: 10080}]
        full.stats = fewer
        waitForRendering(full)
        compare(bars().map(b => b.limit.id), ["seven_day"])
        full.stats = original
    }

    // Plasma creates the popup with width 0 and adopts the first minimum height; after that it
    // never shrinks. If the cards were stacked at that point, empty space would remain at the bottom.
    function test_first_minimum_height_already_uses_two_columns() {
        const comp = Qt.createComponent("../io.github.flexomatic81.limitrings/contents/ui/FullRepresentation.qml")
        const obj = comp.createObject(this, {providers: full.providers, nowMs: full.nowMs, warn: 70, crit: 90,
                                             stats: full.stats})
        const first = obj.Layout.minimumHeight
        obj.width = obj.Layout.preferredWidth
        obj.height = first
        waitForRendering(obj)
        verify(first <= obj.Layout.minimumHeight + 1,
               "first minimum height " + first + " > final " + obj.Layout.minimumHeight)
        obj.destroy()
    }
}
