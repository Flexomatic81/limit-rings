import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "../code/format.js" as Format

ColumnLayout {
    id: card

    property string title
    property var entry: null   // display entry (main account or additional account), for the sign-in hint
    property var provider      // providers.<key> from stats.json or undefined (not "data": that is Item's default property)
    property real nowMs
    property real refreshedAtMs
    property int warn
    property int crit
    property bool remaining: false
    readonly property real nowSec: nowMs / 1000
    // Width the card gets; set by the parent layout because width is 0 before the first layout
    property real layoutWidth: width
    readonly property bool stale: Format.limitsStale(provider, nowMs)
    // Width below which the card would be clipped (usually the Today/Week/Month row)
    readonly property real minimumContentWidth: Math.max(header.implicitWidth, tokenGrid.implicitWidth)

    spacing: Kirigami.Units.smallSpacing

    RowLayout {
        id: header
        Kirigami.Heading { level: 4; text: card.title }
        PlasmaComponents.Label {
            text: card.provider ? Format.planName(card.provider.plan) : ""
            opacity: 0.7
        }
        Item { Layout.fillWidth: true }
    }

    PlasmaComponents.Label {
        readonly property string hint: card.provider ? (Format.authHint(card.provider.auth, card.entry)
                                                         || Format.loginHint(card.provider, card.entry)) : ""
        visible: hint !== ""
        text: hint
        color: Kirigami.Theme.neutralTextColor
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    PlasmaComponents.Label {
        objectName: "limitChanges"
        readonly property string changes: card.provider ? Format.changesText(card.provider.changes) : ""
        visible: changes !== ""
        text: changes
        color: Kirigami.Theme.neutralTextColor
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    PlasmaComponents.Label {
        readonly property string errors: card.provider ? Format.errorText(card.provider.errors) : ""
        visible: errors !== ""
        text: errors
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
            remaining: card.remaining
        }
    }

    ExtraUsage {
        objectName: "extraUsage"
        visible: !!(card.provider && card.provider.extra)
        Layout.fillWidth: true
        opacity: card.stale ? 0.5 : 1
        extra: card.provider && card.provider.extra ? card.provider.extra : ({})
        warn: card.warn
        crit: card.crit
    }

    PlasmaComponents.Label {
        visible: !card.provider || card.provider.limits.length === 0
        text: Format.i18n("No limit data")
        opacity: 0.7
    }

    GridLayout {
        id: tokenGrid
        columns: 6
        columnSpacing: Kirigami.Units.smallSpacing
        visible: !!card.provider

        Repeater {
            model: [{key: "today", label: Format.i18nc("token totals", "Today")},
                    {key: "week", label: Format.i18nc("token totals", "Week")},
                    {key: "month", label: Format.i18nc("token totals", "Month")}]
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

    // Breakdown by project and model (Claude only)
    ColumnLayout {
        id: breakdownBlock
        readonly property var b: card.provider ? card.provider.breakdown : null
        visible: !!(b && b.total > 0)
        Layout.fillWidth: true
        Layout.topMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents.Label {
            text: breakdownBlock.b ? Format.i18n("%1 · share of tokens", Format.breakdownTitle(breakdownBlock.b)) : ""
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
                title: Format.i18n("Projects")
                rows: breakdownBlock.b ? Format.breakdownRows(breakdownBlock.b.projects, breakdownBlock.b.total) : []
            }
            BreakdownList {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                title: Format.i18n("Models")
                rows: breakdownBlock.b ? Format.breakdownRows(breakdownBlock.b.models, breakdownBlock.b.total) : []
            }
        }
    }

    PlasmaComponents.Label {
        text: Format.footerText(card.provider, card.nowMs, card.refreshedAtMs)
        font: Kirigami.Theme.smallFont
        color: card.stale ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.textColor
        opacity: card.stale ? 1 : 0.6
    }
}
