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

CONFIG_PATH = os.environ.get("SIA_CONFIG")
if not CONFIG_PATH:
    if os.path.isdir("/config"):
        CONFIG_PATH = "/config/sia-server.conf"
    else:
        CONFIG_PATH = os.path.join(os.getcwd(), "sia-server.conf")

LOG_FILE_PATH = os.environ.get("SIA_LOG_FILE", "/tmp/sia-server.log")


def get_ini_parser() -> configparser.ConfigParser:
    """Parser setup that strips inline comments and preserves section cases."""
    config = configparser.ConfigParser(
        inline_comment_prefixes=('#', ';'),
        interpolation=None,
    )
    # Convert option keys to uppercase for canonical INI output
    config.optionxform = lambda optionstr: optionstr.upper()
    return config


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    config = get_ini_parser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)

    admin_user = config.get("WebGUI", "ADMIN_USER", fallback="admin")
    admin_pass = config.get("WebGUI", "ADMIN_PASS", fallback="admin")

    if not (secrets.compare_digest(credentials.username, admin_user) and 
            secrets.compare_digest(credentials.password, admin_pass)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def has_comments_or_legacy(file_path: str) -> bool:
    """Scans config file to check if it contains comments or legacy keys."""
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith('#') or stripped.startswith(';'):
                    return True
                if 'watchdog_restore_prio' in stripped or 'watchdog_lost_prio' in stripped:
                    return True
    except Exception:
        pass
    return False


@app.get("/api/config")
def read_config(username: str = Depends(get_current_user)):
    if not os.path.exists(CONFIG_PATH):
        raise HTTPException(status_code=404, detail=f"Config file not found at {CONFIG_PATH}")

    config = get_ini_parser()
    config.read(CONFIG_PATH)

    data = {}
    for section in config.sections():
        # Preserve original section casing strictly ([Default], [SIA-Server], [Watchdog], [IP-Check], [Logging], [Notification])
        data[section] = dict(config[section])

    # Find watchdog and ip-check sections case-insensitively
    watchdog_sec_name = next((s for s in data.keys() if s.lower() == 'watchdog'), None)
    ipcheck_sec_name = next((s for s in data.keys() if s.lower() == 'ip-check'), None)

    if not watchdog_sec_name:
        watchdog_sec_name = "Watchdog"
        data[watchdog_sec_name] = {}

    watchdog_data = data[watchdog_sec_name]
    ipcheck_data = data[ipcheck_sec_name] if ipcheck_sec_name else {}

    # Exact 4-level precedence mapping from configuration.py
    watchdog_keys = [
        "WATCHDOG_THRESHOLD",
        "MONITORING_STARTED_PRIO",
        "CONNECTION_RESTORED_PRIO",
        "INTERVAL_CHANGED_PRIO",
        "WATCHDOG_TIMEOUT_PRIO",
        "MONITORING_STARTED",
        "CONNECTION_RESTORED",
        "INTERVAL_CHANGED",
        "WATCHDOG_TIMEOUT"
    ]
    legacy_map = {
        "CONNECTION_RESTORED_PRIO": "watchdog_restore_prio",
        "WATCHDOG_TIMEOUT_PRIO": "watchdog_lost_prio"
    }

    for key in watchdog_keys:
        existing_val = None
        # 1. Check [Watchdog] section
        for k, v in watchdog_data.items():
            if k.upper() == key.upper():
                existing_val = v
                break
        
        # 2 & 3. Check [IP-Check] section or legacy keys if missing in Watchdog
        if existing_val is None or existing_val == "":
            for k, v in ipcheck_data.items():
                if k.upper() == key.upper():
                    existing_val = v
                    break
            if (existing_val is None or existing_val == "") and key in legacy_map:
                legacy_key = legacy_map[key]
                for k, v in ipcheck_data.items():
                    if k.upper() == legacy_key.upper():
                        existing_val = v
                        break
        
        if existing_val is not None and existing_val != "":
            watchdog_data[key] = existing_val

    contains_comments = has_comments_or_legacy(CONFIG_PATH)

    return {
        "path": CONFIG_PATH, 
        "config": data, 
        "has_comments": contains_comments
    }


@app.post("/api/config")
async def save_config(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    config = get_ini_parser()

    for section_name, section_data in payload.items():
        config.add_section(section_name)
        for key, value in section_data.items():
            clean_val = str(value).split('#')[0].split(';')[0].strip()
            config.set(section_name, key, clean_val)

    try:
        with open(CONFIG_PATH, "w", encoding='utf-8') as configfile:
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
        with open(LOG_FILE_PATH, "r", encoding='utf-8') as f:
            all_lines = f.readlines()
            return {"logs": [line.strip() for line in all_lines[-lines:]]}
    except Exception as e:
        return {"logs": [f"Error reading log file: {str(e)}"]}


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
