"""
Galaxy SIA Notification Provider - Base Class

This module defines the abstract base class that all notification provider
plugins must implement.

To create a new provider:
  1. Create a new file in the providers/ directory (e.g. providers/myprovider.py)
  2. Import and subclass NotificationProvider
  3. Set the class attribute provider_name to a unique lowercase string
  4. Implement from_config(), send() and the name property

The provider will be auto-discovered at startup - no registration needed.
See providers/README.md for full documentation.
"""

from abc import ABC, abstractmethod
import logging

log = logging.getLogger(__name__)


class NotificationProvider(ABC):
    """
    Abstract base class for notification provider plugins.

    All providers must:
    - Define a class attribute 'provider_name' (lowercase string)
    - Implement from_config() to validate and instantiate from raw config dict
    - Implement send() to deliver the notification
    """

    # Each subclass must define this as a class attribute
    # Example: provider_name = 'ntfy'
    provider_name: str

    @classmethod
    @abstractmethod
    def from_config(cls, account_number: str, provider_config: dict) -> 'NotificationProvider':
        """
        Validate the provider config and return an instance of the provider.

        Called once per account at startup. Should raise ValueError with a
        descriptive message if the configuration is invalid or incomplete.
        This is the right place to check for required keys, valid URLs,
        and available dependencies.

        Args:
            account_number: The account number this provider is for (for logging).
            provider_config: Raw key-value dict from the account section of
                             sia-server.conf. Keys are always lowercase.

        Returns:
            A configured instance of the provider ready to send notifications.

        Raises:
            ValueError: If the configuration is invalid or incomplete.
        """
        ...

    @abstractmethod
    def send(self, account: str, message: str, priority: int) -> bool | None:
        """
        Send a notification.

        Args:
            account:  The account number this notification belongs to.
            message:  Notification message body.
            priority: Integer priority 1-5 (1=lowest, 5=highest/urgent).
        """
        ...

    @property
    def name(self) -> str:
        """
        Human-readable provider name for logging.
        Defaults to provider_name but can be overridden.
        """
        return self.provider_name
