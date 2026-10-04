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
        height: 180   // wie die gespeicherte Pop-up-Größe, die den Inhalt abgeschnitten hat
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
        verify(full.Layout.preferredHeight > 200, "Inhalt sollte höher als das alte Pop-up sein")
        verify(full.Layout.minimumHeight >= full.Layout.preferredHeight,
               "minimumHeight " + full.Layout.minimumHeight + " < Inhalt " + full.Layout.preferredHeight)
    }

    // Plasma erzeugt das Pop-up mit Breite 0 und übernimmt die erste Mindesthöhe; danach wird es
    // nicht mehr kleiner. Stünden die Karten dann untereinander, bliebe unten leerer Raum.
    function test_first_minimum_height_already_uses_two_columns() {
        const comp = Qt.createComponent("../io.github.flexomatic81.agentstats/contents/ui/FullRepresentation.qml")
        const obj = comp.createObject(this, {providers: full.providers, nowMs: full.nowMs, warn: 70, crit: 90,
                                             stats: full.stats})
        const first = obj.Layout.minimumHeight
        obj.width = obj.Layout.preferredWidth
        obj.height = first
        waitForRendering(obj)
        verify(first <= obj.Layout.minimumHeight + 1,
               "erste Mindesthöhe " + first + " > endgültige " + obj.Layout.minimumHeight)
        obj.destroy()
    }
}
