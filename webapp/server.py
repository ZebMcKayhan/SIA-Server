import os
import sys
import signal
import configparser
import asyncio
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

app = FastAPI(title="SIA-Server WebGUI", docs_url=None, redoc_url=None)
security = HTTPBasic()

# Configuration path resolution
CONFIG_PATH = os.environ.get("SIA_CONFIG")
if not CONFIG_PATH:
    if os.path.isdir("/config"):
        CONFIG_PATH = "/config/sia-server.conf"
    else:
        CONFIG_PATH = os.path.join(os.getcwd(), "sia-server.conf")

# Memory log buffer for stdout/log tailing
LOG_FILE_PATH = os.environ.get("SIA_LOG_FILE", "/tmp/sia-server.log")


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    """Simple Basic Auth against config.ini WebGUI section or fallback defaults."""
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str  # Preserve case
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
    """Reads the INI file into structured JSON grouped by sections."""
    if not os.path.exists(CONFIG_PATH):
        raise HTTPException(status_code=404, detail=f"Config file not found at {CONFIG_PATH}")

    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(CONFIG_PATH)

    data = {}
    for section in config.sections():
        data[section] = dict(config[section])
    return {"path": CONFIG_PATH, "config": data}


@app.post("/api/config")
async def save_config(payload: Dict[str, Any], username: str = Depends(get_current_user)):
    """Saves updated JSON back to the INI file format while keeping section keys intact."""
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str

    for section_name, section_data in payload.items():
        config.add_section(section_name)
        for key, value in section_data.items():
            config.set(section_name, key, str(value))

    try:
        with open(CONFIG_PATH, "w") as configfile:
            config.write(configfile)
        return {"status": "success", "message": "Configuration saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")


@app.post("/api/reload")
def trigger_hot_reload(username: str = Depends(get_current_user)):
    """Executes SIGHUP signal on Unix/Linux/Docker or direct internal call."""
    try:
        if sys.platform != "win32":
            # Send SIGHUP to parent or self
            os.kill(os.getppid(), signal.SIGHUP)
            return {"status": "success", "message": "SIGHUP signal dispatched successfully"}
        else:
            return {"status": "warning", "message": "SIGHUP not supported on Windows natively"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to dispatch signal: {str(e)}")


@app.get("/api/logs")
def get_logs(lines: int = 100, username: str = Depends(get_current_user)):
    """Fetches the tail end of the log output file."""
    if not os.path.exists(LOG_FILE_PATH):
        return {"logs": [f"Log file not found at {LOG_FILE_PATH}. Logging may be set to Screen or Syslog."]}

    try:
        with open(LOG_FILE_PATH, "r") as f:
            all_lines = f.readlines()
            return {"logs": [line.strip() for line in all_lines[-lines:]]}
    except Exception as e:
        return {"logs": [f"Error reading log file: {str(e)}"]}


# Static frontend files mounting
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
