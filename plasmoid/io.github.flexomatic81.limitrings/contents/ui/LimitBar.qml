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

    readonly property bool reset: Format.isReset(limit, nowSec)
    readonly property real pct: Format.effectivePercent(limit, nowSec)
    readonly property string sev: Format.limitSeverity(limit, nowSec, warn, crit)
    readonly property var elapsed: Format.elapsedShare(limit, nowSec)
    readonly property string forecastText: Format.forecastText(limit, nowSec)
    readonly property bool forecastFull: !!(limit.forecast && limit.forecast.status === "full")

    spacing: 0

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

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
                width: parent.width * Math.min(100, bar.pct) / 100
                height: parent.height
                radius: parent.radius
                color: bar.sev === "critical" ? Kirigami.Theme.negativeTextColor
                     : bar.sev === "warning" ? Kirigami.Theme.neutralTextColor
                     : Kirigami.Theme.highlightColor
            }

            // Where the window stands in time: usage ahead of this mark runs fast
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
            text: bar.reset ? Format.i18nc("limit state", "reset") + " · 0 %" : Math.round(bar.pct) + " %"
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

    // Forecast below the bar, aligned with its left edge
    PlasmaComponents.Label {
        visible: bar.forecastText !== ""
        text: bar.forecastText
        font: Kirigami.Theme.smallFont
        color: bar.forecastFull ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.textColor
        opacity: bar.forecastFull ? 1 : 0.7
        Layout.leftMargin: Kirigami.Units.gridUnit * 5 + Kirigami.Units.smallSpacing
        Layout.fillWidth: true
        elide: Text.ElideRight
    }
}
