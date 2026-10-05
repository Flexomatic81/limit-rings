import QtQuick
import QtTest
import org.kde.notification

// Notifier.qml is loaded like main.qml loads it. sendEvent() is not called here: it would show a real notification
// on the desktop of whoever runs the tests.
TestCase {
    name: "Notifier"

    Loader {
        id: notifier
        source: "../io.github.flexomatic81.limitrings/contents/ui/Notifier.qml"
    }

    function test_notice_becomes_a_workspace_notification() {
        compare(notifier.status, Loader.Ready)
        verify(typeof notifier.item.send === "function")
        const n = notifier.item.create({summary: "Claude: 5-hour limit at 81 %", body: "Reset in 2 h 0 min",
                                        urgent: false})
        compare(n.title, "Claude: 5-hour limit at 81 %")
        compare(n.text, "Reset in 2 h 0 min")
        compare(n.componentName, "plasma_workspace")
        compare(n.eventId, "notification")
        compare(n.iconName, "utilities-system-monitor")
        compare(n.hints["x-kde-display-appname"], "Limit Rings")
        compare(n.urgency, Notification.NormalUrgency)
        verify(n.autoDelete)
        n.destroy()
    }

    function test_urgent_notice_is_critical_and_body_may_be_missing() {
        const n = notifier.item.create({summary: "Claude: limit reached", urgent: true})
        compare(n.text, "")
        compare(n.urgency, Notification.CriticalUrgency)
        n.destroy()
    }
}
