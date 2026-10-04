import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "../code/format.js" as Format

// One breakdown list (projects or models): name, bar, share
ColumnLayout {
    id: list

    property string title
    property var rows: []   // Format.breakdownRows(...)

    spacing: 0

    PlasmaComponents.Label {
        text: list.title
        font: Kirigami.Theme.smallFont
        opacity: 0.7
    }

    Repeater {
        model: list.rows
        delegate: RowLayout {
            id: row
            required property var modelData
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents.Label {
                text: row.modelData.name
                Layout.preferredWidth: Kirigami.Units.gridUnit * 5
                elide: Text.ElideRight
            }

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: Kirigami.Units.smallSpacing * 2

                Rectangle {
                    width: Math.max(1, parent.width * row.modelData.pct / 100)
                    height: parent.height
                    radius: height / 2
                    color: Kirigami.Theme.highlightColor
                    opacity: row.modelData.other ? 0.4 : 0.8
                }
            }

            PlasmaComponents.Label {
                text: Format.percentText(row.modelData.pct)
                Layout.preferredWidth: Kirigami.Units.gridUnit * 2.5
                horizontalAlignment: Text.AlignRight
            }

            HoverHandler { id: hover }
            PlasmaComponents.ToolTip {
                visible: hover.hovered
                text: Format.breakdownTooltip(row.modelData)
            }
        }
    }
}
