# 🏥 Wearable Agent Framework

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Flutter](https://img.shields.io/badge/Flutter-3.16+-02569B.svg)](https://flutter.dev)
[![Tests](https://img.shields.io/badge/tests-46%20passed-success)](tests/)
[![License](https://img.shields.io/badge/license-Radboud%20University-red.svg)]()

**Agent-based framework for wearable data collection, real-time monitoring, and AI-powered health analysis.** Built for research studies combining physiological signals (Fitbit, wearables) with intelligent alerting and affective state inference.

---

## 🎯 Features

### 🔄 **Real-Time Data Pipeline**
- WebSocket streaming for live sensor readings
- Async collection from Fitbit Web API (14 metrics)
- OAuth 2.0 token management with auto-refresh
- Rate limiting (150 req/hr) and error handling

### 🤖 **AI Agent (LangGraph + OpenAI)**
- ReAct agent with database tools
- Natural language queries over health data
- Contextual analysis and recommendations
- Configurable prompts and tool integration

### 📊 **Monitoring & Alerts**
- Rule-based evaluation engine (Python expressions)
- Multi-channel notifications (log, webhook, email)
- Severity levels (info/warning/critical)
- 10 pre-configured physiological rules

### 🧠 **Affective State Inference**
- Arousal, valence, stress, emotion prediction
- Feature extraction from HRV, activity, sleep
- EMA (Ecological Momentary Assessment) integration
- Baseline tracking with EWMA smoothing

### 📱 **Flutter Mobile App**
- Dashboard with 14 metric types & live charts
- Alert feed with severity badges
- AI chat interface
- WebSocket live stream viewer
- Fitbit OAuth login flow
- Settings & rule management

---

## 🚀 Quick Start

### Backend (Python)

```bash
# Clone repository
git clone https://github.com/marcorosata/FITBIT-AGENT.git
cd FITBIT-AGENT

# Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -e .

# Initialize database
python -m wearable_agent.main init-db

# Start server
python -m wearable_agent.main serve
# → API runs on http://localhost:8000
```

### Flutter App

```bash
cd flutter_app

# Install dependencies
flutter pub get

# Run on connected device
flutter run

# Or run in browser
flutter run -d chrome
```

---

## 📦 Installation

### System Requirements
- **Python**: 3.11 or higher
- **Flutter**: 3.16+ (for mobile app)
- **SQLite**: Built-in (aiosqlite)
- **Optional**: OpenAI API key (for AI agent)

### Python Dependencies
```bash
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sqlalchemy>=2.0.0
langchain-openai
langgraph
httpx
structlog
pydantic-settings
aiosqlite
```

**Install all:**
```bash
pip install -e .
```

---

## ⚙️ Configuration

Create `.env` file in project root:

```env
# AI Agent
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Fitbit OAuth
FITBIT_CLIENT_ID=your_client_id
FITBIT_CLIENT_SECRET=your_client_secret
FITBIT_REDIRECT_URI=http://localhost:8000/auth/fitbit/callback
FITBIT_ACCESS_TOKEN=
FITBIT_REFRESH_TOKEN=

# Server
API_HOST=0.0.0.0
API_PORT=8000
DATABASE_URL=sqlite+aiosqlite:///data/wearable_agent.db

# Notifications
WEBHOOK_URL=https://your-webhook.com/alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@email.com
SMTP_PASSWORD=your_password
NOTIFICATION_EMAIL_FROM=alerts@yourdomain.com
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   FastAPI Server                        │
│  ┌────────────────────────────────────────────────┐    │
│  │          REST API + WebSocket                   │    │
│  │  /health /ingest /readings /alerts /analyse     │    │
│  └────────────────────────────────────────────────┘    │
│           ↓                    ↓                         │
│  ┌─────────────────┐  ┌─────────────────────────┐      │
│  │ StreamPipeline  │  │   WearableAgent         │      │
│  │  (async queue)  │  │ ┌─────────────────────┐ │      │
│  └─────────────────┘  │ │  RuleEngine         │ │      │
│           ↓            │ │  (Python eval)      │ │      │
│  ┌─────────────────┐  │ └─────────────────────┘ │      │
│  │  ReadingRepo    │  │ ┌─────────────────────┐ │      │
│  │  AlertRepo      │←─┤ │  LangGraph ReAct    │ │      │
│  │  (SQLAlchemy)   │  │ │  (OpenAI + Tools)   │ │      │
│  └─────────────────┘  │ └─────────────────────┘ │      │
│           ↓            └───────────┬─────────────┘      │
│  ┌─────────────────┐              ↓                     │
│  │   SQLite DB     │  ┌─────────────────────────┐      │
│  └─────────────────┘  │ NotificationDispatcher  │      │
│                        │  (log/webhook/email)    │      │
│                        └─────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
              ↑                            ↓
     ┌────────────────┐         ┌──────────────────┐
     │ FitbitCollector│         │  Flutter App     │
     │  (OAuth 2.0)   │         │  (5 screens)     │
     └────────────────┘         └──────────────────┘
```

---

## 📡 API Endpoints

### Core
- `GET /health` - Health check
- `POST /ingest` - Ingest sensor reading
- `GET /readings/{pid}?metric=heart_rate&limit=50` - Query readings
- `GET /alerts/{pid}` - Get participant alerts
- `GET /api/stats` - System statistics

### Agent
- `POST /analyse` - Chat with AI agent
- `POST /evaluate/{pid}?metric=heart_rate&hours=24` - Contextual evaluation

### Rules
- `GET /rules` - List monitoring rules
- `POST /rules` - Add new rule
- `DELETE /rules/{rule_id}` - Remove rule

### Affect Inference
- `POST /affect/{pid}` - Run affective state inference
- `GET /affect/{pid}` - Get latest affective state
- `POST /ema` - Submit EMA self-report

### WebSocket
- `WS /ws/stream` - Real-time reading stream

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=wearable_agent --cov-report=html

# Specific test file
pytest tests/test_api.py -v
```

**Test suite:** 46 tests across 5 modules
- ✅ `test_affect.py` - Feature extraction, baselines, inference
- ✅ `test_api.py` - FastAPI endpoints
- ✅ `test_collectors.py` - Fitbit collector, registry
- ✅ `test_monitors.py` - Rule engine evaluation
- ✅ `test_pipeline.py` - Streaming pipeline

---

## 📱 Flutter App Screens

1. **Dashboard** - Metric cards, line charts, stats summary
2. **Alerts** - Severity-colored alert feed
3. **AI Chat** - Conversational interface with LangGraph agent
4. **Live Stream** - WebSocket real-time readings
5. **Settings** - Server config, participant ID, Fitbit OAuth, rules viewer

---

## 🚢 Deployment

### Railway (Recommended)

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)

1. **Push to GitHub:**
   ```bash
   git init
   git add.
   git commit -m "Initial commit: Wearable Agent Framework"
   git remote add origin https://github.com/marcorosata/FITBIT-AGENT.git
   git push -u origin main
   ```

2. **Deploy to Railway:**
   - Visit [railway.app](https://railway.app)
   - Click "New Project" → "Deploy from GitHub repo"
   - Select `FITBIT-AGENT` repository
   - Railway auto-detects `railway.json` and deploys

3. **Set environment variables:**
   ```
   OPENAI_API_KEY=sk-...
   FITBIT_CLIENT_ID=...
   FITBIT_CLIENT_SECRET=...
   DATABASE_URL=postgresql://... (optional: use Railway Postgres)
   ```

4. **Access your app:**
   - Railway provides a public URL: `https://your-app.railway.app`
   - Update Flutter app Settings with this URL

### Docker (Alternative)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
EXPOSE 8000
CMD ["python", "-m", "wearable_agent.main", "serve"]
```

```bash
docker build -t wearable-agent .
docker run -p 8000:8000 --env-file .env wearable-agent
```

---

## 🔧 Development

### Project Structure
```
FITBIT-AGENT/
├── src/wearable_agent/
│   ├── agent/           # LangGraph ReAct agent
│   ├── affect/          # Affective state inference
│   ├── api/             # FastAPI server
│   ├── collectors/      # Fitbit & device collectors
│   ├── monitors/        # Rule engine & monitors
│   ├── notifications/   # Alert dispatchers
│   ├── research/        # Data export & analysis
│   ├── storage/         # SQLAlchemy repositories
│   ├── streaming/       # Async pipeline
│   └── ui/              # HTML admin/user dashboards
├── flutter_app/         # Flutter mobile app
│   ├── lib/
│   │   ├── screens/     # 5 app screens
│   │   ├── models.dart  # Data models
│   │   ├── api_client.dart
│   │   └── app_state.dart
│   └── pubspec.yaml
├── tests/               # Pytest test suite
├── docs/                # Architecture docs
├── pyproject.toml       # Python project config
├── railway.json         # Railway deployment
└── Procfile             # Process definitions
```

### Key Design Patterns
- **Async-first**: All I/O uses `async`/`await`
- **Dependency Injection**: Services injected via constructors
- **Repository Pattern**: DB access abstracted
- **Factory Functions**: `create_tools()`, `create_dispatcher()`
- **Type Safety**: Full `mypy` strict mode compliance

### Code Quality
```bash
# Linting
ruff check src/

# Type checking
mypy src/

# Auto-formatting
ruff format src/
```

---

## 📊 Supported Metrics

| Metric | Source | Unit | Freq |
|--------|--------|------|------|
| Heart Rate | Fitbit | bpm | 1s |
| Steps | Fitbit | count | 1min |
| SpO2 | Fitbit | % | varies |
| HRV (RMSSD) | Fitbit | ms | daily |
| Sleep | Fitbit | stages | nightly |
| Skin Temperature | Fitbit | °C | nightly |
| Breathing Rate | Fitbit | breaths/min | varies |
| Calories | Fitbit | kcal | 1min |
| Distance | Fitbit | km | 1min |
| Floors | Fitbit | count | 1min |
| Body Weight | Fitbit | kg | manual |
| Body Fat % | Fitbit | % | manual |
| VO2 Max | Fitbit | ml/kg/min | varies |
| Active Zone Minutes | Fitbit | min | daily |

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

Proprietary — Radboud University. All rights reserved.

---

## 🙏 Acknowledgments

- **LangChain/LangGraph** - Agent framework
- **FastAPI** - Modern Python web framework
- **Fitbit Web API** - Health data access
- **Flutter** - Cross-platform mobile framework
- **SQLAlchemy** - Python ORM
- **Structlog** - Structured logging

---

## 📞 Contact

**Marco Rosata** - [@marcorosata](https://github.com/marcorosata)

**Project Link:** https://github.com/marcorosata/FITBIT-AGENT

---

**⭐ Star this repo if you find it helpful!**
