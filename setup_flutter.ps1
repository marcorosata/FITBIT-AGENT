# Flutter Setup Script
# Run this AFTER extracting flutter to C:\flutter
#
# Usage: Right-click → "Run with PowerShell"

Write-Host "`n╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          Flutter Setup for Wearable Agent               ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝`n" -ForegroundColor Cyan

# Step 1: Add Flutter to PATH
Write-Host "[1/5] Adding Flutter to PATH..." -ForegroundColor Yellow
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*C:\flutter\bin*") {
    $newPath = $currentPath + ";C:\flutter\bin"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = $newPath
    Write-Host "✓ Flutter added to PATH" -ForegroundColor Green
} else {
    Write-Host "✓ Flutter already in PATH" -ForegroundColor Green
}

# Step 2: Verify Flutter
Write-Host "`n[2/5] Verifying Flutter installation..." -ForegroundColor Yellow
if (Test-Path "C:\flutter\bin\flutter.bat") {
    Write-Host "✓ Flutter found at C:\flutter" -ForegroundColor Green
    & C:\flutter\bin\flutter --version
} else {
    Write-Host "✗ Flutter NOT found at C:\flutter" -ForegroundColor Red
    Write-Host "  Please extract the ZIP to C:\flutter first" -ForegroundColor Yellow
    Pause
    exit 1
}

# Step 3: Run Flutter Doctor
Write-Host "`n[3/5] Running Flutter Doctor..." -ForegroundColor Yellow
& C:\flutter\bin\flutter doctor

# Step 4: Check Android Setup
Write-Host "`n[4/5] Checking Android setup..." -ForegroundColor Yellow
Write-Host "Do you have Android Studio installed? (Y/N)" -ForegroundColor Cyan
$response = Read-Host
if ($response -eq "Y" -or $response -eq "y") {
    Write-Host "✓ Great! Run: flutter doctor --android-licenses" -ForegroundColor Green
} else {
    Write-Host "`nInstall Android Studio:" -ForegroundColor Yellow
    Write-Host "1. Download: https://developer.android.com/studio" -ForegroundColor White
    Write-Host "2. Install with default settings" -ForegroundColor White
    Write-Host "3. Open Android Studio → SDK Manager → Install all recommended components" -ForegroundColor White
    Write-Host "`nOR install via Chocolatey (run PowerShell as Admin):" -ForegroundColor Yellow
    Write-Host "   choco install androidstudio -y" -ForegroundColor Cyan
}

# Step 5: Next Steps
Write-Host "`n[5/5] Next Steps:" -ForegroundColor Yellow
Write-Host "1. Accept Android licenses:" -ForegroundColor White
Write-Host "   flutter doctor --android-licenses" -ForegroundColor Cyan
Write-Host "`n2. Enable USB debugging on your Android phone:" -ForegroundColor White
Write-Host "   Settings → About phone → Tap Build number 7 times" -ForegroundColor Gray
Write-Host "   Settings → System → Developer options → Enable USB debugging" -ForegroundColor Gray
Write-Host "`n3. Connect phone via USB and check:" -ForegroundColor White
Write-Host "   flutter devices" -ForegroundColor Cyan
Write-Host "`n4. Navigate to the app and run:" -ForegroundColor White
Write-Host '   cd "C:\Users\marco\OneDrive - Radboud Universiteit\Desktop\FITBIT AGENT\flutter_app"' -ForegroundColor Cyan
Write-Host "   flutter pub get" -ForegroundColor Cyan
Write-Host "   flutter run" -ForegroundColor Cyan

Write-Host "`n✓ Setup complete! Follow the steps above." -ForegroundColor Green
Write-Host "`nPress any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
