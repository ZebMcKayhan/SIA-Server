# SIA-Server WebGUI (Experimental)

> **⚠️ Status:** This feature is currently **experimental and a work in progress**. 

This directory contains the self-contained WebGUI interface for **SIA-Server**, designed to provide an easy-to-use web interface for managing your `sia-server.conf` configuration, viewing live logs, and triggering hot-reloads via `SIGHUP`.

---

## Prerequisites & Dependencies

To run the WebGUI, you need Python 3 along with FastAPI and Uvicorn. Install the required dependencies using pip:

```bash
python -m pip install fastapi uvicorn
```

*(Note: Ensure your main SIA-Server requirements and dependencies are also installed in your Python environment).*

---

## How to Run

To run the WebGUI server properly, execute the command **from the root directory of your `sia-server` repository** so it can locate your configuration file (`sia-server.conf`):

```bash
uvicorn webapp.server:app --host 0.0.0.0 --port 10002 --reload
```

* **`--host 0.0.0.0`**: Binds the web server to all network interfaces (change to `127.0.0.1` if you only want local machine access).
* **`--port 10002`**: Runs the management UI on port `10002` (leaving your SIA listener ports `10000` and `10001` completely free).
* **`--reload`**: *(Optional)* Enables auto-reload during development when Python files change.

---

## Configuration Path & Authentication

* **Configuration File**: By default, the WebGUI looks for `sia-server.conf` in your current working directory, or inside `/config/sia-server.conf` if running inside a Docker container. You can override this explicitly using the environment variable:
  ```bash
  export SIA_CONFIG=/path/to/your/sia-server.conf
  ```
* **Default Login**: Protected by HTTP Basic Auth. Default credentials can be set under the `[WebGUI]` section of your configuration file (`admin` / `admin` by default).
