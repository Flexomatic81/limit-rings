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
