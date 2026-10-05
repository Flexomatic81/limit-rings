import QtQuick
import org.kde.newstuff as NewStuff

// Loaded by main.qml through a Loader: on distributions that package org.kde.newstuff separately, a missing module
// then only replaces the store dialog with the release page instead of breaking the whole widget.
NewStuff.Dialog {
    configFile: "plasmoids.knsrc"
}
