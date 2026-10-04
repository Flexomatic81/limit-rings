import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: full

    property var stats
    property var providers: []
    property real nowMs
    property int warn
    property int crit
    property string message: ""
    property real cardMinWidth: 0   // größte gemeldete Mindestbreite einer Karte

    Layout.preferredWidth: Kirigami.Units.gridUnit * 38
    Layout.preferredHeight: content.implicitHeight + Kirigami.Units.largeSpacing * 2
    Layout.minimumWidth: Kirigami.Units.gridUnit * 14
    // So hoch wie der Inhalt: sonst schneidet eine gespeicherte Pop-up-Größe neue Inhalte ab
    Layout.minimumHeight: Layout.preferredHeight

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: full.message !== ""
            type: Kirigami.MessageType.Warning
            text: full.message
        }

        GridLayout {
            id: cards
            Layout.fillWidth: true
            // Vor dem ersten Layout ist die Breite 0: dann die vorgesehene Breite annehmen, sonst
            // übernimmt Plasma die Höhe für untereinanderstehende Karten und lässt unten Raum frei.
            readonly property real availableWidth: full.width > 0
                ? content.width : full.Layout.preferredWidth - 2 * Kirigami.Units.largeSpacing
            columns: full.cardMinWidth > 0 && availableWidth >= 2 * full.cardMinWidth + cards.columnSpacing ? 2 : 1
            columnSpacing: Kirigami.Units.largeSpacing * 2
            rowSpacing: Kirigami.Units.largeSpacing

            Repeater {
                model: full.providers
                delegate: ProviderCard {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    title: modelData.name
                    provider: full.stats ? full.stats.providers[modelData.key] : undefined
                    nowMs: full.nowMs
                    warn: full.warn
                    crit: full.crit
                    layoutWidth: cards.columns === 2 ? (cards.availableWidth - cards.columnSpacing) / 2
                                                     : cards.availableWidth
                    onMinimumContentWidthChanged: full.cardMinWidth = Math.max(full.cardMinWidth, minimumContentWidth)
                    Component.onCompleted: full.cardMinWidth = Math.max(full.cardMinWidth, minimumContentWidth)
                }
            }
        }

        Item { Layout.fillHeight: true }
    }
}
