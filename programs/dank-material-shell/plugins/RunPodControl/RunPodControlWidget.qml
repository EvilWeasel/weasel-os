import QtQuick
import QtQuick.Layouts
import Quickshell.Io
import qs.Common
import qs.Widgets
import qs.Modules.Plugins

PluginComponent {
    id: root

    property string barText: "RP ..."
    property string podName: "RunPod"
    property string podStatus: "UNKNOWN"
    property string podStatusShort: "..."
    property string currentSpendPerHr: "--"
    property string podCostPerHr: "--"
    property string monthSpend: "--"
    property string monthStorageSpend: "--"
    property string balance: "--"
    property string comfyUrl: ""
    property string sshTarget: ""
    property bool isBusy: false
    property bool hasError: false

    Component.onCompleted: refreshStatus()

    Timer {
        id: refreshTimer
        interval: 30000
        repeat: true
        running: true
        onTriggered: root.refreshStatus()
    }

    function money(value) {
        if (value === undefined || value === null || isNaN(Number(value))) return "--"
        return "$" + Number(value).toFixed(2)
    }

    function shortStatus(status) {
        if (status === "RUNNING") return "RUN"
        if (status === "EXITED" || status === "STOPPED") return "STOP"
        return status ? status.slice(0, 4) : "..."
    }

    function refreshStatus() {
        if (!statusProcess.running) {
            statusProcess.running = true
        }
    }

    function runAction(command) {
        if (!command || actionProcess.running) return
        root.isBusy = true
        actionProcess.command = ["sh", "-c", command]
        actionProcess.running = true
    }

    Process {
        id: statusProcess
        command: ["sh", "-c", "ai-gen-runpod status 2>/dev/null"]
        running: false

        stdout: StdioCollector {
            onStreamFinished: {
                const raw = this.text.trim()
                if (!raw) return
                try {
                    const data = JSON.parse(raw)
                    root.hasError = false
                    root.podName = data.pod_name || data.pod_id || "RunPod"
                    root.podStatus = data.pod_status || "UNKNOWN"
                    root.podStatusShort = data.status_short || root.shortStatus(root.podStatus)
                    root.currentSpendPerHr = root.money(data.current_spend_per_hr)
                    root.podCostPerHr = root.money(data.pod_cost_per_hr)
                    root.monthSpend = root.money(data.month_spend)
                    root.monthStorageSpend = root.money(data.month_storage_spend)
                    root.balance = root.money(data.client_balance)
                    root.comfyUrl = data.comfy_url || ""
                    root.sshTarget = data.public_ip && data.ssh_port ? data.public_ip + ":" + data.ssh_port : ""
                    root.barText = "RP " + root.podStatusShort
                } catch (e) {
                    root.hasError = true
                    root.barText = "RP ?"
                }
            }
        }

        onExited: (exitCode) => {
            if (exitCode !== 0) {
                root.hasError = true
                root.barText = "RP ?"
            }
        }
    }

    Process {
        id: actionProcess
        command: ["sh", "-c", ""]
        running: false

        onExited: (exitCode) => {
            root.isBusy = false
            root.refreshStatus()
        }
    }

    component RunPodIconButton: MouseArea {
        property string iconName: "circle"
        property string actionCommand: ""
        property string accentColor: Theme.surfaceText

        width: Theme.iconSize
        height: Theme.iconSize
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.runAction(actionCommand)

        DankIcon {
            anchors.centerIn: parent
            name: parent.iconName
            size: Theme.iconSize - 6
            color: parent.containsMouse ? Theme.primary : parent.accentColor
        }
    }

    horizontalBarPill: Component {
        Row {
            spacing: Theme.spacingXS

            DankIcon {
                name: root.isBusy ? "sync" : "cloud"
                size: Theme.iconSize - 6
                color: root.podStatus === "RUNNING" ? Theme.success : root.hasError ? Theme.error : Theme.surfaceText
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
                name: root.isBusy ? "sync" : "cloud"
                size: Theme.iconSize - 6
                color: root.podStatus === "RUNNING" ? Theme.success : root.hasError ? Theme.error : Theme.surfaceText
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
            headerText: "RunPod"
            detailsText: root.podName + " • " + root.podStatus
            showCloseButton: true

            Column {
                width: parent.width
                spacing: Theme.spacingM

                StyledRect {
                    width: parent.width
                    height: podDetails.implicitHeight + Theme.spacingM * 2
                    radius: Theme.cornerRadius
                    color: Theme.surfaceContainerHigh

                    Column {
                        id: podDetails
                        anchors.fill: parent
                        anchors.margins: Theme.spacingM
                        spacing: Theme.spacingS

                        Row {
                            width: parent.width
                            spacing: Theme.spacingM

                            DankIcon {
                                name: root.podStatus === "RUNNING" ? "cloud_done" : "cloud_off"
                                size: Theme.iconSize
                                color: root.podStatus === "RUNNING" ? Theme.success : Theme.surfaceVariantText
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Column {
                                width: parent.width - Theme.iconSize - Theme.spacingM
                                spacing: 1

                                StyledText {
                                    text: root.podName
                                    font.pixelSize: Theme.fontSizeMedium
                                    font.weight: Font.Medium
                                    color: Theme.surfaceText
                                    width: parent.width
                                    elide: Text.ElideRight
                                }

                                StyledText {
                                    text: root.podStatus + (root.sshTarget ? " • SSH " + root.sshTarget : "")
                                    font.pixelSize: Theme.fontSizeSmall
                                    color: Theme.surfaceVariantText
                                    width: parent.width
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        GridLayout {
                            columns: 2
                            columnSpacing: Theme.spacingL
                            rowSpacing: Theme.spacingXS
                            width: parent.width

                            StyledText { text: "Now"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                            StyledText { text: root.currentSpendPerHr + "/h"; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall }
                            StyledText { text: "Pod"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                            StyledText { text: root.podCostPerHr + "/h"; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall }
                            StyledText { text: "Month"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                            StyledText { text: root.monthSpend; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall }
                            StyledText { text: "Storage"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                            StyledText { text: root.monthStorageSpend; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall }
                            StyledText { text: "Balance"; color: Theme.surfaceVariantText; font.pixelSize: Theme.fontSizeSmall }
                            StyledText { text: root.balance; color: Theme.surfaceText; font.pixelSize: Theme.fontSizeSmall }
                        }
                    }
                }

                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: Theme.spacingM

                    RunPodIconButton {
                        iconName: "play_arrow"
                        actionCommand: "ai-gen-runpod start"
                        accentColor: Theme.success
                    }

                    RunPodIconButton {
                        iconName: "stop"
                        actionCommand: "ai-gen-runpod stop"
                        accentColor: Theme.error
                    }

                    RunPodIconButton {
                        iconName: "open_in_new"
                        actionCommand: "ai-gen-runpod open"
                    }

                    RunPodIconButton {
                        iconName: "sync"
                        actionCommand: "ai-gen-runpod sync-down"
                    }
                }
            }
        }
    }
}
