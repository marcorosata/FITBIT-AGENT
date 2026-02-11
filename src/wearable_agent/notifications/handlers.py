"""Notification handlers — webhook, email, and log-based delivery.

Architecture
~~~~~~~~~~~~
* **NotificationHandler** — abstract base for delivery channels.
* **LogHandler / WebhookHandler / EmailHandler** — concrete channels.
* **NotificationDispatcher** — fan-out with error-isolation and results.
* **create_dispatcher()** — factory that wires handlers from settings.

Adding a new channel
~~~~~~~~~~~~~~~~~~~~
1. Subclass ``NotificationHandler``.
2. Implement ``async send(alert) -> bool``.
3. Optionally set ``name`` for debug output.
4. Register via ``dispatcher.add_handler(...)`` or add to the factory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    from wearable_agent.config import Settings
    from wearable_agent.models import Alert

logger = structlog.get_logger(__name__)


# ── Dispatch result ───────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Outcome summary for a single ``dispatch()`` call."""

    alert_id: str | None
    sent: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return len(self.failed) == 0


# ── Abstract handler ──────────────────────────────────────────


class NotificationHandler(ABC):
    """Contract for alert delivery channels.

    Subclasses must implement :meth:`send`. They may optionally override
    :attr:`name` for logging/debug purposes and :meth:`should_handle` to
    filter alerts (e.g. only critical ones).
    """

    name: str = "base"

    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """Deliver an alert.  Return ``True`` on success."""

    def should_handle(self, alert: Alert) -> bool:  # noqa: ARG002
        """Return ``False`` to skip this alert (default: handle all)."""
        return True


# ── Concrete handlers ────────────────────────────────────────


class LogHandler(NotificationHandler):
    """Write alerts to the structured log (always enabled)."""

    name = "log"

    async def send(self, alert: Alert) -> bool:
        logger.info(
            "notification.log",
            participant=alert.participant_id,
            severity=alert.severity.value,
            metric=alert.metric_type.value,
            message=alert.message,
            value=alert.value,
        )
        return True


class WebhookHandler(NotificationHandler):
    """POST alert JSON to an external webhook URL."""

    name = "webhook"

    def __init__(self, url: str, *, timeout: float = 10.0) -> None:
        self._url = url
        self._timeout = timeout

    async def send(self, alert: Alert) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    self._url, json=alert.model_dump(mode="json"),
                )
                resp.raise_for_status()
            logger.info("notification.webhook_sent", url=self._url, alert_id=alert.id)
            return True
        except Exception as exc:
            logger.error("notification.webhook_failed", url=self._url, error=str(exc))
            return False


class EmailHandler(NotificationHandler):
    """Send alert emails via SMTP (async-compatible stub).

    Swap in *aiosmtplib* for real async sending when the dependency
    is added.
    """

    name = "email"

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_addr: str,
        to_addr: str,
    ) -> None:
        self._host = smtp_host
        self._port = smtp_port
        self._user = username
        self._password = password
        self._from = from_addr
        self._to = to_addr

    async def send(self, alert: Alert) -> bool:
        # Placeholder — swap in aiosmtplib for real async sending.
        logger.info(
            "notification.email_stub",
            to=self._to,
            subject=f"[{alert.severity.value.upper()}] {alert.message[:80]}",
        )
        return True


# ── Dispatcher ────────────────────────────────────────────────


class NotificationDispatcher:
    """Fan-out alerts to registered handlers with error isolation.

    Each handler is invoked independently — a failure in one channel
    never blocks delivery to the others.
    """

    def __init__(self, *, handlers: list[NotificationHandler] | None = None) -> None:
        self._handlers: list[NotificationHandler] = handlers or [LogHandler()]

    # ── Handler management ────────────────────────────────────

    def add_handler(self, handler: NotificationHandler) -> None:
        self._handlers.append(handler)

    def remove_handler(self, name: str) -> bool:
        """Remove the first handler matching *name*. Return ``True`` if found."""
        for i, h in enumerate(self._handlers):
            if h.name == name:
                self._handlers.pop(i)
                return True
        return False

    @property
    def handler_names(self) -> list[str]:
        """List registered handler names (useful for debugging / tests)."""
        return [h.name for h in self._handlers]

    # ── Dispatch ──────────────────────────────────────────────

    async def dispatch(self, alert: Alert) -> DispatchResult:
        """Send *alert* to every handler, collecting per-handler outcomes.

        A handler that raises is caught, logged, and marked as failed so
        remaining handlers still execute.
        """
        sent: list[str] = []
        failed: list[str] = []

        for handler in self._handlers:
            if not handler.should_handle(alert):
                continue
            try:
                ok = await handler.send(alert)
                (sent if ok else failed).append(handler.name)
            except Exception:
                logger.exception(
                    "notification.handler_error",
                    handler=handler.name,
                    alert_id=alert.id,
                )
                failed.append(handler.name)

        result = DispatchResult(alert_id=alert.id, sent=sent, failed=failed)
        if result.failed:
            logger.warning(
                "notification.partial_failure",
                alert_id=alert.id,
                failed=result.failed,
            )
        return result

    async def dispatch_many(self, alerts: list[Alert]) -> list[DispatchResult]:
        """Dispatch a batch of alerts, returning per-alert results."""
        return [await self.dispatch(a) for a in alerts]


# ── Factory ───────────────────────────────────────────────────


def create_dispatcher(settings: Settings) -> NotificationDispatcher:
    """Build a :class:`NotificationDispatcher` wired from application settings.

    * **LogHandler** is always registered.
    * **WebhookHandler** is added when ``settings.webhook_url`` is non-empty.
    * **EmailHandler** is added when ``settings.smtp_host`` is non-empty.
    """
    dispatcher = NotificationDispatcher()

    if settings.webhook_url:
        dispatcher.add_handler(WebhookHandler(settings.webhook_url))

    if settings.smtp_host:
        dispatcher.add_handler(
            EmailHandler(
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                from_addr=settings.notification_email_from,
                to_addr=settings.notification_email_from,  # default to self
            ),
        )

    return dispatcher
