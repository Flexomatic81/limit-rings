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
    property bool hasProblem: false

    property bool wasExpanded: false

    Layout.minimumWidth: row.implicitWidth
    Layout.preferredWidth: row.implicitWidth
    hoverEnabled: true
    onPressed: wasExpanded = plasmoidItem.expanded
    onClicked: plasmoidItem.expanded = !wasExpanded

    RowLayout {
        id: row
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing

        Repeater {
            model: compact.providers
            delegate: CompactGauge {
                required property var modelData
                readonly property var limits: compact.stats && compact.stats.providers[modelData.key]
                                              ? compact.stats.providers[modelData.key].limits : null
                readonly property var pct: Format.maxPercent(limits, compact.nowSec)
                readonly property var rings: Format.ringLimits(limits, compact.nowSec)
                Layout.fillHeight: true
                letter: modelData.short
                percent: pct
                severity: Format.worstSeverity(limits, compact.nowSec, compact.warn, compact.crit)
                outerPercent: rings.outer ? Format.effectivePercent(rings.outer, compact.nowSec) : null
                innerPercent: rings.inner ? Format.effectivePercent(rings.inner, compact.nowSec) : null
                outerElapsed: Format.elapsedShare(rings.outer, compact.nowSec)
                innerElapsed: Format.elapsedShare(rings.inner, compact.nowSec)
                outerSeverity: Format.limitSeverity(rings.outer, compact.nowSec, compact.warn, compact.crit)
                innerSeverity: Format.limitSeverity(rings.inner, compact.nowSec, compact.warn, compact.crit)
                style: compact.style
                dimmed: compact.hasProblem
                        || Format.limitsStale(compact.stats ? compact.stats.providers[modelData.key] : null,
                                              compact.nowSec * 1000)
            }
        }
    }
}
