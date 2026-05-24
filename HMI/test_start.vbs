Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Shakil\DJangoProjects\NEW_HMI\HMI"
WshShell.Run "cmd /c venv\Scripts\activate.bat && python app.py", 0, False
