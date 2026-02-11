"""Core agent — LangGraph ReAct agent for autonomous wearable monitoring."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from wearable_agent.agent.prompts import EVALUATION_PROMPT, SYSTEM_PROMPT
from wearable_agent.agent.tools import create_tools
from wearable_agent.config import get_settings
from wearable_agent.models import Alert, MetricType, SensorReading
from wearable_agent.monitors.rules import RuleEngine
from wearable_agent.notifications.handlers import NotificationDispatcher
from wearable_agent.storage.repository import AlertRepository, ReadingRepository

logger = structlog.get_logger(__name__)


class WearableAgent:
    """Autonomous monitoring agent that combines rule-based evaluation with
    LLM-powered reasoning.

    The agent operates in two modes:

    1. **Rule-based** (fast path) — every incoming reading is checked against
       ``MonitoringRule`` instances via the :class:`RuleEngine`.  Alerts are
       fired immediately.
    2. **LLM-assisted** (deep path) — on demand (or periodically), the
       LangGraph ReAct agent is invoked to perform richer contextual
       analysis using the database tools.
    """

    def __init__(
        self,
        rule_engine: RuleEngine,
        dispatcher: NotificationDispatcher,
        reading_repo: ReadingRepository | None = None,
        alert_repo: AlertRepository | None = None,
        affect_pipeline: Any | None = None,
    ) -> None:
        self._rule_engine = rule_engine
        self._dispatcher = dispatcher
        self._reading_repo = reading_repo or ReadingRepository()
        self._alert_repo = alert_repo or AlertRepository()
        self._affect_pipeline = affect_pipeline

        # Wire tool-level repositories
        self._tools = create_tools(
            self._reading_repo, self._alert_repo, affect_pipeline=affect_pipeline
        )

        # Build the LangGraph ReAct agent (lazy — created on first LLM call)
        self._agent_executor: Any | None = None

    # ── Lazy LLM initialisation ───────────────────────────────

    def _ensure_agent(self) -> Any:
        if self._agent_executor is None:
            settings = get_settings()
            llm = ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=0,
            )
            self._agent_executor = create_react_agent(
                model=llm,
                tools=self._tools,
                prompt=SYSTEM_PROMPT,
            )
            logger.info("wearable_agent.llm_initialised", model=settings.openai_model)
        return self._agent_executor

    # ── Fast-path: rule evaluation ────────────────────────────

    async def process_reading(self, reading: SensorReading) -> list[Alert]:
        """Evaluate a single reading against all rules.

        Fired alerts are persisted and dispatched to notification channels.
        """
        alerts = self._rule_engine.evaluate(reading)
        for alert in alerts:
            await self._alert_repo.save(alert)
            await self._dispatcher.dispatch(alert)
        return alerts

    async def process_batch(self, readings: list[SensorReading]) -> list[Alert]:
        """Evaluate a batch of readings."""
        all_alerts: list[Alert] = []
        for reading in readings:
            all_alerts.extend(await self.process_reading(reading))
        return all_alerts

    # ── Deep-path: LLM analysis ───────────────────────────────

    async def analyse(self, query: str) -> str:
        """Invoke the LLM agent with a free-form research query.

        The agent has access to database tools and can retrieve readings,
        compute statistics, and reason about anomalies.
        """
        agent = self._ensure_agent()
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=query)]}
        )
        # The last AI message contains the answer.
        return result["messages"][-1].content

    async def evaluate_participant(
        self,
        participant_id: str,
        metric_type: str,
        hours_back: int = 24,
    ) -> str:
        """Run a structured evaluation for a participant over a time window."""
        rows = await self._reading_repo.get_latest(
            participant_id,
            metric_type=MetricType(metric_type),
            limit=100,
        )
        values = ", ".join(f"{r.value}" for r in rows[:20])
        rules_text = "\n".join(
            f"- {r.condition} → {r.severity.value}" for r in self._rule_engine.list_rules()
        )

        prompt = EVALUATION_PROMPT.format(
            participant_id=participant_id,
            metric_type=metric_type,
            time_start="(auto)",
            time_end="(now)",
            count=len(rows),
            values=values or "(none)",
            rules=rules_text or "(no rules configured)",
        )
        return await self.analyse(prompt)
