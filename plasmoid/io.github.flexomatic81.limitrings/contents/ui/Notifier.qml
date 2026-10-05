import QtQuick
import org.kde.notification

// Loaded by main.qml through a Loader: on distributions that package org.kde.notification separately, a missing
// module then only disables notifications instead of the whole widget.
QtObject {
    id: notifier

    // A widget from the store cannot install its own .notifyrc, so it notifies as part of the Plasma workspace.
    readonly property Component notification: Component {
        Notification {
            componentName: "plasma_workspace"
            eventId: "notification"
            iconName: "utilities-system-monitor"
            hints: ({"x-kde-display-appname": "Limit Rings"})
            autoDelete: true
        }
    }

    function create(notice) {
        return notification.createObject(notifier, {
            title: notice.summary, text: notice.body || "",
            urgency: notice.urgent ? Notification.CriticalUrgency : Notification.NormalUrgency
        })
    }

    function send(notice) {
        create(notice).sendEvent()
    }
}
