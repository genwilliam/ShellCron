"""Abstract notification provider interface."""

from abc import ABC, abstractmethod
from typing import Optional, Any


class NotificationProvider(ABC):
    """Interface for notification providers (email, webhook, push, etc.)."""

    @abstractmethod
    def send(
        self,
        task_name: str,
        status: str,
        summary: str,
        details: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Send a notification about a task execution.

        Args:
            task_name: Name of the task that ran.
            status: Execution status ('success', 'failed', etc.).
            summary: Short human-readable summary.
            details: Optional dict with additional context (logs, duration, etc.).

        Returns:
            True if notification was sent successfully, False otherwise.
        """
        ...

    @abstractmethod
    def configure(self, config: dict[str, Any]) -> bool:
        """Configure the provider with settings.

        Args:
            config: Provider-specific configuration dict.

        Returns:
            True if configuration is valid, False otherwise.
        """
        ...
