# Copilot Instructions for Wearable Agent Framework

## Project Context
**Framework**: Async Python 3.11+ for wearable data collection & analysis.
**Core Stack**: FastAPI, LangGraph, SQLAlchemy (Async), Pydantic, Fitbit API.
**Architecture**: Service-layered (Collectors -> Pipeline -> Agent/Monitors -> Storage).

## 1. Architecture & Patterns
- **Async First**: Use `async`/`await` for all I/O (DB, API, Streaming). Use `asyncio.run()` only at entrypoints.
- **Dependency Injection**: 
  - Avoid global state. Inject repositories and services into classes/functions.
  - *Example*: Use `create_tools(reading_repo, alert_repo)` factory in `agent/tools.py` instead of global tool lists.
- **Repository Pattern**: 
  - All DB access goes through `src/wearable_agent/storage/repository.py`.
  - Do NOT write raw SQL or direct ORM queries in business logic or API handlers.
- **Configuration**: 
  - Use `wearable_agent.config.get_settings()`. It is cached via `@lru_cache`.
  - Settings are read from `.env` via `pydantic-settings`.

## 2. Coding Standards
- **Logging**: Use `structlog`. **CRITICAL**: Never name files `logging.py` to avoid shadowing stdlib.
- **Type Safety**: Use `mypy` strict mode. All public functions must have type hints.
- **Imports**: 
  - Use `from __future__ import annotations`.
  - Avoid circular imports by using `TYPE_CHECKING` blocks for type-only dependencies.
  - Fix circular imports by refactoring into smaller modules or specialized files (e.g., `logger.py`).

## 3. Critical Workflows
- **Running the App**:
  ```bash
  $env:PYTHONPATH="src"; python -m wearable_agent.main serve
  # OR if installed via pip -e .
  wearable-agent serve
  ```
- **Database Init**: `wearable-agent init-db` (Creates SQLite tables in `data/`).
- **Testing**: 
  - Use `pytest`. Async mode is auto-configured in `pyproject.toml`.
  - Mock repositories when testing agents/logic to avoid DB side effects.
- **Linting**: `ruff check` and `mypy` are the sources of truth.

## 4. Key Components
- **Agent (`src/wearable_agent/agent/`)**: 
  - Uses `LangGraph` ReAct agent.
  - Tools are lazily initialized per instance to allow proper repo injection.
- **Pipeline (`src/wearable_agent/streaming/`)**:
  - `StreamPipeline` is an in-memory `asyncio.Queue` publisher.
- **Monitors (`src/wearable_agent/monitors/`)**:
  - `RuleEngine` evaluates strict Python expressions safely.

## 5. Common Pitfalls
- **Global Tools**: Do not define LangChain tools as global variables if they depend on DB state. Use a factory.
- **Blocking Code**: Blocking calls in FastAPI/AsyncIO loop will freeze the streaming pipeline.
- **Path Handling**: Use `pathlib` relative to `_PROJECT_ROOT` in `config.py`.
