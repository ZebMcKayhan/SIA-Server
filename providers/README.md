# Notification Provider Plugins

This directory contains notification provider plugins for the Galaxy SIA Server.
Providers handle the delivery of notifications to various services.

## Built-in Providers

| Provider | File | Description |
|----------|------|-------------|
| `ntfy` | `ntfy.py` | Sends notifications via [ntfy.sh](https://ntfy.sh/) or a self-hosted ntfy server |
| `telegram` | `telegram.py` | Sends notifications via [Telegram](https://telegram.org/) or self hosted Bot API |

> **Note:** The `ntfy` provider is the primary provider and is fully documented with
> examples in `sia-server.conf`. For other providers, see the docstring at the top of
> the provider file for configuration keys and setup instructions.

## How Providers Work

Providers are **auto-discovered** at startup. Any `.py` file placed in this directory
that contains a subclass of `NotificationProvider` will be automatically loaded and
made available for use in `sia-server.conf`.

No changes to any other file are needed - just drop your provider file here.

## Creating a New Provider

### 1. Create the provider file

Create a new file in this directory, e.g. `providers/myprovider.py`:

```python
from providers.base import NotificationProvider
import logging

log = logging.getLogger(__name__)

class MyProvider(NotificationProvider):
    """Brief description of your provider."""

    provider_name = 'myprovider'  # must be unique, lowercase

    def __init__(self, site_name: str, my_setting: str):
        # Store validated config values.
        # Do NOT store account_number - it is passed to send() at runtime
        # as the actual account number received from the panel.
        self._site_name  = site_name   # None if not configured
        self._my_setting = my_setting

    @classmethod
    def from_config(cls, account_number: str, provider_config: dict) -> 'MyProvider':
        """
        Validate config and return a configured instance.
        Raises ValueError if config is invalid.
        provider_config keys are always lowercase.
        account_number is available for error messages and logging only.
        """
        # Validate required keys
        my_setting = provider_config.get('my_setting')
        if not my_setting:
            raise ValueError(f"[{account_number}] MY_SETTING is required but missing.")

        # site_name is None if not configured - use account number as fallback in send()
        site_name = provider_config.get('site_name')

        return cls(site_name, my_setting)

    def send(self, account: str, message: str, priority: int) -> bool | None:
        """
        Send a notification.

        Args:
            account:  The account number received from the panel (ground truth).
            message:  The formatted notification text.
            priority: Integer 1-5 (1=lowest, 5=highest/urgent).

        Returns:
            True  - sent successfully
            False - delivery failed, will be retried with backoff
            None  - configuration issue, skip silently without retry
        """
        # Use configured site_name for display if available, otherwise account number
        display_name = self._site_name if self._site_name else account

        try:
            # your delivery code here
            log.info("Sent notification for %s (%s) via myprovider.", display_name, account)
            return True
        except Exception as e:
            log.error("Failed to send notification for account %s: %s", account, e)
            return False

    @property
    def name(self) -> str:
        """
        Simple provider name used by notification.py in log messages.
        Keep this short - detailed delivery info belongs in send() logs.
        """
        return 'myprovider'
```

### 2. Configure an account to use your provider

In `sia-server.conf`, add `PROVIDER = myprovider` to the account section along
with any provider-specific settings:

```ini
[123456]
SITE_NAME = My Home
ENABLED = Yes
PROVIDER = myprovider
MY_SETTING = some_value
MY_OTHER_SETTING = another_value
```

### 3. That's it!

The provider will be discovered and loaded automatically at startup. If the
configuration is invalid, a warning will be logged and notifications will be
disabled for that account - the server will continue running normally.

## Provider Interface

### `provider_name` (class attribute)
A unique lowercase string identifying your provider. Used in `sia-server.conf`
as the value for `PROVIDER = `. Must not conflict with existing providers.

### `from_config(account_number, provider_config)` (classmethod)
Called once per account at startup. Receives the raw key-value dict from the
account section of `sia-server.conf` (all keys are lowercase). Should validate
all required settings and raise `ValueError` with a descriptive message if
anything is missing or invalid. This is the right place to check for external
dependencies.

Note: `account_number` is available for use in error messages and logging only.
Do not store it - the actual runtime account number is passed to `send()`.

### `send(account, message, priority)` (instance method)
Called each time a notification needs to be sent. Parameters:
- `account` - the account number string as received from the panel (ground truth)
- `message` - the formatted notification text
- `priority` - integer 1-5 (1=lowest, 5=highest/urgent)

Return values:
- `True` - notification sent successfully
- `False` - delivery failed, the dispatcher will retry with exponential backoff
- `None` - configuration issue, skip silently without retry

### `name` (property)
Human-readable provider name used in log messages by `notification.py`.
Should return a simple name like `'myprovider'`. Keep it short - detailed
delivery information belongs in the provider's own log messages inside `send()`.

## Configuration Keys

Your provider can use any configuration keys in the account section of
`sia-server.conf`. Keys are normalized to lowercase by the configuration loader.

The following keys are reserved and used by the server itself:
- `site_name` - the human-readable site name (`None` if not configured).
  Available in `provider_config` in `from_config()`. Use it to build
  notification titles, falling back to the `account` parameter in `send()`
  when `None`.
- `enabled` - connection policy (Yes/No/Secure)
- `provider` - which provider to use

## External Dependencies

If your provider requires external Python packages, check for them in
`from_config()` and raise a descriptive `ValueError` if they are missing:

```python
@classmethod
def from_config(cls, account_number: str, provider_config: dict) -> 'MyProvider':
    try:
        import some_package
    except ImportError:
        raise ValueError(
            f"[{account_number}] 'some_package' is required for myprovider. "
            "Install with: pip install some_package"
        )
    ...
```

## Pull Requests

Provider plugins that meet the following criteria are welcome as pull requests:

- Verified working against real hardware or service
- No required external binaries or non-Python dependencies
- No required external services beyond the notification target itself
- Clean, readable code with appropriate error handling
- Documented configuration keys

Providers requiring additional dependencies beyond the standard library and
`requests` or `pycryptodome` are welcome as forks or private implementations.
