import os
import sys
import signal
import configparser
import secrets
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

app = FastAPI(title="SIA-Server WebGUI", docs_url=None, redoc_url=None)
security = HTTPBasic()

# Path resolution
CONFIG_PATH = os.environ.get("SIA_CONFIG")
if not CONFIG_PATH:
    if os.path.isdir("/config"):
        CONFIG_PATH = "/config/sia-server.conf"
    else:
        CONFIG_PATH = os.path.join(os.getcwd(), "sia-server.conf")

LOG_FILE_PATH = os.environ.get("SIA_LOG_FILE", "/tmp/sia-server.log")


def get_ini_parser() -> configparser.ConfigParser:
    """Configured parser with inline comment stripping and case-insensitivity."""
    config = configparser.ConfigParser(
        inline_comment_prefixes=('#', ';'),
        interpolation=None,
    )
    # Case-insensitive option matching to prevent duplicates
    config.optionxform = str.lower
    return config


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    config = get_ini_parser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)

    admin_user = config.get("webgui", "admin_user", fallback="admin")
    admin_pass = config.get("webgui", "admin_pass", fallback="admin")

    is_correct_username = secrets.compare_digest(credentials.username, admin_user)
    is_correct_password = secrets.compare_digest(credentials.password, admin_pass)

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def resolve_watchdog_settings(raw_config: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """Applies the exact 4-tier precedence from configuration.py for Watchdog values."""
    watchdog_sec = raw_config.get("watchdog", {})
    ipcheck_sec = raw_config.get("ip-check", {})

    def get_val(key: str, legacy_ip_key: str = None, default: str = "") -> str:
        if key in watchdog_sec:
            return watchdog_sec[key]
        if key in ipcheck_sec:
            return ipcheck_sec[key]
        if legacy_ip_key and legacy_ip_key in ipcheck_sec:
            return ipcheck_sec[legacy_ip_key]
        return default

    return {
        "watchdog_threshold": get_val("watchdog_threshold", default="2.1"),
        "monitoring_started_prio": get_val("monitoring_started_prio", default="2"),
        "connection_restored_prio": get_val("connection_restored_prio", "watchdog_restore_prio", default="2"),
        "interval_changed_prio": get_val("interval_changed_prio", default="3"),
        "watchdog_timeout_prio": get_val("watchdog_timeout_prio", "watchdog_lost_prio", default="4"),
        "monitoring_started": get_val("monitoring_started", default=""),
        "connection_restored": get_val(
            "connection_restored",
            default="Heartbeat received [at %new_panel_time, ]after %elapsed, connection restored."
        ),
        "interval_changed": get_val("interval_changed", default=""),
        "watchdog_timeout": get_val(
            "watchdog_timeout",
            default="Heartbeat lost, last heartbeat received was [at %last_panel_time, ]%elapsed ago."
        ),
    }


@app.get("/api/config")
def read_config(username: str = Depends(get_current_user)):
    if not os.path.exists(CONFIG_PATH):
        raise HTTPException(status_code=404, detail=f"Config file not found at {CONFIG_PATH}")

    config = get_ini_parser()
    config.read(CONFIG_PATH)

    data = {}
    for section in config.sections():
        # Store as lowercase dictionary keys to unify UI access
        data[section.lower()] = dict(config[section])

    # Unify Watchdog settings into a single section using configuration.py rules
    data["watchdog"] = resolve_watchdog_settings(data)

    return {"path": CONFIG_PATH, "config": data}


@app.post("/api/config")
async def save_config(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    config = get_ini_parser()

    for section_name, section_data in payload.items():
        config.add_section(section_name)
        for key, value in section_data.items():
            clean_val = str(value).split('#')[0].split(';')[0].strip()
            config.set(section_name, key, clean_val)

    try:
        with open(CONFIG_PATH, "w") as configfile:
            config.write(configfile)
        return {"status": "success", "message": "Configuration saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")


@app.post("/api/reload")
def trigger_hot_reload(username: str = Depends(get_current_user)):
    try:
        if sys.platform != "win32":
            os.kill(os.getppid(), signal.SIGHUP)
            return {"status": "success", "message": "SIGHUP signal sent to sia-server process"}
        else:
            return {"status": "warning", "message": "SIGHUP hot-reload is not supported on Windows"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload process: {str(e)}")


@app.get("/api/logs")
def get_logs(lines: int = 100, username: str = Depends(get_current_user)):
    if not os.path.exists(LOG_FILE_PATH):
        return {"logs": [f"Log file not found at {LOG_FILE_PATH}."]}

    try:
        with open(LOG_FILE_PATH, "r") as f:
            all_lines = f.readlines()
            return {"logs": [line.strip() for line in all_lines[-lines:]]}
    except Exception as e:
        return {"logs": [f"Error reading log file: {str(e)}"]}


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
