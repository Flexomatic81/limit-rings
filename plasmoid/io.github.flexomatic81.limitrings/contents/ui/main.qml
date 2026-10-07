import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami
import "../code/format.js" as Format
import "../code/build.js" as Build

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
    property real refreshedAtMs: 0   // last "Refresh now", for the hint when the limits are asked for again
    readonly property real nowSec: nowMs / 1000
    readonly property int warn: Plasmoid.configuration.warnThreshold
    readonly property int crit: Plasmoid.configuration.criticalThreshold
    readonly property var accounts: Format.parseAccounts(Plasmoid.configuration.extraAccounts)
    readonly property var providers: {
        const list = []
        if (Plasmoid.configuration.showClaude) list.push({key: "claude", name: "Claude", short: "C"})
        if (Plasmoid.configuration.showCodex) list.push({key: "codex", name: "Codex", short: "X"})
        return Format.displayEntries(list, accounts)
    }
    readonly property string collectorCommand: Format.collectorCommand(Qt.resolvedUrl("../collector/run.py"), Plasmoid.id,
                                                                       Plasmoid.configuration.showNotifications,
                                                                       providers.filter(p => !p.account).map(p => p.key),
                                                                       {thresholds: [Plasmoid.configuration.notifyFirst,
                                                                                     Plasmoid.configuration.notifySecond],
                                                                        reset: Plasmoid.configuration.notifyReset},
                                                                       Format.accountsEnv(accounts))
    readonly property string releaseApi: "https://api.github.com/repos/Flexomatic81/limit-rings/releases/latest"
    readonly property string releasePage: "https://github.com/Flexomatic81/limit-rings/releases/latest"
    readonly property string storeProvider: "api.kde-look.org"   // KNewStuff provider ID of store.kde.org
    readonly property string updateVersion: Plasmoid.configuration.checkUpdates
        && Format.isNewerVersion(Plasmoid.configuration.latestVersion, Build.version)
        ? Plasmoid.configuration.latestVersion : ""
    readonly property string osReleaseCommand: "cat /etc/os-release"
    readonly property string statusMessage: translationHandle
        ? Format.statusMessage(loadError, stats, nowMs,
                               {pythonVersion: pythonVersion, installCommand: Format.pythonInstallCommand(osRelease)})
        : ""

    preferredRepresentation: Plasmoid.formFactor === PlasmaCore.Types.Planar ? fullRepresentation : compactRepresentation
    switchWidth: Kirigami.Units.gridUnit * 12
    switchHeight: Kirigami.Units.gridUnit * 8

    toolTipMainText: "Limit Rings"
    toolTipSubText: translationHandle
        ? Format.tooltipText(stats, providers, nowSec, refreshedAtMs)
          + (updateVersion ? "\n" + Format.i18n("Update available: %1", updateVersion) : "")
        : ""

    compactRepresentation: CompactRepresentation {
        plasmoidItem: root
        stats: root.stats
        providers: root.providers
        nowSec: root.nowSec
        warn: root.warn
        crit: root.crit
        style: Plasmoid.configuration.compactStyle
        hasProblem: root.statusMessage !== ""
        vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical
    }

    fullRepresentation: FullRepresentation {
        stats: root.stats
        providers: root.providers
        nowMs: root.nowMs
        refreshedAtMs: root.refreshedAtMs
        warn: root.warn
        crit: root.crit
        message: root.statusMessage
        updateVersion: root.updateVersion
        installSource: Build.installSource
        hasStoreEntry: Build.storeId !== ""
        updateCommand: Format.updateCommand(Build.repoDir)
        onOpenStore: root.openStoreEntry()
        onOpenReleasePage: Qt.openUrlExternally(root.releasePage)
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
        if (notifier.item) notifier.item.send(notice)
    }

    // Notifications and the store dialog live in files of their own: some distributions package their QML modules
    // (org.kde.notification, org.kde.newstuff) separately, and a missing one must only disable its feature.
    Loader {
        id: notifier
        source: "Notifier.qml"
    }

    // Runs a collector pass right away: the logs are read anew, the limits only when due (5-minute interval,
    // pauses after a rate limit) – the footer says when they come next.
    function refreshNow() {
        refreshedAtMs = Date.now()
        nowMs = refreshedAtMs
        executable.connectSource(root.collectorCommand)
    }

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("Refresh now")
            icon.name: "view-refresh"
            onTriggered: root.refreshNow()
        }
    ]

    // At most once a day; a failed request is not retried before the next day either.
    function checkForUpdate() {
        if (!Plasmoid.configuration.checkUpdates || Build.installSource === "dev") return
        const now = Date.now() / 1000
        if (now - Plasmoid.configuration.lastUpdateCheck < 86400) return
        Plasmoid.configuration.lastUpdateCheck = now
        const xhr = new XMLHttpRequest()
        xhr.onreadystatechange = () => {
            if (xhr.readyState !== XMLHttpRequest.DONE || xhr.status !== 200) return
            try {
                const tag = JSON.parse(xhr.responseText).tag_name
                if (typeof tag === "string") Plasmoid.configuration.latestVersion = tag.replace(/^v/, "")
            } catch (e) {
            }
        }
        xhr.open("GET", releaseApi)
        xhr.setRequestHeader("Accept", "application/vnd.github+json")
        xhr.send()
    }

    function openStoreEntry() {
        if (storeDialog.item) {
            storeDialog.item.open()
            storeDialog.item.showEntryDetails(storeProvider, Build.storeId)
            return
        }
        storeDialog.active = true   // onLoaded opens the dialog
        if (storeDialog.status === Loader.Error) Qt.openUrlExternally(root.releasePage)   // no org.kde.newstuff
    }

    Loader {
        id: storeDialog
        active: false
        source: "StoreDialog.qml"
        onLoaded: {
            item.open()
            item.showEntryDetails(root.storeProvider, Build.storeId)
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

    Timer {
        interval: 3600000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.checkForUpdate()
    }
}
