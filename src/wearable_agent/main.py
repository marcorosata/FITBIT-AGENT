"""Application entrypoint — start the API server or run one-off commands."""

from __future__ import annotations

import argparse
import asyncio
import sys

import uvicorn

from wearable_agent.config import get_settings
from wearable_agent.logger import setup_logging


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="wearable-agent",
        description="Agent-based wearable data collection framework.",
    )
    sub = parser.add_subparsers(dest="command")

    # ── serve ─────────────────────────────────────────────────
    serve_parser = sub.add_parser("serve", help="Start the API server.")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--reload", action="store_true")

    # ── init-db ───────────────────────────────────────────────
    sub.add_parser("init-db", help="Create database tables.")

    args = parser.parse_args(argv)
    settings = get_settings()
    setup_logging(settings.agent_log_level)

    if args.command == "serve":
        uvicorn.run(
            "wearable_agent.api.server:app",
            host=args.host or settings.api_host,
            port=args.port or settings.api_port,
            reload=args.reload,
        )
    elif args.command == "init-db":
        from wearable_agent.storage.database import init_db

        asyncio.run(init_db())
        print("Database tables created.")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
