import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import "../code/format.js" as Format

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
        Kirigami.Separator {
            Kirigami.FormData.isSection: true
            Kirigami.FormData.label: i18n("Additional accounts")
        }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: i18n("For accounts you use with CLAUDE_CONFIG_DIR or CODEX_HOME in their own directory.")
        }
        Repeater {
            // A number: rows are only recreated when accounts are added or removed, so editing keeps focus.
            model: accounts.length
            delegate: RowLayout {
                id: accountRow
                required property int index
                readonly property var account: accounts[index] || ({})
                // Handlers below always use accountRow.index: ComboBox.activated passes its own "index"
                // (the chosen item) that would otherwise shadow the row index.
                QQC2.ComboBox {
                    model: ["Claude", "Codex"]
                    currentIndex: accountRow.account.provider === "codex" ? 1 : 0
                    onActivated: chosen => updateAccount(accountRow.index, {provider: chosen === 1 ? "codex" : "claude"})
                }
                QQC2.TextField {
                    Layout.fillWidth: true
                    placeholderText: i18n("Directory")
                    text: accountRow.account.dir
                    onEditingFinished: updateAccount(accountRow.index, {dir: text})
                }
                QQC2.ToolButton {
                    icon.name: "document-open-folder"
                    QQC2.ToolTip.text: i18n("Choose directory")
                    QQC2.ToolTip.visible: hovered
                    visible: folderPicker.status === Loader.Ready
                    onClicked: { folderPicker.item.accountIndex = accountRow.index; folderPicker.item.open() }
                }
                QQC2.TextField {
                    placeholderText: i18n("Name")
                    text: accountRow.account.name
                    onEditingFinished: updateAccount(accountRow.index, {name: text})
                }
                QQC2.TextField {
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 3
                    maximumLength: 2
                    placeholderText: i18nc("short letters for the panel ring", "Short")
                    text: accountRow.account.short
                    onEditingFinished: updateAccount(accountRow.index, {short: text})
                }
                QQC2.CheckBox {
                    text: i18n("Show")
                    checked: accountRow.account.show
                    onToggled: updateAccount(accountRow.index, {show: checked})
                }
                QQC2.ToolButton {
                    icon.name: "edit-delete"
                    QQC2.ToolTip.text: i18n("Remove account")
                    QQC2.ToolTip.visible: hovered
                    onClicked: removeAccount(accountRow.index)
                }
            }
        }
        RowLayout {
            visible: accounts.length < Format.MAX_ACCOUNTS
            QQC2.Button { text: i18n("Add Claude account"); icon.name: "list-add"; onClicked: addAccount("claude") }
            QQC2.Button { text: i18n("Add Codex account"); icon.name: "list-add"; onClicked: addAccount("codex") }
        }
    }

    // The folder dialog lives in a file of its own: QtQuick.Dialogs is a separate package on some distributions
    Loader {
        id: folderPicker
        source: "FolderPicker.qml"
    }
    Connections {
        target: folderPicker.item
        function onChosen(accountIndex, path) { updateAccount(accountIndex, {dir: path}) }
    }
}
