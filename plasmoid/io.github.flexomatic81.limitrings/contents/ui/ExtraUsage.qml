import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "../code/format.js" as Format

// Claude's extra usage or Codex credits below the limit bars: a bar when there is a monthly limit,
// otherwise a line of text. Same columns as LimitBar.
ColumnLayout {
    id: extraRow

    property var extra
    property int warn
    property int crit

    readonly property bool hasBar: extra.percent !== null && extra.percent !== undefined
    readonly property real pct: hasBar ? extra.percent : 0
    readonly property string sev: Format.severity(pct, warn, crit)

    spacing: 0

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents.Label {
            text: Format.extraName(extraRow.extra)
            Layout.preferredWidth: Kirigami.Units.gridUnit * 5
            elide: Text.ElideRight
        }

        Rectangle {
            visible: extraRow.hasBar
            Layout.fillWidth: true
            Layout.preferredHeight: Kirigami.Units.smallSpacing * 2
            radius: height / 2
            color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.15)

            Rectangle {
                width: parent.width * Math.min(100, extraRow.pct) / 100
                height: parent.height
                radius: parent.radius
                color: Format.toneFor(extraRow.sev, Kirigami.Theme)
            }
        }

        PlasmaComponents.Label {
            visible: extraRow.hasBar
            text: Math.round(extraRow.pct) + " %"
            font.bold: extraRow.sev !== "normal"
            color: extraRow.sev === "normal" ? Kirigami.Theme.textColor : Format.toneFor(extraRow.sev, Kirigami.Theme)
            Layout.preferredWidth: Math.max(Kirigami.Units.gridUnit * 3, implicitWidth)
            horizontalAlignment: Text.AlignRight
        }

        // Without a monthly limit: the amount takes the place of the bar
        PlasmaComponents.Label {
            visible: !extraRow.hasBar
            text: Format.extraText(extraRow.extra)
            Layout.fillWidth: true
            elide: Text.ElideRight
        }

        Item { Layout.preferredWidth: Kirigami.Units.gridUnit * 3 }
    }

    // With a monthly limit: the amounts below the bar, aligned with its left edge
    PlasmaComponents.Label {
        visible: extraRow.hasBar
        text: Format.extraText(extraRow.extra)
        font: Kirigami.Theme.smallFont
        opacity: 0.7
        Layout.leftMargin: Kirigami.Units.gridUnit * 5 + Kirigami.Units.smallSpacing
        Layout.fillWidth: true
        elide: Text.ElideRight
    }
}
