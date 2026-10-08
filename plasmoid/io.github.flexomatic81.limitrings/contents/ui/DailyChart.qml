import QtQuick
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "../code/format.js" as Format

Item {
    id: chart

    property var series: []
    property string range: "days"   // what one bar stands for: a day, a week or a month (Format.chartRanges)
    readonly property real maxTotal: {
        let m = 0
        for (let i = 0; i < series.length; i++) m = Math.max(m, series[i].total)
        return m
    }
    readonly property real gap: 2

    Row {
        anchors.fill: parent
        spacing: chart.gap

        Repeater {
            model: chart.series
            delegate: Item {
                required property var modelData
                width: chart.series.length > 0 ? (chart.width - chart.gap * (chart.series.length - 1)) / chart.series.length : 0
                height: chart.height

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: chart.maxTotal > 0 ? Math.max(1, parent.height * modelData.total / chart.maxTotal) : 1
                    color: Kirigami.Theme.highlightColor
                    opacity: hover.hovered ? 1 : 0.7
                }

                HoverHandler { id: hover }

                PlasmaComponents.ToolTip {
                    visible: hover.hovered
                    text: Format.chartTooltip(modelData, chart.range)
                }
            }
        }
    }
}
