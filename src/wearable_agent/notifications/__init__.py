"""Notification sub-package — multi-channel alert delivery."""

from wearable_agent.notifications.handlers import (
    NotificationDispatcher,
    NotificationHandler,
    create_dispatcher,
)

__all__ = ["NotificationDispatcher", "NotificationHandler", "create_dispatcher"]
