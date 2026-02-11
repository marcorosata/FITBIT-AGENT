# Architecture — Wearable Agent Framework

## Design Principles

1. **Research-first** — The framework is designed for academic research, not consumer health apps. Data collection is protocol-driven, context-aware, and privacy-respecting.

2. **Separation of concerns** — Each layer (collection, streaming, monitoring, storage, notification, analysis) is independent and can be tested, replaced, or extended without affecting others.

3. **Dual intelligence** — Fast rule-based evaluation handles real-time threshold monitoring, while an LLM agent provides deeper contextual analysis when needed.

4. **Async-native** — All I/O-bound operations (API calls, database, streaming) use Python `asyncio` for high throughput with minimal resource usage.

5. **Extensibility** — New device types, metric types, notification channels, and analysis methods can be added through well-defined interfaces.

---

## Data Flow

```
[Wearable Device]
       │
       │  OAuth2 / API poll
       ▼
[Collector]  ──fetch()──▶  list[SensorReading]
       │
       │  publish()
       ▼
[StreamPipeline]  ──async queue──▶  [Consumer callbacks]
       │                                    │
       ├───────────────────────┐            │
       ▼                       ▼            ▼
[ReadingRepository]     [RuleEngine]   [WearableAgent]
   .save()              .evaluate()     .process_reading()
       │                    │                │
       │                    ▼                │
       │              [Alert]                │
       │                    │                │
       │                    ▼                │
       │         [NotificationDispatcher]    │
       │              .dispatch()            │
       │                    │                │
       │         ┌──────────┼──────────┐     │
       │         ▼          ▼          ▼     │
       │     [Log]    [Webhook]   [Email]    │
       │                                     │
       ▼                                     ▼
[SQLite / PostgreSQL]              [LLM Analysis]
       │                          (on-demand)
       ▼
[Research Export]
  CSV / JSON / DataFrame
```

---

## Component Details

### Collectors (`collectors/`)

- **`BaseCollector`** — Abstract interface: `authenticate()`, `fetch()`, `stream()`, `close()`
- **`FitbitCollector`** — Implements Fitbit Web API v1.2 with OAuth2 bearer token
- **`CollectorRegistry`** — Maps `DeviceType` → collector class; enables runtime discovery

### Streaming (`streaming/`)

- **`StreamPipeline`** — `asyncio.Queue`-backed pub/sub within the process
- Consumers are registered callbacks; the pipeline decouples producers from processing
- Backpressure via bounded queue (default 10,000 items)

### Monitoring (`monitors/`)

- **`RuleEngine`** — Evaluates Python expressions in a sandboxed namespace (`value` only)
- **`heart_rate`** — Pre-configured default rules for HR monitoring

### Agent (`agent/`)

- **`WearableAgent`** — Orchestrator combining rule engine + LLM
- **`tools`** — LangChain `@tool`-decorated functions exposing DB queries to the LLM
- **`prompts`** — System prompt (research assistant persona) + evaluation template
- Built on **LangGraph** `create_react_agent` for ReAct-style reasoning

### Storage (`storage/`)

- **SQLAlchemy 2.0** async ORM with `aiosqlite` (dev) / `asyncpg` (prod)
- **Repository pattern** for clean separation between ORM and business logic
- Tables: `sensor_readings`, `alerts`, `studies`

### API (`api/`)

- **FastAPI** with async lifespan management
- REST endpoints for CRUD + ingestion
- WebSocket endpoint for real-time data streaming
- Auto-generated OpenAPI docs at `/docs`

### Research (`research/`)

- **`export`** — CSV and JSON export with clean column naming
- **`analysis`** — `pandas` DataFrame conversion, summary stats, resampling

---

## Security Considerations

- API secret key for session signing
- Fitbit OAuth2 tokens stored server-side (never exposed to participants)
- Rule conditions are `eval()`-ed in a restricted namespace (no builtins)
- Database credentials via environment variables, never in code

---

## Future Work

- [ ] Alembic migration scripts for schema evolution
- [ ] Apple Watch (HealthKit via proxy) and Garmin Connect collectors
- [ ] Multi-modal data support (accelerometer, GPS context)
- [ ] Participant consent management module
- [ ] Dashboard UI (React / Next.js)
- [ ] Containerised deployment (Docker Compose)
- [ ] Study protocol DSL for no-code rule configuration
