' ============================================================================
' Run MQTT Subscriber Service in Background
' This VBScript runs the service hidden without a console window
' ============================================================================

Set objShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get the directory of this script
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batFile = scriptDir & "\run_service.bat"

' Run the batch file hidden (0 = hidden, 1 = normal, 2 = minimized)
objShell.Run Chr(34) & batFile & Chr(34), 0, False

WScript.Echo "MQTT Subscriber Service started in background"
