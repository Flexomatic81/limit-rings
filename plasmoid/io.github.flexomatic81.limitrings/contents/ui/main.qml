import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami
import org.kde.notification
import "../code/format.js" as Format

PlasmoidItem {
    id: root

    // Hands KDE's translation functions and the system locale to format.js (a .pragma library
    // cannot see i18n); the representations are created after this root object.
    readonly property int translationHandle: Format.init({
        i18n: (...a) => i18n(...a), i18nc: (...a) => i18nc(...a), i18np: (...a) => i18np(...a),
        locale: Qt.locale()})
    property var stats: null
    property string loadError: ""
    property string pythonVersion: ""
    property string osRelease: ""
    property real nowMs: Date.now()
    readonly property real nowSec: nowMs / 1000
    readonly property int warn: Plasmoid.configuration.warnThreshold
    readonly property int crit: Plasmoid.configuration.criticalThreshold
    readonly property var providers: {
        const list = []
        if (Plasmoid.configuration.showClaude) list.push({key: "claude", name: "Claude", short: "C"})
        if (Plasmoid.configuration.showCodex) list.push({key: "codex", name: "Codex", short: "X"})
        return list
    }
    readonly property string collectorCommand: Format.collectorCommand(Qt.resolvedUrl("../collector/run.py"), Plasmoid.id,
                                                                       Plasmoid.configuration.showNotifications)
    readonly property string osReleaseCommand: "cat /etc/os-release"
    readonly property string statusMessage: translationHandle
        ? Format.statusMessage(loadError, stats, nowMs,
                               {pythonVersion: pythonVersion, installCommand: Format.pythonInstallCommand(osRelease)})
        : ""

    preferredRepresentation: Plasmoid.formFactor === PlasmaCore.Types.Planar ? fullRepresentation : compactRepresentation
    switchWidth: Kirigami.Units.gridUnit * 12
    switchHeight: Kirigami.Units.gridUnit * 8

    toolTipMainText: "Limit Rings"
    toolTipSubText: translationHandle ? Format.tooltipText(stats, providers, nowSec) : ""

    compactRepresentation: CompactRepresentation {
        plasmoidItem: root
        stats: root.stats
        providers: root.providers
        nowSec: root.nowSec
        warn: root.warn
        crit: root.crit
        style: Plasmoid.configuration.compactStyle
        hasProblem: root.statusMessage !== ""
    }

    fullRepresentation: FullRepresentation {
        stats: root.stats
        providers: root.providers
        nowMs: root.nowMs
        warn: root.warn
        crit: root.crit
        message: root.statusMessage
    }

    Component.onDestruction: Format.release(translationHandle)
    Component.onCompleted: executable.connectSource(osReleaseCommand)

    function applyResult(exitCode, stdout) {
        const r = Format.readCollectorOutput(exitCode, stdout)
        if (r.stats) stats = r.stats
        loadError = r.error
        pythonVersion = r.pythonVersion
        r.notices.forEach(n => notify(n))   // only non-empty when this instance has notifications on
    }

    function notify(notice) {
        notificationComponent.createObject(root, {
            title: notice.summary, text: notice.body || "",
            urgency: notice.urgent ? Notification.CriticalUrgency : Notification.NormalUrgency
        }).sendEvent()
    }

    // A widget from the store cannot install its own .notifyrc, so it notifies as part of the Plasma workspace.
    Component {
        id: notificationComponent
        Notification {
            componentName: "plasma_workspace"
            eventId: "notification"
            iconName: "utilities-system-monitor"
            hints: ({"x-kde-display-appname": "Limit Rings"})
            autoDelete: true
        }
    }

    P5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: (sourceName, data) => {
            disconnectSource(sourceName)
            if (sourceName === root.osReleaseCommand)
                root.osRelease = data["exit code"] === 0 ? data["stdout"] : ""
            else
                root.applyResult(data["exit code"], data["stdout"])
        }
    }

    // While a long first pass is still running its source stays connected, so this starts no second process.
    // Other instances use their own command (applet id) and meet the collector's lock instead.
    Timer {
        interval: 60000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: executable.connectSource(root.collectorCommand)
    }

    Timer {
        interval: 15000
        running: true
        repeat: true
        onTriggered: root.nowMs = Date.now()
    }
}
