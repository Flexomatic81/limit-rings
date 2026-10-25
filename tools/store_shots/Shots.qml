// Renders the parts of the store images (docs/store/shots/) from invented data (fake.js), at the scale
// tools/store_shots.py runs it with. The placeholders @UI@, @CODE@ and @OUT@ are filled in by that script.
import QtQuick
import QtQuick.Layouts
import QtTest
import org.kde.kirigami as Kirigami
import "@UI@" as UI
import "@CODE@/format.js" as Format
import "fake.js" as Fake

TestCase {
    id: tc
    name: "Store"
    when: windowShown
    visible: true
    width: 1300
    height: 2600

    readonly property string out: "@OUT@/"
    readonly property var both: [{key: "claude", name: "Claude", short: "C"}, {key: "codex", name: "Codex", short: "X"}]
    readonly property var claudeOnly: [{key: "claude", name: "Claude", short: "C"}]
    readonly property var withAccount: both.concat([{key: "w0rk01", account: true, provider: "claude",
                                                     name: "Claude (Work)", short: "W", dir: "~/.claude-work"}])
    readonly property var statsMain: Fake.stats(false)
    readonly property var statsAccounts: Fake.stats(true)

    Item {
        id: themed
        anchors.fill: parent
        Kirigami.Theme.inherit: false
        Kirigami.Theme.textColor: "#fcfcfc"
        Kirigami.Theme.backgroundColor: "#202326"
        Kirigami.Theme.alternateBackgroundColor: "#292c30"
        Kirigami.Theme.highlightColor: "#3daee9"
        Kirigami.Theme.highlightedTextColor: "#fcfcfc"
        Kirigami.Theme.disabledTextColor: "#a1a9b1"
        Kirigami.Theme.neutralTextColor: "#f67400"
        Kirigami.Theme.negativeTextColor: "#da4453"
        Kirigami.Theme.positiveTextColor: "#27ae60"

        Column {
            spacing: 20
            Rectangle {
                id: popupBothShot
                color: "#202326"
                width: popupBoth.width; height: popupBoth.height
                UI.FullRepresentation {
                    id: popupBoth
                    width: 820; height: Layout.preferredHeight
                    providers: tc.both; stats: tc.statsMain
                    nowMs: Fake.NOW * 1000; warn: 70; crit: 90; installSource: "store"
                }
            }
            Rectangle {
                id: popupClaudeShot
                color: "#202326"
                width: popupClaude.width; height: popupClaude.height
                UI.FullRepresentation {
                    id: popupClaude
                    width: 420; height: Layout.preferredHeight
                    providers: tc.claudeOnly; stats: tc.statsMain
                    nowMs: Fake.NOW * 1000; warn: 70; crit: 90; installSource: "store"
                }
            }
            Row {
                spacing: 20
                Compact { id: ringsMain; providers: tc.both; stats: tc.statsMain }
                Compact { id: number; providers: tc.both; stats: tc.statsMain; style: "number" }
                Compact { id: remaining; providers: tc.both; stats: tc.statsMain; remaining: true }
                Compact { id: accounts; providers: tc.withAccount; stats: tc.statsAccounts }
                Compact { id: vertical; providers: tc.both; stats: tc.statsMain; vertical: true }
            }
            Rectangle {
                id: tooltip
                width: tipText.implicitWidth + 32; height: tipTitle.height + tipText.height + 42
                color: "#2a2e32"; border.color: "#3e4347"; radius: 6
                Text { id: tipTitle; x: 16; y: 14; text: "Limit Rings"; color: "#fcfcfc"; font.bold: true; font.pointSize: 10 }
                Text {
                    id: tipText; x: 16; y: tipTitle.y + tipTitle.height + 10
                    color: "#d4d6d8"; font.pointSize: 10; lineHeight: 1.15
                    text: Format.tooltipText(tc.statsMain, tc.both, Fake.NOW, 0, false)
                }
            }
        }
    }

    component Compact: UI.CompactRepresentation {
        plasmoidItem: QtObject { property bool expanded: false }
        nowSec: Fake.NOW
        warn: 70; crit: 90
        // a panel 44 px thick; vertical: 44 px wide
        width: vertical ? 44 : Math.max(Layout.minimumWidth, Layout.preferredWidth)
        height: vertical ? Math.max(Layout.minimumHeight, Layout.preferredHeight) : 44
    }

    function save(item, file) {
        let done = false
        item.grabToImage(r => { r.saveToFile(tc.out + file); done = true })
        tryVerify(() => done, 5000)
    }

    function textItem(root, prefix) {
        for (let i = 0; i < root.children.length; i++) {
            const c = root.children[i]
            if (c.visible && c.text !== undefined && String(c.text).indexOf(prefix) === 0) return c
            const r = textItem(c, prefix)
            if (r) return r
        }
        return null
    }

    function test_store() {
        waitForRendering(themed)
        wait(400)
        save(popupBothShot, "popup-both.png")
        save(popupClaudeShot, "popup-claude.png")
        save(ringsMain, "panel-rings.png")
        save(number, "panel-number.png")
        save(remaining, "panel-remaining.png")
        save(accounts, "panel-accounts.png")
        save(vertical, "panel-vertical.png")
        save(tooltip, "tooltip.png")
        // where the parts of the Claude card are, as a share of its height (for the labels in image 2)
        const marks = {}
        for (const [key, prefix] of [["limits", "5 h"], ["forecast", "Full in"], ["extra", "Extra usage"],
                                     ["tokens", "Today"], ["chart", "30 days"], ["breakdown", "Since weekly reset"],
                                     ["models", "Models"]]) {
            const t = textItem(popupClaude, prefix)
            if (t) { const p = t.mapToItem(popupClaude, 0, t.height / 2); marks[key] = p.y / popupClaude.height }
        }
        const chart = findChild(popupClaude, "dailyChart")
        if (chart) { const p = chart.mapToItem(popupClaude, 0, chart.height / 2); marks.chartMid = p.y / popupClaude.height }
        // where the parts of the Claude card are, as a share of its height: the labels of store image 2
        console.log("MARKS " + JSON.stringify(marks))
        console.log("SIZES " + JSON.stringify({both: [popupBoth.width, popupBoth.height], claude: [popupClaude.width, popupClaude.height],
            rings: [ringsMain.width, ringsMain.height], number: [number.width, number.height], remaining: [remaining.width, remaining.height],
            accounts: [accounts.width, accounts.height], vertical: [vertical.width, vertical.height], tooltip: [tooltip.width, tooltip.height]}))
    }
}
