import QtQuick
import QtQuick.Layouts
import QtTest
import "../io.github.flexomatic81.limitrings/contents/ui" as UI

TestCase {
    id: tc
    name: "Compact"
    when: windowShown
    width: 400
    height: 400

    readonly property var stats: ({providers: {
        claude: {limits: [{id: "five_hour", used_percent: 40, resets_at: null, window_minutes: 300},
                          {id: "seven_day", used_percent: 20, resets_at: null, window_minutes: 10080}],
                 limits_updated_at: new Date().toISOString()},
        codex: {limits: [{id: "primary", used_percent: 7, resets_at: null, window_minutes: 10080}],
                limits_updated_at: new Date().toISOString()}}})
    readonly property var providers: [{key: "claude", name: "Claude", short: "C"},
                                      {key: "codex", name: "Codex", short: "X"}]

    Component {
        id: compactComponent
        UI.CompactRepresentation {
            plasmoidItem: QtObject { property bool expanded: false }
            stats: tc.stats
            providers: tc.providers
            nowSec: Date.now() / 1000
            warn: 70
            crit: 90
        }
    }

    // A panel gives the widget its thickness and takes the length the widget asks for.
    function place(vertical, thickness, style) {
        const c = createTemporaryObject(compactComponent, tc, {vertical: vertical, style: style})
        verify(c !== null)
        if (vertical) c.width = thickness
        else c.height = thickness
        waitForItemPolished(c.children[0])  // the layout takes in the thickness before the widget names its length
        if (vertical) c.height = Math.max(c.Layout.minimumHeight, c.Layout.preferredHeight)
        else c.width = Math.max(c.Layout.minimumWidth, c.Layout.preferredWidth)
        waitForItemPolished(c.children[0])
        return c
    }

    function gauges(c) {
        const out = []
        const walk = item => {
            for (let i = 0; i < item.children.length; i++) {
                const ch = item.children[i]
                if (ch.letter !== undefined && ch.outerPercent !== undefined) out.push(ch)
                walk(ch)
            }
        }
        walk(c)
        return out
    }

    function checkFits(vertical, thickness, style) {
        const c = place(vertical, thickness, style)
        const list = gauges(c)
        compare(list.length, 2)
        for (let i = 0; i < list.length; i++) {
            const g = list[i], pos = g.mapToItem(c, 0, 0)
            verify(pos.x >= -0.5 && pos.y >= -0.5, "gauge starts outside")
            verify(pos.x + g.width <= c.width + 0.5, style + " " + thickness + ": too wide " + (pos.x + g.width)
                   + " > " + c.width)
            verify(pos.y + g.height <= c.height + 0.5, style + " " + thickness + ": too tall " + (pos.y + g.height)
                   + " > " + c.height)
            verify(g.width > 0 && g.height > 0, "empty gauge " + g.width + "x" + g.height + " in " + c.width + "x" + c.height)
        }
        if (vertical) verify(list[0].mapToItem(c, 0, 0).y < list[1].mapToItem(c, 0, 0).y, "stacked")
        else verify(list[0].mapToItem(c, 0, 0).x < list[1].mapToItem(c, 0, 0).x, "side by side")
    }

    function test_horizontal_panels_data() {
        const rows = []
        for (const t of [22, 32, 64])
            for (const style of ["ring", "number"]) rows.push({tag: style + " " + t, t: t, style: style})
        return rows
    }
    function test_horizontal_panels(d) { checkFits(false, d.t, d.style) }

    function test_vertical_panels_data() { return test_horizontal_panels_data() }
    function test_vertical_panels(d) { checkFits(true, d.t, d.style) }

    // The ring repaints only when what it shows changes – not on every tick of the widget's clock
    function test_ring_repaints_only_on_changes() {
        const c = place(false, 32, "ring")
        const canvas = findChild(gauges(c)[0], "ringCanvas")
        verify(canvas !== null)
        waitForRendering(canvas)
        let paints = 0
        canvas.painted.connect(() => paints++)
        for (let i = 1; i <= 5; i++) {   // five ticks, nothing changes (no reset times → no time mark)
            c.nowSec += 15
            wait(20)
        }
        compare(paints, 0)
        const changed = JSON.parse(JSON.stringify(tc.stats))
        changed.providers.claude.limits[0].used_percent = 41
        c.stats = changed
        tryVerify(() => paints === 1)
        wait(50)
        compare(paints, 1)
    }

    function test_rings_are_square_in_both_directions() {
        for (const vertical of [false, true]) {
            const g = gauges(place(vertical, 40, "ring"))[0]
            fuzzyCompare(g.width, g.height, 1)
        }
    }

    function test_three_gauges_with_an_account() {
        const stats = JSON.parse(JSON.stringify(tc.stats))
        stats.accounts = {k7f3a2: {provider: "claude", dir: "~/.c",
                                   limits: [{id: "five_hour", used_percent: 60, resets_at: null, window_minutes: 300}],
                                   limits_updated_at: new Date().toISOString()}}
        for (const vertical of [false, true]) {
            const c = createTemporaryObject(compactComponent, tc, {vertical: vertical, stats: stats,
                providers: tc.providers.concat([{key: "k7f3a2", account: true, provider: "claude", dir: "~/.c",
                                                 name: "Claude (Work)", short: "A"}])})
            if (vertical) c.width = 32; else c.height = 32
            waitForItemPolished(c.children[0])
            if (vertical) c.height = c.Layout.preferredHeight; else c.width = c.Layout.preferredWidth
            waitForItemPolished(c.children[0])
            const list = gauges(c)
            compare(list.length, 3)
            compare(list[2].letter, "A")
            compare(list[2].innerPercent, 60)
        }
    }
}
