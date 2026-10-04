import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "../code/format.js" as Format

ColumnLayout {
    id: card

    property string title
    property var provider      // providers.<key> aus stats.json oder undefined (nicht "data": Default-Property von Item)
    property real nowMs
    property int warn
    property int crit
    readonly property real nowSec: nowMs / 1000
    // Breite, die die Karte bekommt; vom Elternlayout vorgegeben, weil width vor dem ersten Layout 0 ist
    property real layoutWidth: width
    readonly property bool stale: Format.limitsStale(provider, nowMs)
    // Breite, unter der die Karte abgeschnitten würde (meist die Zeile Heute/Woche/Monat)
    readonly property real minimumContentWidth: Math.max(header.implicitWidth, tokenGrid.implicitWidth)

    spacing: Kirigami.Units.smallSpacing

    RowLayout {
        id: header
        Kirigami.Heading { level: 4; text: card.title }
        PlasmaComponents.Label {
            text: card.provider && card.provider.plan ? card.provider.plan : ""
            opacity: 0.7
        }
        Item { Layout.fillWidth: true }
    }

    PlasmaComponents.Label {
        readonly property string hint: card.provider ? Format.authHint(card.provider.auth) : ""
        visible: hint !== ""
        text: hint
        color: Kirigami.Theme.neutralTextColor
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    PlasmaComponents.Label {
        visible: !!(card.provider && card.provider.error)
        text: card.provider && card.provider.error ? card.provider.error : ""
        color: Kirigami.Theme.negativeTextColor
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    Repeater {
        model: card.provider ? card.provider.limits : []
        delegate: LimitBar {
            required property var modelData
            Layout.fillWidth: true
            opacity: card.stale ? 0.5 : 1
            limit: modelData
            nowSec: card.nowSec
            warn: card.warn
            crit: card.crit
        }
    }

    PlasmaComponents.Label {
        visible: !card.provider || card.provider.limits.length === 0
        text: "Keine Limit-Daten"
        opacity: 0.7
    }

    GridLayout {
        id: tokenGrid
        columns: 6
        columnSpacing: Kirigami.Units.smallSpacing
        visible: !!card.provider

        Repeater {
            model: [{key: "today", label: "Heute"}, {key: "week", label: "Woche"}, {key: "month", label: "Monat"}]
            delegate: RowLayout {
                required property var modelData
                Layout.columnSpan: 2
                PlasmaComponents.Label { text: modelData.label; opacity: 0.7 }
                PlasmaComponents.Label {
                    id: value
                    text: card.provider ? Format.compactNumber(card.provider.tokens[modelData.key].total) : ""
                    font.bold: true
                    HoverHandler { id: valueHover }
                    PlasmaComponents.ToolTip {
                        visible: valueHover.hovered
                        text: card.provider ? Format.tokenBreakdown(card.provider.tokens[modelData.key]) : ""
                    }
                }
            }
        }
    }

    DailyChart {
        Layout.fillWidth: true
        Layout.preferredHeight: Kirigami.Units.gridUnit * 2.5
        series: card.provider ? card.provider.daily : []
    }

    // Aufschlüsselung nach Projekt und Modell (nur Claude)
    ColumnLayout {
        id: breakdownBlock
        readonly property var b: card.provider ? card.provider.breakdown : null
        visible: !!(b && b.total > 0)
        Layout.fillWidth: true
        Layout.topMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents.Label {
            text: breakdownBlock.b ? Format.breakdownTitle(breakdownBlock.b) + " · Anteil an Tokens" : ""
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }

        GridLayout {
            Layout.fillWidth: true
            columns: card.layoutWidth >= Kirigami.Units.gridUnit * 24 ? 2 : 1
            columnSpacing: Kirigami.Units.largeSpacing * 2
            rowSpacing: Kirigami.Units.smallSpacing

            BreakdownList {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: "Projekte"
                rows: breakdownBlock.b ? Format.breakdownRows(breakdownBlock.b.projects, breakdownBlock.b.total) : []
            }
            BreakdownList {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: "Modelle"
                rows: breakdownBlock.b ? Format.breakdownRows(breakdownBlock.b.models, breakdownBlock.b.total) : []
            }
        }
    }

    PlasmaComponents.Label {
        text: Format.footerText(card.provider, card.nowMs)
        font: Kirigami.Theme.smallFont
        color: card.stale ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.textColor
        opacity: card.stale ? 1 : 0.6
    }
}
