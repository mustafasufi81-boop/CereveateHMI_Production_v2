@echo off
REM ============================================================================
REM React Frontend - Production Build Script (Windows)
REM Builds optimized production bundle for deployment
REM ============================================================================

echo ============================================================================
echo React HMI Frontend - Production Build
echo ============================================================================
echo.

cd /d "%~dp0apex-hmi"

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is not installed!
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

echo [1/4] Node.js version:
node --version

REM Check if npm is installed
npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm is not installed!
    pause
    exit /b 1
)

echo [2/4] Installing dependencies...
call npm install
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies!
    pause
    exit /b 1
)

echo [3/4] Building production bundle...
call npm run build
if errorlevel 1 (
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo [4/4] Build complete!
echo.
echo ============================================================================
echo Production build created in: apex-hmi\dist\
echo ============================================================================
echo.
echo Files created:
dir dist /b
echo.
echo Next steps:
echo 1. Deploy backend: cd ..\HMI ^&^& deploy_windows.bat
echo 2. Configure nginx to serve dist folder
echo 3. Access app at: https://hmi.yourdomain.com
echo ============================================================================
pause
