@echo off
echo.
echo =========================================
echo   ANDROID DEVICE INSTALLER
echo =========================================
echo.

:: Set Flutter path
set PATH=C:\flutter\bin;%PATH%

echo [1/6] Checking Flutter installation...
where flutter >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Flutter not found!
    echo Please wait for Flutter setup to complete, then run this again.
    pause
    exit /b 1
)
echo [OK] Flutter found!

echo.
echo [2/6] Checking Android device connection...
echo.
echo IMPORTANT: On your Android phone:
echo   1. Settings -^> About phone -^> Tap "Build number" 7 times
echo   2. Settings -^> System -^> Developer options
echo   3. Enable "USB debugging"
echo   4. Connect phone via USB cable
echo   5. Allow USB debugging when prompted
echo.
pause

echo.
echo [3/6] Scanning for devices...
flutter devices

echo.
echo [4/6] Navigating to app folder...
cd /d "%~dp0flutter_app"

echo.
echo [5/6] Installing dependencies...
call flutter pub get
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [6/6] Installing app on Android device...
echo.
echo This will:
echo   1. Build the app (first time takes 5-10 minutes)
echo   2. Install APK on your device
echo   3. Launch the app automatically
echo.
echo Press any key to start installation...
pause >nul

echo.
echo ========================================
echo   BUILDING AND INSTALLING...
echo ========================================
echo.

start "Flutter App - Building" cmd /k "flutter run"

echo.
echo Installation started in new window!
echo.
echo After installation:
echo   1. Go to Settings tab in the app
echo   2. Set Server URL: http://YOUR_PC_IP:8000
echo      (Get your PC IP: ipconfig ^| find "IPv4")
echo   3. Set Participant ID: P001
echo   4. Tap "Save & Reconnect"
echo.
echo You can close this window.
timeout /t 5
