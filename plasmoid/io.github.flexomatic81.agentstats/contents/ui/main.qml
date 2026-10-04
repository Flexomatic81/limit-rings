import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami
import "../code/format.js" as Format

PlasmoidItem {
    id: root

    property var stats: null
    property string loadError: ""
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
    readonly property string statsCommand: 'cat "$HOME/.cache/agent-stats/stats.json"'

    preferredRepresentation: Plasmoid.formFactor === PlasmaCore.Types.Planar ? fullRepresentation : compactRepresentation
    switchWidth: Kirigami.Units.gridUnit * 12
    switchHeight: Kirigami.Units.gridUnit * 8

    toolTipMainText: "Agent Stats"
    toolTipSubText: Format.tooltipText(stats, providers, nowSec)

    compactRepresentation: CompactRepresentation {
        plasmoidItem: root
        stats: root.stats
        providers: root.providers
        nowSec: root.nowSec
        warn: root.warn
        crit: root.crit
        style: Plasmoid.configuration.compactStyle
        hasProblem: Format.statusMessage(root.loadError, root.stats, root.nowMs) !== ""
    }

    fullRepresentation: FullRepresentation {
        stats: root.stats
        providers: root.providers
        nowMs: root.nowMs
        warn: root.warn
        crit: root.crit
        message: Format.statusMessage(root.loadError, root.stats, root.nowMs)
    }

    function applyResult(exitCode, stdout) {
        if (exitCode !== 0) {
            loadError = "nofile"
            return
        }
        try {
            const parsed = JSON.parse(stdout)
            if (parsed.schema !== 1) {
                loadError = "schema"
                return
            }
            stats = parsed
            loadError = ""
        } catch (e) {
            loadError = "parse"
        }
    }

    P5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: (sourceName, data) => {
            disconnectSource(sourceName)
            root.applyResult(data["exit code"], data["stdout"])
        }
    }

    Timer {
        interval: 30000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: executable.connectSource(root.statsCommand)
    }

    Timer {
        interval: 15000
        running: true
        repeat: true
        onTriggered: root.nowMs = Date.now()
    }
}
