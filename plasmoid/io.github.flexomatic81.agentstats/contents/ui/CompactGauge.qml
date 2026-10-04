import QtQuick
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents

Item {
    id: gauge

    property string letter: ""
    property var percent: null        // höchster Wert, für die Darstellung „Zahl“ (null = keine Daten)
    property var outerPercent: null   // äußerer Ring: Wochenlimit
    property var innerPercent: null   // innerer Ring: 5-h-Limit (null = kein innerer Ring)
    property string severity: "normal"
    property string outerSeverity: "normal"
    property string innerSeverity: "normal"
    property string style: "ring"
    property bool dimmed: false

    function toneFor(sev) {
        return sev === "critical" ? Kirigami.Theme.negativeTextColor
             : sev === "warning" ? Kirigami.Theme.neutralTextColor
             : Kirigami.Theme.highlightColor
    }

    readonly property color tone: toneFor(severity)
    readonly property color outerTone: toneFor(outerSeverity)
    readonly property color innerTone: toneFor(innerSeverity)
    readonly property color trackColor: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g,
                                                Kirigami.Theme.textColor.b, 0.2)
    readonly property bool hasInner: innerPercent !== null

    implicitWidth: style === "ring" ? height : label.implicitWidth
    implicitHeight: Kirigami.Units.iconSizes.medium
    opacity: dimmed ? 0.5 : 1

    Canvas {
        id: ring
        visible: gauge.style === "ring"
        anchors.fill: parent

        function arc(ctx, r, lineWidth, pct, color) {
            ctx.lineWidth = lineWidth
            ctx.strokeStyle = gauge.trackColor
            ctx.beginPath()
            ctx.arc(ring.width / 2, ring.height / 2, r, 0, 2 * Math.PI)
            ctx.stroke()
            if (pct !== null) {
                ctx.strokeStyle = color
                ctx.beginPath()
                ctx.arc(ring.width / 2, ring.height / 2, r, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * Math.min(100, pct) / 100)
                ctx.stroke()
            }
        }

        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const r = Math.min(width, height) / 2 - 2
            arc(ctx, r, 3, gauge.outerPercent, gauge.outerTone)
            if (gauge.hasInner)
                arc(ctx, r - 5, 2.5, gauge.innerPercent, gauge.innerTone)
        }

        Connections {
            target: gauge
            function onOuterPercentChanged() { ring.requestPaint() }
            function onInnerPercentChanged() { ring.requestPaint() }
            function onOuterToneChanged() { ring.requestPaint() }
            function onInnerToneChanged() { ring.requestPaint() }
            function onTrackColorChanged() { ring.requestPaint() }
        }
    }

    PlasmaComponents.Label {
        id: label
        anchors.centerIn: parent
        text: gauge.style === "ring"
              ? gauge.letter
              : gauge.letter + " " + (gauge.percent === null ? "–" : Math.round(gauge.percent) + "%")
        font.pixelSize: gauge.style === "ring" ? parent.height * (gauge.hasInner ? 0.3 : 0.4)
                                               : Kirigami.Theme.smallFont.pixelSize * 1.1
        color: gauge.style === "ring" ? Kirigami.Theme.textColor : gauge.tone
    }
}
