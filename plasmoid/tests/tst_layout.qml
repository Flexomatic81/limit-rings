import QtQuick
import QtQuick.Layouts
import QtTest
import "../io.github.flexomatic81.agentstats/contents/ui" as UI

TestCase {
    name: "Layout"
    when: windowShown
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
        stats: ({schema: 1, generated_at: "2026-10-04T13:29:30+02:00", providers: {claude: {
            limits: [{id: "five_hour", label: "5 h", used_percent: 6, resets_at: null, window_minutes: 300}],
            limits_source: "oauth", limits_updated_at: "2026-10-04T13:29:00+02:00", plan: "pro",
            tokens: {today: {input: 1, output: 1, cache_read: 1, cache_write: 1, total: 4},
                     week: {input: 1, output: 1, cache_read: 1, cache_write: 1, total: 4},
                     month: {input: 1, output: 1, cache_read: 1, cache_write: 1, total: 4}},
            daily: [{date: "2026-10-04", total: 4}], error: null,
            breakdown: {since: "2026-09-29T06:00:00+02:00", basis: "window", total: 100,
                        projects: [{name: "website", total: 67}, {name: "agent-stats", total: 33}],
                        models: [{name: "Opus 5.5", total: 100}]}}}})
    }

    function test_minimum_height_covers_content() {
        waitForRendering(full)
        verify(full.Layout.preferredHeight > 200, "content should be taller than the old popup")
        verify(full.Layout.minimumHeight >= full.Layout.preferredHeight,
               "minimumHeight " + full.Layout.minimumHeight + " < content " + full.Layout.preferredHeight)
    }

    // Plasma creates the popup with width 0 and adopts the first minimum height; after that it
    // never shrinks. If the cards were stacked at that point, empty space would remain at the bottom.
    function test_first_minimum_height_already_uses_two_columns() {
        const comp = Qt.createComponent("../io.github.flexomatic81.agentstats/contents/ui/FullRepresentation.qml")
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
