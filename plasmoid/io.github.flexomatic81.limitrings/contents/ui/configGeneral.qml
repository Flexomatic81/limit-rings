pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import "../code/format.js" as Format

// i18n()/i18nc() come from KDE's localized context, which qmllint cannot see: those lines are marked.
KCM.SimpleKCM {
    id: page

    property alias cfg_warnThreshold: warnSpin.value
    property alias cfg_criticalThreshold: critSpin.value
    property alias cfg_showClaude: claudeBox.checked
    property alias cfg_showCodex: codexBox.checked
    property alias cfg_useLoginClaude: loginClaudeBox.checked
    property alias cfg_useLoginCodex: loginCodexBox.checked
    property alias cfg_showNotifications: notificationsBox.checked
    property alias cfg_notifyFirst: firstSpin.value
    property alias cfg_notifySecond: secondSpin.value
    property alias cfg_notifyReset: resetBox.checked
    property alias cfg_checkUpdates: updatesBox.checked
    property string cfg_compactStyle
    property bool cfg_showRemaining
    property string cfg_extraAccounts
    property var accounts: Format.parseAccounts(cfg_extraAccounts)

    function updateAccount(index, change) {
        const list = accounts.slice()
        list[index] = Object.assign({}, list[index], change)
        cfg_extraAccounts = Format.serializeAccounts(list)
    }
    function removeAccount(index) {
        const list = accounts.slice()
        list.splice(index, 1)
        cfg_extraAccounts = Format.serializeAccounts(list)
    }
    function addAccount(provider) {
        cfg_extraAccounts = Format.serializeAccounts(accounts.concat([Format.newAccount(provider, accounts)]))
    }

    Kirigami.FormLayout {
        QQC2.SpinBox {
            id: warnSpin
            Kirigami.FormData.label: i18n("Warning at (%):") // qmllint disable unqualified
            from: 1; to: critSpin.value - 1
        }
        QQC2.SpinBox {
            id: critSpin
            Kirigami.FormData.label: i18n("Critical at (%):") // qmllint disable unqualified
            from: warnSpin.value + 1; to: 100
        }
        QQC2.CheckBox {
            id: claudeBox
            Kirigami.FormData.label: i18n("Show:") // qmllint disable unqualified
            text: "Claude"
        }
        QQC2.CheckBox {
            id: codexBox
            text: "Codex"
        }
        QQC2.CheckBox {
            id: loginClaudeBox
            Kirigami.FormData.label: i18n("Live limits via login:") // qmllint disable unqualified
            text: "Claude"
        }
        QQC2.CheckBox {
            id: loginCodexBox
            text: "Codex"
        }
        QQC2.Label {
            Layout.fillWidth: true
            // a wrapping label asks for its whole text on one line: keep it about as wide as the longest row
            Layout.maximumWidth: Kirigami.Units.gridUnit * 24
            wrapMode: Text.WordWrap
            font: Kirigami.Theme.smallFont
            text: i18n("Without login, limits come only from Claude's status line or Codex's session logs – no limits per model, no extra usage or credits. Applies to this widget and to the provider's additional accounts.") // qmllint disable unqualified
        }
        QQC2.CheckBox {
            id: notificationsBox
            Kirigami.FormData.label: i18n("Notifications:") // qmllint disable unqualified
            text: i18n("Warn when a limit reaches %1 % or %2 %", firstSpin.value, secondSpin.value) // qmllint disable unqualified
        }
        QQC2.SpinBox {
            id: firstSpin
            Kirigami.FormData.label: i18n("Notify at (%):") // qmllint disable unqualified
            enabled: notificationsBox.checked
            from: 1; to: secondSpin.value - 1
        }
        QQC2.SpinBox {
            id: secondSpin
            Kirigami.FormData.label: i18n("Urgent at (%):") // qmllint disable unqualified
            enabled: notificationsBox.checked
            from: firstSpin.value + 1; to: 100
        }
        QQC2.CheckBox {
            id: resetBox
            enabled: notificationsBox.checked
            text: i18n("Tell me when a limit has reset after a warning") // qmllint disable unqualified
        }
        QQC2.ComboBox {
            Kirigami.FormData.label: i18n("Panel:") // qmllint disable unqualified
            model: [{value: "ring", text: i18nc("panel display style", "Ring")}, // qmllint disable unqualified
                    {value: "number", text: i18nc("panel display style", "Number")}] // qmllint disable unqualified
            textRole: "text"
            valueRole: "value"
            // not indexOfValue(): evaluated before the model is set, it stays at -1 and leaves the box empty
            currentIndex: page.cfg_compactStyle === "number" ? 1 : 0
            onActivated: page.cfg_compactStyle = currentValue
        }
        QQC2.ComboBox {
            Kirigami.FormData.label: i18n("Percentages:") // qmllint disable unqualified
            model: [i18nc("show the percentage of a limit that is", "Used"), // qmllint disable unqualified
                    i18nc("show the percentage of a limit that is", "Remaining")] // qmllint disable unqualified
            currentIndex: page.cfg_showRemaining ? 1 : 0
            onActivated: page.cfg_showRemaining = currentIndex === 1
        }
        QQC2.CheckBox {
            id: updatesBox
            Kirigami.FormData.label: i18n("Updates:") // qmllint disable unqualified
            text: i18n("Check daily for a new version (asks GitHub)") // qmllint disable unqualified
        }
        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Additional accounts") // qmllint disable unqualified
        }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: i18n("For accounts you use with CLAUDE_CONFIG_DIR or CODEX_HOME in their own directory.") // qmllint disable unqualified
        }
        Repeater {
            // A number: rows are only recreated when accounts are added or removed, so editing keeps focus.
            model: page.accounts.length
            delegate: RowLayout {
                id: accountRow
                required property int index
                readonly property var account: page.accounts[index] || ({})
                // Handlers below always use accountRow.index: ComboBox.activated passes its own "index"
                // (the chosen item) that would otherwise shadow the row index.
                QQC2.ComboBox {
                    model: ["Claude", "Codex"]
                    currentIndex: accountRow.account.provider === "codex" ? 1 : 0
                    onActivated: chosen => page.updateAccount(accountRow.index, {provider: chosen === 1 ? "codex" : "claude"})
                }
                QQC2.TextField {
                    Layout.fillWidth: true
                    placeholderText: i18n("Directory") // qmllint disable unqualified
                    text: accountRow.account.dir
                    onEditingFinished: page.updateAccount(accountRow.index, {dir: text})
                }
                QQC2.ToolButton {
                    icon.name: "document-open-folder"
                    QQC2.ToolTip.text: i18n("Choose directory") // qmllint disable unqualified
                    QQC2.ToolTip.visible: hovered
                    visible: folderPicker.status === Loader.Ready
                    onClicked: {
                        const picker = folderPicker.item as FolderPicker
                        picker.accountIndex = accountRow.index
                        picker.open()
                    }
                }
                QQC2.TextField {
                    placeholderText: i18n("Name") // qmllint disable unqualified
                    text: accountRow.account.name
                    onEditingFinished: page.updateAccount(accountRow.index, {name: text})
                }
                QQC2.TextField {
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 3
                    maximumLength: 2
                    placeholderText: i18nc("short letters for the panel ring", "Short") // qmllint disable unqualified
                    text: accountRow.account.short
                    onEditingFinished: page.updateAccount(accountRow.index, {short: text})
                }
                QQC2.CheckBox {
                    text: i18n("Show") // qmllint disable unqualified
                    checked: accountRow.account.show
                    onToggled: page.updateAccount(accountRow.index, {show: checked})
                }
                QQC2.ToolButton {
                    icon.name: "edit-delete"
                    QQC2.ToolTip.text: i18n("Remove account") // qmllint disable unqualified
                    QQC2.ToolTip.visible: hovered
                    onClicked: page.removeAccount(accountRow.index)
                }
            }
        }
        RowLayout {
            visible: page.accounts.length < Format.MAX_ACCOUNTS
            QQC2.Button { text: i18n("Add Claude account"); icon.name: "list-add"; onClicked: page.addAccount("claude") } // qmllint disable unqualified
            QQC2.Button { text: i18n("Add Codex account"); icon.name: "list-add"; onClicked: page.addAccount("codex") } // qmllint disable unqualified
        }
    }

    // The folder dialog lives in a file of its own: QtQuick.Dialogs is a separate package on some distributions
    Loader {
        id: folderPicker
        source: "FolderPicker.qml"
    }
    Connections {
        target: folderPicker.item
        function onChosen(accountIndex, path) { page.updateAccount(accountIndex, {dir: path}) }
    }
}
