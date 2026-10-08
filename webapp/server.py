import os
import sys
import signal
import configparser
import secrets
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
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
    """Configured parser with inline comment stripping matching configuration.py."""
    config = configparser.ConfigParser(
        inline_comment_prefixes=('#', ';'),
        interpolation=None,
    )
    config.optionxform = str  # Preserve case
    return config


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    """Basic Auth authentication."""
    config = get_ini_parser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)

    admin_user = config.get("WebGUI", "ADMIN_USER", fallback="admin")
    admin_pass = config.get("WebGUI", "ADMIN_PASS", fallback="admin")

    is_correct_username = secrets.compare_digest(credentials.username, admin_user)
    is_correct_password = secrets.compare_digest(credentials.password, admin_pass)

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.get("/api/config")
def read_config(username: str = Depends(get_current_user)):
    """Reads the INI file, cleans inline comments, and maps legacy Watchdog settings."""
    if not os.path.exists(CONFIG_PATH):
        raise HTTPException(status_code=404, detail=f"Config file not found at {CONFIG_PATH}")

    config = get_ini_parser()
    config.read(CONFIG_PATH)

    data = {}
    for section in config.sections():
        data[section] = dict(config[section])

    # Dynamic legacy section bridging for WATCHDOG / IP-CHECK
    if "WATCHDOG" not in data:
        data["WATCHDOG"] = {}

    if "IP-Check" in data:
        # Migrate legacy IP-Check keys to Watchdog if missing in Watchdog
        ip_sec = data["IP-Check"]
        legacy_mappings = {
            "watchdog_threshold": "watchdog_threshold",
            "watchdog_restore_prio": "connection_restored_prio",
            "watchdog_lost_prio": "watchdog_timeout_prio",
            "monitoring_started_prio": "monitoring_started_prio",
            "interval_changed_prio": "interval_changed_prio",
            "monitoring_started": "monitoring_started",
            "connection_restored": "connection_restored",
            "interval_changed": "interval_changed",
            "watchdog_timeout": "watchdog_timeout",
        }
        for old_key, new_key in legacy_mappings.items():
            if old_key in ip_sec and new_key not in data["WATCHDOG"]:
                data["WATCHDOG"][new_key] = ip_sec[old_key]

    return {"path": CONFIG_PATH, "config": data}


@app.post("/api/config")
async def save_config(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    """Saves sanitized configuration back to disk."""
    config = get_ini_parser()

    for section_name, section_data in payload.items():
        config.add_section(section_name)
        for key, value in section_data.items():
            # Strip trailing inline comments if pasted manually
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
    """Dispatches SIGHUP signal to server process."""
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
