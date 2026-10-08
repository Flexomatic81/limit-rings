import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "../code/format.js" as Format

MouseArea {
    id: compact

    property var plasmoidItem
    property var stats
    property var providers: []
    property real nowSec
    property int warn
    property int crit
    property string style: "ring"
    property bool remaining: false   // show what is left instead of what is used (colours keep going by usage)
    property bool hasProblem: false
    property bool vertical: false   // vertical panel: the gauges stack, the panel width is the size


    property bool wasExpanded: false

    Layout.minimumWidth: vertical ? -1 : row.implicitWidth
    Layout.preferredWidth: vertical ? -1 : row.implicitWidth
    Layout.minimumHeight: vertical ? row.implicitHeight : -1
    Layout.preferredHeight: vertical ? row.implicitHeight : -1
    hoverEnabled: true
    onPressed: wasExpanded = plasmoidItem.expanded
    onClicked: plasmoidItem.expanded = !wasExpanded

    GridLayout {
        id: row
        anchors.fill: parent
        flow: compact.vertical ? GridLayout.TopToBottom : GridLayout.LeftToRight
        rows: compact.vertical ? Math.max(1, compact.providers.length) : 1
        columns: compact.vertical ? 1 : Math.max(1, compact.providers.length)
        rowSpacing: Kirigami.Units.smallSpacing
        columnSpacing: Kirigami.Units.smallSpacing

        Repeater {
            model: compact.providers
            delegate: CompactGauge {
                required property var modelData
                readonly property var entryStats: Format.entryData(compact.stats, modelData)
                readonly property var limits: entryStats ? entryStats.limits : null
                readonly property var pct: Format.shownMax(limits, compact.nowSec, compact.remaining)
                readonly property var rings: Format.ringLimits(limits, compact.nowSec)
                Layout.fillHeight: !compact.vertical
                Layout.fillWidth: compact.vertical
                vertical: compact.vertical
                letter: modelData.short
                percent: pct
                severity: Format.worstSeverity(limits, compact.nowSec, compact.warn, compact.crit)
                outerPercent: rings.outer ? Format.shownPercent(rings.outer, compact.nowSec, compact.remaining) : null
                innerPercent: rings.inner ? Format.shownPercent(rings.inner, compact.nowSec, compact.remaining) : null
                outerElapsed: Format.shownShare(Format.elapsedShare(rings.outer, compact.nowSec), compact.remaining)
                innerElapsed: Format.shownShare(Format.elapsedShare(rings.inner, compact.nowSec), compact.remaining)
                outerSeverity: Format.limitSeverity(rings.outer, compact.nowSec, compact.warn, compact.crit)
                innerSeverity: Format.limitSeverity(rings.inner, compact.nowSec, compact.warn, compact.crit)
                style: compact.style
                dimmed: compact.hasProblem
                        || Format.limitsStale(entryStats || null, compact.nowSec * 1000)
            }
        }
    }
}
