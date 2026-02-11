# Wearable Agent — Flutter App

Participant-facing mobile companion for the Wearable Agent research framework.

## Features

- **Dashboard** — live metric cards (heart rate, steps, SpO₂, HRV, sleep, calories)
- **Alerts** — severity-coded notification feed
- **AI Chat** — free-form questions answered by the LangGraph agent
- **Live Stream** — real-time WebSocket feed of incoming sensor data
- **Fitbit Login** — in-app OAuth 2.0 authorization flow

## Setup

```bash
cd flutter_app
flutter pub get
flutter run
```

On first launch, tap ⚙️ to set your backend URL (e.g. `http://10.0.2.2:8000` for Android emulator, `http://localhost:8000` for web/iOS simulator, or your server IP).

## Backend

This app connects to the FastAPI server in the parent workspace. Start it with:

```bash
cd ..
wearable-agent serve
```
