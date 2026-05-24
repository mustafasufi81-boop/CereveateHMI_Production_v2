@echo off
REM Launch OPC DA Web Browser in kiosk mode (hides address bar and URL)
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --app=http://localhost:6001 --window-size=1400,900 --disable-infobars --no-first-run --kiosk
