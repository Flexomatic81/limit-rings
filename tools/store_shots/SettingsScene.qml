// Renders the settings page for store image 5. tools/store_shots.py runs it as a widget application with the
// stock Breeze Dark colours, from a copy of configGeneral.qml (ui/ConfigPage.qml) that brings stand-ins for KDE's
// i18n(), which only Plasma provides. The placeholder @OUT@ is filled in by that script.
import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import "ui" as Cfg

QQC2.ApplicationWindow {
    visible: true
    width: 700
    height: 600
    color: Kirigami.Theme.backgroundColor
    Cfg.ConfigPage {
        id: page
        anchors.fill: parent
        cfg_warnThreshold: 70; cfg_criticalThreshold: 90; cfg_showClaude: true; cfg_showCodex: true
        cfg_useLoginClaude: true; cfg_useLoginCodex: false; cfg_showNotifications: true
        cfg_notifyFirst: 80; cfg_notifySecond: 95; cfg_notifyReset: true; cfg_checkUpdates: true
        cfg_compactStyle: "ring"; cfg_showRemaining: false; cfg_extraAccounts: "[]"
    }
    Item { id: sink; focus: true }   // takes the focus, so no field shows a focus frame
    Timer {
        interval: 1500; running: true
        onTriggered: { sink.forceActiveFocus(); grab.start() }
    }
    Timer {
        id: grab
        interval: 400
        onTriggered: page.grabToImage(r => { r.saveToFile("@OUT@/settings.png"); Qt.quit() })
    }
}
