@echo off
echo ========================================
echo Building Cereveate_Praxis OPC Server
echo Self-Contained Standalone Package
echo ========================================
echo.

echo Cleaning previous builds...
if exist "bin\Release\net8.0\publish" rmdir /s /q "bin\Release\net8.0\publish"

echo.
echo Building self-contained single-file executable...
echo This will include .NET runtime - NO downloads needed!
echo.

dotnet publish --configuration Release --runtime win-x86 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:IncludeAllContentForSelfExtract=true --output "bin\Release\net8.0\publish"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo *** BUILD FAILED ***
    pause
    exit /b 1
)

echo.
echo Copying web assets...
xcopy /E /I /Y "wwwroot" "bin\Release\net8.0\publish\wwwroot"

echo.
echo Copying configuration...
copy /Y "logging-config.json" "bin\Release\net8.0\publish\" 2>nul

echo.
echo ========================================
echo BUILD COMPLETE!
echo ========================================
echo.
echo Output: bin\Release\net8.0\publish\OpcDaWebBrowser.exe
echo Size: ~60-80 MB (includes .NET runtime)
echo.
echo This is a STANDALONE package - NO .NET installation required!
echo All dependencies are embedded in the single EXE file.
echo.
pause
