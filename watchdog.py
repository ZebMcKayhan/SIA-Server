#!/usr/bin/env python3
"""
Galaxy SIA Watchdog

Generic watchdog shared by the IP-Check server and the Dimension
heartbeat monitor.

Heartbeat sources:
  - ip_check.py   – decodes the 26-byte IP-Check packet and calls update_watchdog().
  - sia-server.py – detects a Dimension heartbeat GalaxyEvent and calls update_watchdog().

The watchdog task is started **lazily** on the first valid call to
update_watchdog().  If no heartbeat is ever received, no task is created.
"""

import asyncio
import logging
import re
import time
import datetime
from queue import Queue
from typing import Optional, Union

from notification import enqueue_message_notification

log = logging.getLogger('watchdog')

# ---------------------------------------------------------------------------
# Module-level state — set by init()
# ---------------------------------------------------------------------------
config   = None
accounts = None


def init(cfg, accts) -> None:
    """Initialise the watchdog module with shared config and accounts."""
    global config, accounts
    config   = cfg
    accounts = accts


# Watchdog state per account.
# {
#   account_number: {
#       'state':           'UNKNOWN' | 'CONNECTED' | 'DISCONNECTED' | 'DISABLED',
#       'last_seen':       float,        # server time (time.time())
#       'last_panel_time': str | None,   # formatted panel local time
#       'last_panel_ts':   float | None, # panel epoch float
#       'interval':        int,          # heartbeat interval in seconds
#   }
# }
watchdog_state: dict = {}

# Lazy task handle — None until the first valid heartbeat.
_watchdog_task_handle: Optional[asyncio.Task] = None


# ===================================================================
# Heartbeat Interval Parsing
# ===================================================================

def parse_heartbeat_interval(action_text: str, prefix: str) -> Optional[int]:
    r"""
    Parse the heartbeat interval from a Dimension heartbeat action_text string.

    Expected format after *prefix*: ``' HH:MM <value>'``

    Example::

        action_text = '[HEARTBT.] 00:05 00001'
        prefix      = '[HEARTBT.]'
        → 300   (5 minutes in seconds)

    Returns the interval in integer seconds, or ``None`` if the text
    cannot be parsed or the resulting interval is zero.

    The trailing ``<value>`` field (e.g. ``00001``) is intentionally
    discarded — its meaning is not yet confirmed.
    """
    remainder = action_text[len(prefix):].strip()
    match = re.match(r'^(\d{1,2}):(\d{2})\b', remainder)
    if not match:
        log.warning(
            "Watchdog: cannot parse heartbeat interval from action_text %r "
            "(expected 'HH:MM' after prefix %r).", action_text, prefix)
        return None
    hours   = int(match.group(1))
    minutes = int(match.group(2))
    interval = hours * 3600 + minutes * 60
    if interval <= 0:
        log.warning(
            "Watchdog: parsed zero-length heartbeat interval from action_text %r - "
            "ignoring.", action_text)
        return None
    return interval


# ===================================================================
# Notification Formatting
# ===================================================================

def format_duration(seconds: Union[int, float], fmt: str) -> str:
    """
    Format a duration in seconds using the tokens ``%DD``, ``%hh``, ``%mm``,
    ``%ss``.

    Rules:

    - Units are calculated from the largest to the smallest token present
      in *fmt*.
    - A missing higher-order token folds its value into the next lower one.
    - ``%DD``: days — no leading zeros, ``0`` shown as ``'0'``.
    - ``%hh``: hours — minimum 2 digits.
    - ``%mm``: minutes — minimum 2 digits.
    - ``%ss``: seconds — minimum 2 digits.
    """
    total = max(0, int(round(seconds)))
    has_days    = '%DD' in fmt
    has_hours   = '%hh' in fmt
    has_minutes = '%mm' in fmt
    has_seconds = '%ss' in fmt

    rem = total
    days    = 0
    hours   = 0
    minutes = 0
    secs    = 0

    if has_days:
        days = rem // 86400
        rem %= 86400
    if has_hours:
        hours = rem // 3600
        rem %= 3600
    if has_minutes:
        minutes = rem // 60
        rem %= 60
    if has_seconds:
        secs = rem

    result = fmt
    if has_days:
        result = result.replace('%DD', str(days))
    if has_hours:
        result = result.replace('%hh', f"{hours:02d}")
    if has_minutes:
        result = result.replace('%mm', f"{minutes:02d}")
    if has_seconds:
        result = result.replace('%ss', f"{secs:02d}")
    return result


def format_timestamp_dt(dt: datetime.datetime, fmt: str) -> str:
    """Format a ``datetime`` using ``%YYYY``, ``%YY``, ``%MM``, ``%DD``,
    ``%hh``, ``%mm``, ``%ss`` tokens."""
    res = fmt
    res = res.replace('%YYYY', dt.strftime('%Y'))
    res = res.replace('%YY',   dt.strftime('%y'))
    res = res.replace('%MM',   dt.strftime('%m'))
    res = res.replace('%DD',   dt.strftime('%d'))
    res = res.replace('%hh',   dt.strftime('%H'))
    res = res.replace('%mm',   dt.strftime('%M'))
    res = res.replace('%ss',   dt.strftime('%S'))
    return res


def format_timestamp_struct(st: time.struct_time, fmt: str) -> str:
    """Format a ``struct_time`` using ``%YYYY``, ``%YY``, ``%MM``, ``%DD``,
    ``%hh``, ``%mm``, ``%ss`` tokens."""
    res = fmt
    res = res.replace('%YYYY', time.strftime('%Y', st))
    res = res.replace('%YY',   time.strftime('%y', st))
    res = res.replace('%MM',   time.strftime('%m', st))
    res = res.replace('%DD',   time.strftime('%d', st))
    res = res.replace('%hh',   time.strftime('%H', st))
    res = res.replace('%mm',   time.strftime('%M', st))
    res = res.replace('%ss',   time.strftime('%S', st))
    return res


def _render_watchdog_field(
    field_name: str,
    fmt: Optional[str],
    context: dict,
    server_time_st: time.struct_time,
) -> Optional[str]:
    """
    Render a single ``%field`` or ``%field{format}`` token for a watchdog
    notification template.

    Returns ``None`` when the field is unavailable — this causes the enclosing
    ``[ ... ]`` optional section to be suppressed.
    """
    # Server time tokens
    _server_strftime = {
        'time': '%H:%M',
        'YYYY': '%Y',
        'YY':   '%y',
        'MM':   '%m',
        'DD':   '%d',
        'hh':   '%H',
        'mm':   '%M',
        'ss':   '%S',
    }
    if field_name in _server_strftime:
        return time.strftime(_server_strftime[field_name], server_time_st)

    # Plain string fields
    if field_name in ('account', 'site_name', 'current_state', 'new_state'):
        val = context.get(field_name)
        return str(val) if val is not None else None

    # Duration fields
    if field_name in ('last_interval', 'new_interval', 'last_threshold',
                      'new_threshold', 'elapsed'):
        val = context.get(field_name)
        if val is None:
            return None
        return format_duration(val, fmt) if fmt else format_duration(val, '%hh:%mm:%ss')

    # last_seen timestamp
    if field_name == 'last_seen':
        ts = context.get('last_seen')
        if ts is None:
            return None
        st = time.localtime(ts)
        return format_timestamp_struct(st, fmt) if fmt else time.strftime('%Y-%m-%d %H:%M:%S', st)

    # Panel time fields (may carry a pre-formatted string or a float epoch)
    if field_name in ('last_panel_time', 'new_panel_time'):
        ts_key  = 'last_panel_ts'  if field_name == 'last_panel_time' else 'new_panel_ts'
        ts      = context.get(ts_key)
        str_val = context.get(field_name)
        if ts is None and str_val is None:
            return None
        if fmt:
            if ts is not None:
                dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
                return format_timestamp_dt(dt, fmt)
            if str_val is not None:
                try:
                    dt = datetime.datetime.strptime(
                        str_val, '%Y-%m-%d %H:%M').replace(tzinfo=datetime.timezone.utc)
                    return format_timestamp_dt(dt, fmt)
                except Exception:
                    return str_val
            return None
        if str_val is not None:
            return str_val
        return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')

    return None


def format_watchdog_notification(template: str, context: dict) -> str:
    r"""
    Render a watchdog notification string from a template and a context dict.

    Template syntax::

        %field              – field with default formatting
        %field{format}      – field with custom format specifier
        [ ... ]             – optional section; omitted when any field inside is None
        \n  or  \r\n        – replaced with a real newline

    Available fields mirror the ``IP_CHECK_NOTIFICATION_FIELDS`` set in
    ``configuration.py``.
    """
    server_time_st = time.localtime()

    _TOKEN = re.compile(r'%([a-zA-Z_][a-zA-Z0-9_]*)(?:\{([^{}]*)\})?')

    def render_optional(m: re.Match) -> str:
        section = m.group(1)
        tokens  = _TOKEN.findall(section)
        if any(
            _render_watchdog_field(fn, f or None, context, server_time_st) is None
            for fn, f in tokens
        ):
            return ''

        def sub_in_section(sm: re.Match) -> str:
            val = _render_watchdog_field(
                sm.group(1), sm.group(2) or None, context, server_time_st)
            return val if val is not None else ''

        return _TOKEN.sub(sub_in_section, section)

    template = re.sub(r'\[([^\[\]]*)\]', render_optional, template)

    def sub_main(m: re.Match) -> str:
        val = _render_watchdog_field(
            m.group(1), m.group(2) or None, context, server_time_st)
        return val if val is not None else ''

    template = _TOKEN.sub(sub_main, template)
    template = template.replace(r'\r\n', '\n').replace(r'\n', '\n')
    return template


# ===================================================================
# Watchdog State Management
# ===================================================================

def _format_interval_str(interval: int) -> str:
    """Return ``'HH:MM:SS (Ns)'`` string for log messages."""
    h = interval // 3600
    m = (interval % 3600) // 60
    s = interval % 60
    return f"{h:02d}:{m:02d}:{s:02d} ({interval}s)"


def update_watchdog(
    account_number: str,
    site_name: str,
    panel_time: Optional[str],
    panel_ts: Optional[float],
    interval: int,
    notification_queue: Queue,
) -> None:
    """
    Update watchdog state on receipt of a valid heartbeat.

    Called by **two** sources:

    * ``ip_check.py`` — after validating and decoding a raw IP-Check packet.
    * ``sia-server.py`` — after detecting and parsing a Dimension heartbeat
      ``GalaxyEvent``.

    The watchdog does not know or care which source sent the heartbeat.

    The watchdog task is started **lazily** here on the very first call.

    Args:
        account_number:     Account identifier string.
        site_name:          Human-readable site name (falls back to account_number).
        panel_time:         Formatted panel local time ``'YYYY-MM-DD HH:MM'``,
                            or ``None`` when not available (Dimension heartbeats).
        panel_ts:           Panel epoch ``float`` timestamp, or ``None``.
        interval:           Heartbeat interval in **seconds** (must be > 0).
        notification_queue: Notification queue for state-transition messages.
    """
    global _watchdog_task_handle

    # --- Lazy task start ---
    if _watchdog_task_handle is None:
        try:
            loop = asyncio.get_running_loop()
            _watchdog_task_handle = loop.create_task(watchdog_task(notification_queue))
            log.debug("Watchdog task started lazily (first heartbeat, account %s).",
                      account_number)
        except RuntimeError:
            log.debug("Watchdog: no running event loop; task not started.")

    interval_str      = _format_interval_str(interval)
    now               = time.time()
    prev              = watchdog_state.get(account_number, {})
    current_state     = prev.get('state', 'UNKNOWN')
    previous_interval = prev.get('interval')
    prev_panel_time   = prev.get('last_panel_time')
    prev_panel_ts     = prev.get('last_panel_ts')
    prev_last_seen    = prev.get('last_seen')
    current_threshold = (previous_interval * config.IP_CHECK_WATCHDOG
                         if previous_interval is not None else None)
    new_threshold     = interval * config.IP_CHECK_WATCHDOG

    new_state = 'DISABLED' if config.IP_CHECK_WATCHDOG <= 1.0 else 'CONNECTED'
    watchdog_state[account_number] = {
        'state':           new_state,
        'last_seen':       now,
        'last_panel_time': panel_time,
        'last_panel_ts':   panel_ts,
        'interval':        interval,
    }

    # --- State transition notifications ---

    if current_state == 'DISCONNECTED':
        log.info("Watchdog: Site: %s (Account: %s) - connection restored, interval %s.",
                 site_name, account_number, interval_str)
        fmt = getattr(config, 'IP_CHECK_CONNECTION_RESTORED', None)
        if fmt:
            elapsed = (now - prev_last_seen) if prev_last_seen is not None else None
            msg = format_watchdog_notification(fmt, {
                'account':         account_number,
                'site_name':       site_name,
                'current_state':   current_state,
                'new_state':       new_state,
                'last_panel_time': prev_panel_time,
                'last_panel_ts':   prev_panel_ts,
                'last_interval':   previous_interval,
                'last_threshold':  current_threshold,
                'last_seen':       prev_last_seen,
                'elapsed':         elapsed,
                'new_panel_time':  panel_time,
                'new_panel_ts':    panel_ts,
                'new_interval':    interval,
                'new_threshold':   new_threshold,
            })
            enqueue_message_notification(
                account_number, site_name, msg,
                priority=getattr(config, 'IP_CHECK_CONNECTION_RESTORED_PRIO', 2),
                queue=notification_queue,
            )

    elif current_state == 'UNKNOWN':
        if config.IP_CHECK_WATCHDOG <= 1.0:
            log.info("Watchdog: Site: %s (Account: %s) - watchdog DISABLED, interval %s.",
                     site_name, account_number, interval_str)
        else:
            log.info("Watchdog: Site: %s (Account: %s) - monitoring started, interval %s.",
                     site_name, account_number, interval_str)
        fmt = getattr(config, 'IP_CHECK_MONITORING_STARTED', None)
        if fmt:
            msg = format_watchdog_notification(fmt, {
                'account':         account_number,
                'site_name':       site_name,
                'current_state':   current_state,
                'new_state':       new_state,
                'last_panel_time': None,
                'last_panel_ts':   None,
                'last_interval':   None,
                'last_threshold':  None,
                'last_seen':       None,
                'elapsed':         None,
                'new_panel_time':  panel_time,
                'new_panel_ts':    panel_ts,
                'new_interval':    interval,
                'new_threshold':   new_threshold,
            })
            enqueue_message_notification(
                account_number, site_name, msg,
                priority=getattr(config, 'IP_CHECK_MONITORING_STARTED_PRIO', 2),
                queue=notification_queue,
            )

    else:
        # CONNECTED or DISABLED — check for interval change
        if previous_interval is not None and previous_interval != interval:
            log.info("Watchdog: Site: %s (Account: %s) - interval updated to %s.",
                     site_name, account_number, interval_str)
            fmt = getattr(config, 'IP_CHECK_INTERVAL_CHANGED', None)
            if fmt:
                elapsed = (now - prev_last_seen) if prev_last_seen is not None else None
                msg = format_watchdog_notification(fmt, {
                    'account':         account_number,
                    'site_name':       site_name,
                    'current_state':   current_state,
                    'new_state':       new_state,
                    'last_panel_time': prev_panel_time,
                    'last_panel_ts':   prev_panel_ts,
                    'last_interval':   previous_interval,
                    'last_threshold':  current_threshold,
                    'last_seen':       prev_last_seen,
                    'elapsed':         elapsed,
                    'new_panel_time':  panel_time,
                    'new_panel_ts':    panel_ts,
                    'new_interval':    interval,
                    'new_threshold':   new_threshold,
                })
                enqueue_message_notification(
                    account_number, site_name, msg,
                    priority=getattr(config, 'IP_CHECK_INTERVAL_CHANGED_PRIO', 3),
                    queue=notification_queue,
                )


# ===================================================================
# Watchdog Task
# ===================================================================

async def watchdog_task(notification_queue: Queue) -> None:
    """
    Async task that checks for missed heartbeats every 60 seconds.

    Started lazily by :func:`update_watchdog` on the first valid heartbeat.

    Transitions ``CONNECTED`` accounts to ``DISCONNECTED`` when the time
    elapsed since ``last_seen`` exceeds ``interval × IP_CHECK_WATCHDOG``.
    """
    log.debug("Watchdog task running.")
    while True:
        await asyncio.sleep(60)

        now = time.time()
        for account_number, state in list(watchdog_state.items()):
            if state['state'] != 'CONNECTED':
                continue

            interval = state['interval']
            if not interval:
                continue

            elapsed   = now - state['last_seen']
            threshold = interval * config.IP_CHECK_WATCHDOG
            if elapsed <= threshold:
                continue

            # Transition to DISCONNECTED
            current_state   = state['state']
            new_state       = 'DISCONNECTED'
            watchdog_state[account_number]['state'] = new_state
            last_panel_time = state['last_panel_time']
            last_panel_ts   = state.get('last_panel_ts')
            last_seen       = state['last_seen']

            account_cfg = accounts.get(account_number)
            site_name   = account_cfg.site_name if account_cfg else account_number
            policy      = account_cfg.policy    if account_cfg else 'yes'

            if policy == 'no':
                log.debug(
                    "Watchdog: Site: %s (Account: %s) - heartbeat lost but account is "
                    "disabled, skipping notification.", site_name, account_number)
                continue

            e_h, e_m, e_s = (int(elapsed) // 3600,
                              (int(elapsed) % 3600) // 60,
                              int(elapsed) % 60)
            log.warning(
                "Watchdog: Site: %s (Account: %s) - heartbeat lost! "
                "No ping received for %02d:%02d:%02d.",
                site_name, account_number, e_h, e_m, e_s)

            fmt = getattr(config, 'IP_CHECK_WATCHDOG_TIMEOUT', None)
            if fmt:
                msg = format_watchdog_notification(fmt, {
                    'account':         account_number,
                    'site_name':       site_name,
                    'current_state':   current_state,
                    'new_state':       new_state,
                    'last_panel_time': last_panel_time,
                    'last_panel_ts':   last_panel_ts,
                    'last_interval':   interval,
                    'last_threshold':  threshold,
                    'last_seen':       last_seen,
                    'elapsed':         elapsed,
                    'new_panel_time':  None,
                    'new_panel_ts':    None,
                    'new_interval':    None,
                    'new_threshold':   None,
                })
                enqueue_message_notification(
                    account_number, site_name, msg,
                    priority=getattr(config, 'IP_CHECK_WATCHDOG_TIMEOUT_PRIO', 4),
                    queue=notification_queue,
                )
