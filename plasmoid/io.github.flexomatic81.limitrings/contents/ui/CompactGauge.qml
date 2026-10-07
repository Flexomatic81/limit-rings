import QtQuick
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "../code/format.js" as Format

Item {
    id: gauge

    property string letter: ""
    property var percent: null        // highest value, for the "Number" style (null = no data)
    property var outerPercent: null   // outer ring: weekly limit
    property var innerPercent: null   // inner ring: 5 h limit (null = no inner ring)
    property var outerElapsed: null   // share of the window that has passed (0–1), drawn as a mark; null = none
    property var innerElapsed: null
    property string severity: "normal"
    property string outerSeverity: "normal"
    property string innerSeverity: "normal"
    property string style: "ring"
    property bool vertical: false     // vertical panel: the width is given, the height follows
    property bool dimmed: false

    function toneFor(sev) {
        return Format.toneFor(sev, Kirigami.Theme)
    }

    readonly property color tone: toneFor(severity)
    readonly property color outerTone: toneFor(outerSeverity)
    readonly property color innerTone: toneFor(innerSeverity)
    readonly property color trackColor: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g,
                                                Kirigami.Theme.textColor.b, 0.2)
    readonly property bool hasInner: innerPercent !== null

    // Horizontal panel: the height is given; vertical panel: the width. The ring stays square.
    implicitWidth: vertical ? Kirigami.Units.iconSizes.small : (style === "ring" ? height : label.implicitWidth)
    implicitHeight: vertical ? (style === "ring" ? width : label.implicitHeight) : Kirigami.Units.iconSizes.medium
    opacity: dimmed ? 0.5 : 1

    Canvas {
        id: ring
        objectName: "ringCanvas"
        visible: gauge.style === "ring"
        anchors.fill: parent

        // Short stroke across the ring where the window stands in time: usage ahead of it runs fast
        function mark(ctx, r, lineWidth, share) {
            if (share === null) return
            const a = -Math.PI / 2 + 2 * Math.PI * share
            const cx = ring.width / 2, cy = ring.height / 2, half = lineWidth / 2 + 1
            ctx.lineWidth = 1.5
            ctx.strokeStyle = Kirigami.Theme.textColor
            ctx.beginPath()
            ctx.moveTo(cx + (r - half) * Math.cos(a), cy + (r - half) * Math.sin(a))
            ctx.lineTo(cx + (r + half) * Math.cos(a), cy + (r + half) * Math.sin(a))
            ctx.stroke()
        }

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
            mark(ctx, r, 3, gauge.outerElapsed)
            if (gauge.hasInner) {
                arc(ctx, r - 5, 2.5, gauge.innerPercent, gauge.innerTone)
                mark(ctx, r - 5, 2.5, gauge.innerElapsed)
            }
        }

        Connections {
            target: gauge
            function onOuterPercentChanged() { ring.requestPaint() }
            function onInnerPercentChanged() { ring.requestPaint() }
            function onOuterToneChanged() { ring.requestPaint() }
            function onInnerToneChanged() { ring.requestPaint() }
            function onTrackColorChanged() { ring.requestPaint() }
            function onOuterElapsedChanged() { ring.requestPaint() }
            function onInnerElapsedChanged() { ring.requestPaint() }
        }
    }

    PlasmaComponents.Label {
        id: label
        anchors.centerIn: parent
        // On a vertical panel letter and number go on two lines and shrink to the panel width
        width: gauge.vertical && gauge.style !== "ring" ? gauge.width : implicitWidth
        horizontalAlignment: Text.AlignHCenter
        fontSizeMode: gauge.vertical && gauge.style !== "ring" ? Text.HorizontalFit : Text.FixedSize
        minimumPixelSize: 6
        text: gauge.style === "ring"
              ? gauge.letter
              : gauge.letter + (gauge.vertical ? "\n" : " ") + (gauge.percent === null ? "–" : Math.round(gauge.percent) + "%")
        font.pixelSize: gauge.style === "ring" ? parent.height * (gauge.hasInner ? 0.3 : 0.4)
                                               : Kirigami.Theme.smallFont.pixelSize * 1.1
        color: gauge.style === "ring" ? Kirigami.Theme.textColor : gauge.tone
    }
}
