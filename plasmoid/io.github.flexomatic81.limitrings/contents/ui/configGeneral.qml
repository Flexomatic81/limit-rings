import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_warnThreshold: warnSpin.value
    property alias cfg_criticalThreshold: critSpin.value
    property alias cfg_showClaude: claudeBox.checked
    property alias cfg_showCodex: codexBox.checked
    property alias cfg_showNotifications: notificationsBox.checked
    property alias cfg_notifyFirst: firstSpin.value
    property alias cfg_notifySecond: secondSpin.value
    property alias cfg_notifyReset: resetBox.checked
    property alias cfg_checkUpdates: updatesBox.checked
    property string cfg_compactStyle

    Kirigami.FormLayout {
        QQC2.SpinBox {
            id: warnSpin
            Kirigami.FormData.label: i18n("Warning at (%):")
            from: 1; to: critSpin.value - 1
        }
        QQC2.SpinBox {
            id: critSpin
            Kirigami.FormData.label: i18n("Critical at (%):")
            from: warnSpin.value + 1; to: 100
        }
        QQC2.CheckBox {
            id: claudeBox
            Kirigami.FormData.label: i18n("Show:")
            text: "Claude"
        }
        QQC2.CheckBox {
            id: codexBox
            text: "Codex"
        }
        QQC2.CheckBox {
            id: notificationsBox
            Kirigami.FormData.label: i18n("Notifications:")
            text: i18n("Warn when a limit reaches %1 % or %2 %", firstSpin.value, secondSpin.value)
        }
        QQC2.SpinBox {
            id: firstSpin
            Kirigami.FormData.label: i18n("Notify at (%):")
            enabled: notificationsBox.checked
            from: 1; to: secondSpin.value - 1
        }
        QQC2.SpinBox {
            id: secondSpin
            Kirigami.FormData.label: i18n("Urgent at (%):")
            enabled: notificationsBox.checked
            from: firstSpin.value + 1; to: 100
        }
        QQC2.CheckBox {
            id: resetBox
            enabled: notificationsBox.checked
            text: i18n("Tell me when a limit has reset after a warning")
        }
        QQC2.ComboBox {
            Kirigami.FormData.label: i18n("Panel:")
            model: [{value: "ring", text: i18nc("panel display style", "Ring")},
                    {value: "number", text: i18nc("panel display style", "Number")}]
            textRole: "text"
            valueRole: "value"
            currentIndex: indexOfValue(cfg_compactStyle)
            onActivated: cfg_compactStyle = currentValue
        }
        QQC2.CheckBox {
            id: updatesBox
            Kirigami.FormData.label: i18n("Updates:")
            text: i18n("Check daily for a new version (asks GitHub)")
        }
    }
}
