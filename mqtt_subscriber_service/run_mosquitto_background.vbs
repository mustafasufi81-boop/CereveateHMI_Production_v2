' ============================================================================
' Run Mosquitto Broker in Background
' This VBScript runs Mosquitto hidden without a console window
' ============================================================================

Set objShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get the directory of this script
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
confFile = scriptDir & "\mosquitto_test.conf"
mosquittoPath = "C:\Program Files\mosquitto\mosquitto.exe"

' Build command
cmd = Chr(34) & mosquittoPath & Chr(34) & " -c " & Chr(34) & confFile & Chr(34) & " -v"

' Run Mosquitto hidden (0 = hidden, 1 = normal, 2 = minimized)
objShell.Run cmd, 0, False
