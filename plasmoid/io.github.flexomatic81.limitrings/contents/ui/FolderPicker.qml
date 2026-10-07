import QtQuick
import QtQuick.Dialogs

// Loaded by configGeneral.qml through a Loader: on distributions that package QtQuick.Dialogs separately, a missing
// module then only hides the folder button instead of breaking the whole settings page.
FolderDialog {
    property int accountIndex: -1   // row of the account the folder is chosen for

    signal chosen(int accountIndex, string path)

    function pathOf(url) {
        return decodeURIComponent(String(url).replace(/^file:\/\//, ""))
    }

    onAccepted: chosen(accountIndex, pathOf(selectedFolder))
}
