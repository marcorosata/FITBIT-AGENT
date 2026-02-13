# Wearable Agent Framework

> Agent-based software framework for collecting and analysing data from wearable devices in behavioral, health, and social research.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)]()
[![License: Radboud University](https://img.shields.io/badge/License-Radboud%20University-red.svg)]()

---

## Overview

**Wearable Agent** is an open-source research framework that combines **agentic AI** (LangChain / LangGraph) with **IoT data collection** from consumer wearable devices. It is designed for researchers who need to:

- Collect longitudinal, ecologically valid physiological data from study participants.
- Monitor incoming sensor streams in real time against study-specific rules.
- Receive automated notifications when anomalies or deviations are detected.
- Export clean, reproducible datasets for analysis and publication.

The initial implementation supports **Fitbit** devices; the architecture is extensible to Apple Watch, Garmin, and other wearables.

---

## Architecture

```
Wearable Devices
    │
    ▼
┌──────────────────┐     ┌────────────────────┐
│  Data Collectors  │────▶│  Streaming Pipeline │
│  (Fitbit, …)     │     │  (async queue)      │
└──────────────────┘     └────────┬───────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼              ▼
              ┌──────────┐ ┌──────────┐ ┌──────────────┐
              │ Storage  │ │  Agent   │ │  Monitoring  │
              │ (SQLite/ │ │ (LangChain│ │  Rules       │
              │  Postgres)│ │  ReAct)  │ │  Engine      │
              └──────────┘ └──────────┘ └──────┬───────┘
                    │                          │
                    ▼                          ▼
              ┌──────────┐           ┌──────────────────┐
              │ Research │           │  Notifications   │
              │ Export   │           │  (webhook/email) │
              └──────────┘           └──────────────────┘
                    │
                    ▼
              ┌──────────┐
              │ FastAPI  │
              │ REST API │
              └──────────┘
```

### Key Components

| Component | Description |
|---|---|
| **Collectors** | Device-specific adapters (Fitbit OAuth2 API). Pluggable via a registry. |
| **Streaming Pipeline** | Async queue that decouples ingestion from processing. |
| **Rule Engine** | Declarative threshold rules evaluated on every reading. |
| **LangChain Agent** | LLM-powered ReAct agent for contextual analysis and free-form queries. |
| **Storage** | Async SQLAlchemy (SQLite dev / PostgreSQL prod) with repository pattern. |
| **Notifications** | Multi-channel: structured log, webhook, email (extensible). |
| **Research Utilities** | CSV/JSON export, pandas DataFrames, summary statistics, resampling. |
| **FastAPI Server** | REST API + WebSocket for data ingestion, querying, and real-time streaming. |

---

## Quick Start

### 1. Clone & install

```bash
git clone <repo-url>
cd "FITBIT AGENT"
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -e ".[dev,analysis]"
```

### 2. Configure

```bash
copy .env.example .env
# Edit .env — add your OPENAI_API_KEY and FITBIT credentials.
```

### 3. Initialise database

```bash
wearable-agent init-db
```

### 4. Start the server

```bash
wearable-agent serve
# Server runs at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

### 5. Ingest data

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "participant_id": "P001",
    "device_type": "fitbit",
    "metric_type": "heart_rate",
    "value": 85.0,
    "unit": "bpm"
  }'
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/ingest` | Ingest a single sensor reading |
| `POST` | `/ingest/batch` | Ingest multiple readings |
| `GET` | `/readings/{participant_id}` | Query readings by participant & metric |
| `GET` | `/alerts/{participant_id}` | Retrieve alerts for a participant |
| `POST` | `/analyse` | Free-form LLM agent query |
| `GET` | `/evaluate/{participant_id}` | Structured agent evaluation |
| `GET` | `/rules` | List monitoring rules |
| `POST` | `/rules` | Add a monitoring rule |
| `DELETE` | `/rules/{rule_id}` | Remove a rule |
| `WS` | `/ws/stream` | Real-time WebSocket feed |

---

## Monitoring Rules

Rules are declarative Python expressions evaluated against each reading's `value`:

```json
{
  "metric_type": "heart_rate",
  "condition": "value > 100 or value < 50",
  "severity": "warning",
  "message_template": "Heart rate {value} bpm outside range [50, 100]."
}
```

Default heart-rate rules are loaded automatically. Add study-specific rules via the `/rules` endpoint or programmatically.

---

## Running Tests

```bash
pytest --cov=wearable_agent -v
```

---

## Project Structure

```
src/wearable_agent/
├── __init__.py
├── config.py              # Pydantic settings (env / .env)
├── logging.py             # Structured logging (structlog)
├── main.py                # CLI entrypoint
├── models.py              # Shared Pydantic models
├── agent/
│   ├── core.py            # LangGraph ReAct agent
│   ├── prompts.py         # System & evaluation prompts
│   └── tools.py           # LangChain tools (DB queries)
├── api/
│   └── server.py          # FastAPI application
├── collectors/
│   ├── base.py            # Abstract collector
│   ├── fitbit.py          # Fitbit API collector
│   └── registry.py        # Device registry
├── monitors/
│   ├── heart_rate.py      # HR-specific defaults
│   └── rules.py           # Generic rule engine
├── notifications/
│   └── handlers.py        # Log, webhook, email handlers
├── research/
│   ├── analysis.py        # Pandas helpers
│   └── export.py          # CSV / JSON export
└── streaming/
    └── pipeline.py        # Async data pipeline
```

---

## Extending the Framework

### Adding a new device collector

1. Create `src/wearable_agent/collectors/garmin.py` implementing `BaseCollector`.
2. Register it in `registry.py`:
   ```python
   register_collector(DeviceType.GARMIN, GarminCollector)
   ```

### Adding a new metric type

1. Add the enum value to `MetricType` in `models.py`.
2. Add parser logic in the relevant collector.
3. Create monitoring rules for the new metric.

---

## License

Proprietary — Radboud University. All rights reserved.

---

## Acknowledgements

Developed at **Radboud University** as part of research into agentic AI for IoT-based behavioral and health studies.
