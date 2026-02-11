# Flutter Setup & Installation Guide

## Step 1: Install Flutter (Windows)

### Quick Install via Winget (Recommended)
```powershell
# Install Flutter
winget install -e --id Google.Flutter

# Restart your terminal, then verify
flutter --version
```

### Manual Install (Alternative)
1. Download Flutter SDK: https://docs.flutter.dev/get-started/install/windows
2. Extract to `C:\flutter` (or your preferred location)
3. Add to PATH: `C:\flutter\bin`
4. Restart terminal and run `flutter --version`

## Step 2: Install Android Studio & SDK

### Option A: Android Studio (Full IDE)
1. Download: https://developer.android.com/studio
2. Install with default settings
3. Open Android Studio → SDK Manager → Install:
   - Android SDK Platform (latest)
   - Android SDK Build-Tools
   - Android SDK Command-line Tools

### Option B: Command-line Tools Only (Lighter)
```powershell
# Via winget
winget install Google.AndroidStudio

# OR download cmdline-tools from:
# https://developer.android.com/studio#command-tools
```

## Step 3: Accept Android Licenses
```powershell
flutter doctor --android-licenses
# Press 'y' to accept all licenses
```

## Step 4: Enable Developer Mode on Android Device

### On Your Android Phone/Tablet:
1. Go to **Settings** → **About phone**
2. Tap **Build number** 7 times (enables Developer options)
3. Go back → **System** → **Developer options**
4. Enable **USB debugging**
5. Connect device via USB cable to your PC
6. Accept the "Allow USB debugging" prompt on your phone

## Step 5: Verify Setup
```powershell
flutter doctor -v
```
Should show:
- ✓ Flutter (Channel stable)
- ✓ Android toolchain
- ✓ Connected devices (your Android device)

## Step 6: Run the Wearable Agent App

```powershell
# Navigate to the Flutter app directory
cd "C:\Users\marco\OneDrive - Radboud Universiteit\Desktop\FITBIT AGENT\flutter_app"

# Install dependencies
flutter pub get

# List connected devices
flutter devices

# Run on Android device
flutter run
```

## Quick Commands Reference

```powershell
# Check setup status
flutter doctor

# List available devices (Android phone, emulator, Chrome)
flutter devices

# Run on specific device
flutter run -d <device-id>

# Run in release mode (faster, smaller)
flutter run --release

# Hot reload (press 'r' in terminal while app is running)
# Hot restart (press 'R')
# Quit (press 'q')
```

## Troubleshooting

### "No devices found"
- Ensure USB debugging is enabled on phone
- Try different USB cable (data cable, not charge-only)
- Install USB drivers: https://developer.android.com/studio/run/oem-usb

### "ADB not found"
```powershell
# Add Android SDK platform-tools to PATH
# Usually located at: C:\Users\<username>\AppData\Local\Android\Sdk\platform-tools
```

### "License not accepted"
```powershell
flutter doctor --android-licenses
```

## Alternative: Run in Browser (No Android Setup)
```powershell
cd flutter_app
flutter run -d chrome
```
Note: Some features (Notifications, certain sensors) won't work in browser.

---

## Next Steps After Installation

1. **Start the Python backend server first:**
   ```powershell
   cd "C:\Users\marco\OneDrive - Radboud Universiteit\Desktop\FITBIT AGENT"
   $env:PYTHONPATH="src"
   python -m wearable_agent.main serve
   # Server runs on http://localhost:8000
   ```

2. **Then run the Flutter app:**
   ```powershell
   # In a new terminal
   cd flutter_app
   flutter run
   ```

3. **Configure the app:**
   - Open Settings tab in the app
   - Set Server URL to your PC's IP (e.g., `http://192.168.1.100:8000`)
     - Find your PC IP: `ipconfig` → look for IPv4 Address
   - Set Participant ID (e.g., `P001`)
   - Tap "Save & Reconnect"

4. **Fitbit connection (optional):**
   - In Settings → tap "Connect Fitbit"
   - Login with Fitbit credentials
   - Backend will start syncing data automatically
