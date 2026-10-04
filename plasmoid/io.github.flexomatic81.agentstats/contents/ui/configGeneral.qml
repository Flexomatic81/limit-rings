import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_warnThreshold: warnSpin.value
    property alias cfg_criticalThreshold: critSpin.value
    property alias cfg_showClaude: claudeBox.checked
    property alias cfg_showCodex: codexBox.checked
    property string cfg_compactStyle

    Kirigami.FormLayout {
        QQC2.SpinBox {
            id: warnSpin
            Kirigami.FormData.label: "Warnung ab (%):"
            from: 1; to: critSpin.value - 1
        }
        QQC2.SpinBox {
            id: critSpin
            Kirigami.FormData.label: "Kritisch ab (%):"
            from: warnSpin.value + 1; to: 100
        }
        QQC2.CheckBox {
            id: claudeBox
            Kirigami.FormData.label: "Anzeigen:"
            text: "Claude"
        }
        QQC2.CheckBox {
            id: codexBox
            text: "Codex"
        }
        QQC2.ComboBox {
            Kirigami.FormData.label: "Leiste:"
            model: [{value: "ring", text: "Ring"}, {value: "number", text: "Zahl"}]
            textRole: "text"
            valueRole: "value"
            currentIndex: indexOfValue(cfg_compactStyle)
            onActivated: cfg_compactStyle = currentValue
        }
    }
}
