import QtQuick
import QtQuick.Layouts
import Quickshell.Io
import qs.Common
import qs.Widgets
import qs.Modules.Plugins

PluginComponent {
    id: root

    property string barText: "CX ..."
    property string primaryRemaining: "--"
    property string weeklyRemaining: "--"
    property string primaryReset: "--"
    property string weeklyReset: "--"
    property string source: "--"
    property string account: "--"
    property string updatedAt: "--"
    property string errorText: ""
    property bool isBusy: false
    property bool hasError: false

    Component.onCompleted: refreshStatus()

    Timer {
        interval: 120000
        repeat: true
        running: true
        onTriggered: root.refreshStatus()
    }

    function percent(value) {
        if (value === undefined || value === null || isNaN(Number(value))) return "--"
        return Math.round(Number(value)) + "%"
    }

    function resetCountdown(value) {
        if (!value || value === "--") return "--"
        const resetAt = Date.parse(value)
        if (isNaN(resetAt)) return "--"
        const remainingMs = Math.max(0, resetAt - Date.now())
        const totalMinutes = Math.ceil(remainingMs / 60000)
        const hours = Math.floor(totalMinutes / 60)
        const minutes = totalMinutes % 60
        return String(hours).padStart(2, "0") + ":" + String(minutes).padStart(2, "0")
    }

    function refreshStatus() {
        if (!statusProcess.running) statusProcess.running = true
    }

    function updateNow() {
        if (!updateProcess.running) {
            root.isBusy = true
            updateProcess.running = true
        }
    }

    Process {
        id: statusProcess
        command: ["sh", "-c", "kai-codex-usage status 2>/dev/null"]
        running: false

        stdout: StdioCollector {
            onStreamFinished: {
                const raw = this.text.trim()
                if (!raw) return
                try {
                    const data = JSON.parse(raw)
                    root.hasError = !data.ok
                    root.errorText = data.error || ""
                    root.primaryRemaining = root.percent(data.primary_remaining_percent)
                    root.weeklyRemaining = root.percent(data.weekly_remaining_percent)
                    root.primaryReset = root.resetCountdown(data.primary_resets_at)
                    root.weeklyReset = root.resetCountdown(data.weekly_resets_at)
                    root.source = data.source || "--"
                    root.account = data.account || data.identity?.accountEmail || "--"
                    root.updatedAt = data.updated_at || "--"
                    root.barText = data.ok ? "CX " + root.primaryRemaining + " " + root.weeklyRemaining : "CX ?"
                } catch (e) {
                    root.hasError = true
                    root.errorText = "Could not parse usage"
                    root.barText = "CX ?"
                }
            }
        }

        onExited: (exitCode) => {
            if (exitCode !== 0 && root.barText === "CX ...") {
                root.hasError = true
                root.barText = "CX ?"
            }
        }
    }

    Process {
        id: updateProcess
        command: ["sh", "-c", "kai-codex-usage update >/dev/null 2>&1"]
        running: false
        onExited: (exitCode) => {
            root.isBusy = false
            root.refreshStatus()
        }
    }

    horizontalBarPill: Component {
        Row {
            spacing: Theme.spacingXS

            DankIcon {
                name: root.isBusy ? "sync" : "data_usage"
                size: Theme.iconSize - 6
                color: root.hasError ? Theme.error : Theme.primary
                anchors.verticalCenter: parent.verticalCenter
            }

            StyledText {
                text: root.barText
                font.pixelSize: Theme.fontSizeSmall
                font.weight: Font.Medium
                color: Theme.surfaceText
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    verticalBarPill: Component {
        Column {
            spacing: Theme.spacingXS
            DankIcon {
                name: root.isBusy ? "sync" : "data_usage"
                size: Theme.iconSize - 6
                color: root.hasError ? Theme.error : Theme.primary
                anchors.horizontalCenter: parent.horizontalCenter
            }
            StyledText {
                text: root.barText
                font.pixelSize: Theme.fontSizeSmall
                font.weight: Font.Medium
                color: Theme.surfaceText
                anchors.horizontalCenter: parent.horizontalCenter
                rotation: 90
            }
        }
    }

    popoutContent: Component {
        PopoutComponent {
            headerText: "Codex Usage"
            detailsText: root.hasError ? root.errorText : "5h " + root.primaryRemaining + " • Week " + root.weeklyRemaining
            showCloseButton: true

            Column {
                width: parent.width
                spacing: Theme.spacingM

                StyledRect {
                    width: parent.width
                    height: details.implicitHeight + Theme.spacingM * 2
                    radius: Theme.cornerRadius
                    color: Theme.surfaceContainerHigh

                    GridLayout {
                        id: details
                        anchors.fill: parent
                        anchors.margins: Theme.spacingM
                        columns: 2
                        columnSpacing: Theme.spacingL
                        rowSpacing: Theme.spacingS

                        StyledText { text: "5h left"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                        StyledText { text: root.primaryRemaining; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall }
                        StyledText { text: "Week left"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                        StyledText { text: root.weeklyRemaining; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall }
                        StyledText { text: "5h reset"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                        StyledText { text: root.primaryReset + " bis zum reset"; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall; Layout.maximumWidth: 220; elide: Text.ElideRight }
                        StyledText { text: "Week reset"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                        StyledText { text: root.weeklyReset + " bis zum reset"; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall; Layout.maximumWidth: 220; elide: Text.ElideRight }
                        StyledText { text: "Source"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                        StyledText { text: root.source; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall }
                        StyledText { text: "Account"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                        StyledText { text: root.account; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall; Layout.maximumWidth: 220; elide: Text.ElideRight }
                    }
                }

                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: Theme.spacingM

                    MouseArea {
                        width: Theme.iconSize
                        height: Theme.iconSize
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.updateNow()
                        DankIcon {
                            anchors.centerIn: parent
                            name: "refresh"
                            size: Theme.iconSize - 6
                            color: parent.containsMouse ? Theme.primary : Theme.surfaceText
                        }
                    }
                }
            }
        }
    }
}
