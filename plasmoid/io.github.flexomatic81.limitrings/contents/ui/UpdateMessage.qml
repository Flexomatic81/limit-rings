import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "../code/format.js" as Format

// Shown in the popup when a newer release exists; the widget root decides what the buttons do.
Kirigami.InlineMessage {
    id: msg

    property string version: ""
    property string installSource: "dev"   // "store", "git" or "dev", see contents/code/build.js
    property bool hasStoreEntry: false
    property string command: ""            // update command for a git checkout
    signal openStore()
    signal openReleasePage()

    // TextEdit is the only way to reach the clipboard from plain QML.
    readonly property TextEdit clipboard: TextEdit { visible: false }

    objectName: "updateMessage"
    Layout.fillWidth: true
    visible: version !== ""
    type: Kirigami.MessageType.Information
    text: installSource === "git" ? Format.i18n("Version %1 is available. Update with: %2", version, command)
                                  : Format.i18n("Version %1 is available.", version)
    actions: [
        Kirigami.Action {
            visible: msg.installSource === "git"
            icon.name: "edit-copy"
            text: Format.i18n("Copy command")
            onTriggered: {
                msg.clipboard.text = msg.command
                msg.clipboard.selectAll()
                msg.clipboard.copy()
            }
        },
        Kirigami.Action {
            visible: msg.installSource !== "git"
            icon.name: "update-none"
            text: msg.hasStoreEntry ? Format.i18n("Update") : Format.i18n("Open release page")
            onTriggered: msg.hasStoreEntry ? msg.openStore() : msg.openReleasePage()
        }
    ]
}
