import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "../code/format.js" as Format

ColumnLayout {
    id: bar

    property var limit
    property real nowSec
    property int warn
    property int crit
    property bool remaining: false   // show what is left instead of what is used (colours keep going by usage)

    readonly property bool reset: Format.isReset(limit, nowSec)
    readonly property string sev: Format.limitSeverity(limit, nowSec, warn, crit)
    readonly property real shown: Format.shownPercent(limit, nowSec, remaining)
    readonly property var elapsed: Format.shownShare(Format.elapsedShare(limit, nowSec), remaining)
    readonly property bool forecastFull: !!(limit.forecast && limit.forecast.status === "full")

    spacing: 0

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        HoverHandler { id: hover }
        PlasmaComponents.ToolTip {
            readonly property string tip: Format.barTooltip(bar.limit, bar.nowSec)
            visible: hover.hovered && tip !== ""
            text: tip
        }

        PlasmaComponents.Label {
            text: Format.limitName(bar.limit)
            Layout.preferredWidth: Kirigami.Units.gridUnit * 5
            elide: Text.ElideRight
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Kirigami.Units.smallSpacing * 2
            radius: height / 2
            color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.15)

            Rectangle {
                width: parent.width * Math.min(100, bar.shown) / 100
                height: parent.height
                radius: parent.radius
                color: Format.toneFor(bar.sev, Kirigami.Theme)
            }

            // Where the window stands in time: usage ahead of this mark runs fast (remaining: what is left
            // falls short of the time still to come)
            Rectangle {
                objectName: "elapsedMark"
                visible: bar.elapsed !== null
                width: 2
                height: parent.height + Kirigami.Units.smallSpacing
                anchors.verticalCenter: parent.verticalCenter
                x: Math.round(parent.width * (bar.elapsed || 0) - width / 2)
                color: Kirigami.Theme.textColor
            }
        }

        PlasmaComponents.Label {
            objectName: "percentLabel"
            text: Format.limitPercentText(bar.limit, bar.nowSec, bar.remaining)   // a reset window says so below the bar
            font.bold: bar.sev !== "normal"
            color: bar.sev === "normal" ? Kirigami.Theme.textColor : Format.toneFor(bar.sev, Kirigami.Theme)
            Layout.preferredWidth: Math.max(Kirigami.Units.gridUnit * 3, implicitWidth)
            horizontalAlignment: Text.AlignRight
        }

        PlasmaComponents.Label {
            text: bar.reset ? "" : Format.countdownShort(bar.limit.resets_at, bar.nowSec)
            Layout.preferredWidth: Kirigami.Units.gridUnit * 3
            horizontalAlignment: Text.AlignRight
            opacity: 0.7
        }
    }

    // A warning forecast (or that the window has reset) below the bar, aligned with its left edge
    PlasmaComponents.Label {
        objectName: "forecastLabel"
        visible: text !== ""
        text: Format.barNote(bar.limit, bar.nowSec)
        font: Kirigami.Theme.smallFont
        color: bar.forecastFull ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.textColor
        opacity: bar.forecastFull ? 1 : 0.7
        Layout.leftMargin: Kirigami.Units.gridUnit * 5 + Kirigami.Units.smallSpacing
        Layout.fillWidth: true
        elide: Text.ElideRight
    }
}
