import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: full

    property var stats
    property var providers: []
    property real nowMs
    property real refreshedAtMs
    property int warn
    property int crit
    property string message: ""
    property string updateVersion: ""
    property string installSource: "dev"
    property bool hasStoreEntry: false
    property string updateCommand: ""
    signal openStore()
    signal openReleasePage()
    property real cardMinWidth: 0   // largest minimum width reported by any card

    Layout.preferredWidth: Kirigami.Units.gridUnit * 38
    Layout.preferredHeight: content.implicitHeight + Kirigami.Units.largeSpacing * 2
    Layout.minimumWidth: Kirigami.Units.gridUnit * 14
    // As tall as the content: otherwise a saved popup size cuts off new content
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

        UpdateMessage {
            version: full.updateVersion
            installSource: full.installSource
            hasStoreEntry: full.hasStoreEntry
            command: full.updateCommand
            onOpenStore: full.openStore()
            onOpenReleasePage: full.openReleasePage()
        }

        GridLayout {
            id: cards
            Layout.fillWidth: true
            // Before the first layout the width is 0: assume the intended width then, otherwise
            // Plasma adopts the height for stacked cards and leaves empty space at the bottom.
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
                    refreshedAtMs: full.refreshedAtMs
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
