import QtQuick
import QtTest
import "../io.github.flexomatic81.limitrings/contents/ui" as UI

TestCase {
    name: "FolderPicker"

    UI.FolderPicker { id: picker }

    SignalSpy { id: spy; target: picker; signalName: "chosen" }

    function test_folder_url_becomes_a_plain_path() {
        compare(picker.pathOf("file:///home/someone/my%20accounts/.claude-w%C3%B6rk"), "/home/someone/my accounts/.claude-wörk")
    }

    function test_accepting_reports_the_row() {
        picker.accountIndex = 2
        picker.accepted()
        compare(spy.count, 1)
        compare(spy.signalArguments[0][0], 2)
    }
}
