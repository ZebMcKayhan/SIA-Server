# Asuswrt-Merlin Entware Service

These files provide a robust, self-healing service management solution for running the `sia-server` on a router with Asuswrt-Merlin firmware and the Entware package manager.

This setup consists of two scripts:
1.  **`S99siaserver`:** A standard `init.d` service script that handles starting and stopping the server during router boot/shutdown.
2.  **`check-sia.sh`:** A watchdog script, run periodically by `cron`, that ensures the server is always running and restarts it if it ever crashes.

## Prerequisites

-   An Asus router running [Asuswrt-Merlin](https://www.asuswrt-merlin.net/).
-   [Entware](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Entware) installed on a USB drive.
-   The `sia-server` project files.
-   The required Python packages (`python3`, `python3-requests`, etc.) installed via `opkg`.

## Installation

These instructions assume you have cloned or unzipped the `sia-server` project into the recommended JFFS directory `/jffs/addons/`.

### Step 1: Place the Project Files

It is recommended to place the entire `sia-server` project directory on the JFFS partition to ensure it survives reboots.

```
/jffs/addons/sia-server/
```

### Step 2: Install and Enable the Service Script

Copy the `init.d` script to the Entware startup directory and make it executable. The `S99` prefix ensures it starts late in the boot sequence, after networking is fully available.

```bash
# Copy the service file
cp /jffs/addons/sia-server/asuswrt-merlin/S99siaserver /opt/etc/init.d/

# Make it executable
chmod +x /opt/etc/init.d/S99siaserver
```

### Step 3: Prepare the Watchdog Script

The watchdog script is called by `cron` to monitor the service. It also needs to be made executable.

```bash
chmod +x /jffs/addons/sia-server/asuswrt-merlin/check-sia.sh
```

### Step 4: Start the Service

You can now start the service manually. This will launch the `sia-server.py` and `ip_check.py` processes and set up the monitoring cron job.

```bash
/opt/etc/init.d/S99siaserver start
```

The service will now start automatically every time your router boots.

## Managing the Service

You can manage the service from the command line using the `init.d` script:

-   **Start the service:**
    ```bash
    /opt/etc/init.d/S99siaserver start
    ```

-   **Stop the service:**
    ```bash
    /opt/etc/init.d/S99siaserver stop
    ```

-   **Restart the service:**
    ```bash
    /opt/etc/init.d/S99siaserver restart
    ```

## Running on Other Embedded Devices (e.g., OpenWrt)

While this project provides specific instructions for standard Linux (using `systemd`) and Asuswrt-Merlin (using `init.d`), it is possible to run the server on other embedded Linux systems like **OpenWrt**.

This is an advanced topic that will require familiarity with your specific platform. The general requirements are:

1.  **Python 3:** You must have a working Python 3 interpreter.
2.  **Dependencies:** You must be able to install the `requests` library (and `pyopenssl` stack if needed) via your platform's package manager (e.g., `opkg` on OpenWrt).
3.  **Service Management:** You will need to create your own service/init script that is compatible with your system's init process.
    -   For **OpenWrt**, this means creating a `procd` init script in `/etc/init.d/`. The logic will be similar to the `systemd` or `S99siaserver` examples, but the syntax is different.
    -   You will need to ensure the script starts the `sia-server.py` and, optionally, the `ip_check.py` processes.

The `asuswrt-merlin/check-sia.sh` watchdog script is written in POSIX-compliant shell and can likely be adapted with minor changes to provide self-healing capabilities on other platforms that use `cron`.
