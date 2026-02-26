# Honeywell Galaxy SIA Notification Server

SIA-Server is a lightweight, self-hosted Python service that receives SIA protocol messages from Honeywell Galaxy Flex alarm systems and forwards them as rich, prioritized push notifications via [ntfy.sh](https://ntfy.sh/).

It was created as a replacement for the discontinued free Honeywell push notification service, allowing users to regain full control over their alarm alerts without ongoing subscription costs.

This project was developed and tested on a Honeywell Galaxy Flex 20. It is likely compatible with other Honeywell Galaxy panels, but this has not been verified.

If your Galaxy Flex notifications suddenly stopped working, this project provides a self-hosted alternative.

> **IMPORTANT SECURITY NOTICE**
> The communication between the alarm panel and this server is **unencrypted**. This server is designed to be run on a trusted local network only. Please read the full [Security & Privacy Guidelines](#security--privacy-guidelines) before installation.

## Features

-   **Self-Hosted:** Runs on any local Windows or Linux machine, like a Raspberry Pi.
-   **Real-time Notifications:** Instantly forwards alarm events to your devices.
-   **Prioritized Alerts:** Uses ntfy.sh priorities to distinguish between urgent alarms and routine events.
-   **Advanced Notification Routing:** Route notifications for different accounts to different ntfy.sh topics, each with its own authentication (Bearer Token or User/Pass).
-   **Robust Protocol Handling:** Correctly parses the multi-message protocol used by Galaxy Flex panels.
-   **Broad SIA Level Support:** The flexible parser can correctly handle event data from SIA Levels 0, 1, 2, and 3.
-   **Optional Heartbeat Server:** Includes an optional server to handle the proprietary Honeywell "IP Check" heartbeat.
-   **Character Encoding Fixes:** Decodes the proprietary character set used by Galaxy panels (e.g., Å, Ä, Ö).
-   **Highly Configurable:** Most user settings are in a simple `sia-server.conf` file, with advanced protocol constants located in the `galaxy/` directory.

## Prerequisites

-   A Honeywell Galaxy Flex alarm system with an Ethernet module (e.g., A083-00-10 or E080-4).
-   A Linux or Windows machine on the same network as the alarm system (a Raspberry Pi running Raspberry Pi OS is perfect).
-   Python 3.
-   The `python3-requests` package and the optional `python3-uvloop` package (for Linux).

## File Structure

The project is structured to separate the server logic, protocol parsing, and configuration.
```
.
├── sia-server.py           # The main server application
├── sia-server.conf         # Main user configuration file.
├── configuration.py        # Loads and validates all configuration.
├── notification.py         # Handles formatting and sending of notifications.
├── ip_check.py             # Optional subprocess for answering heartbeats.
├── README.md               # This file.
├── galaxy/
│   ├── __init__.py
│   ├── README.md           # Technical description of the protocol.  
│   ├── parser.py           # Handles parsing of the Galaxy SIA protocol.
│   └── constants.py        # Constants used in the SIA protocol.
└── asuswrt-merlin/
    ├── README.md           # Install instructions for Asuswrt-Merlin.
    ├── S99siaserver        # Entware service (init.d) file.
    └── check-sia.sh        # Watchdog script for Entware service.
```

## Installation & Setup

This guide will walk you through the five main steps to get your server running.

### Step 1: Download the Server Code
The recommended way is to download the latest stable release.
1.  Go to the [Releases page](https://github.com/ZebMcKayhan/SIA-Server/releases) on GitHub.
2.  Under the latest release, download the `Source code (zip)` file.
3.  Unzip the file to your chosen directory (e.g., `/home/pi/Scripts/sia-server` on Linux or `C:\siaserver` on Windows).

<details>
<summary>For Developers: Cloning with Git</summary>

If you want the latest development code, you can clone the repository directly:
```bash
git clone https://github.com/ZebMcKayhan/SIA-Server.git sia-server
cd sia-server
```
</details>

### Step 2: Install Python and Dependencies
This server requires Python 3. The installation steps are different for Linux and Windows.

#### For Linux (e.g., Raspberry Pi, Debian, Ubuntu)
1.  **Install Python (if needed):** Most modern Linux systems come with Python 3 pre-installed. You can check with `python3 --version`. If you need to install it
    ```bash
    sudo apt update
    sudo apt install python3
    ```
2.  **Install Dependencies:** Use `apt` to install the required packages. `uvloop` is an optional performance enhancement.
    ```bash
    sudo apt update
    sudo apt install python3-requests python3-uvloop
    ```

#### For Windows
1.  **Install Python:** Download and install the latest Python 3 from the [official Python website](https://www.python.org/). **Important:** During installation, make sure to check the box that says "Add Python to PATH".
2.  **Install Dependencies:** Open a **PowerShell** or **Command Prompt**. It is strongly recommended to use `python -m pip` to ensure you are installing packages for the correct Python interpreter.
    ```powershell
    python -m pip install requests pyopenssl cryptography ndg-httpsclient
    ```
    > **Note:** The extra packages (`pyopenssl`, etc.) are highly recommended to avoid potential HTTPS/SSL errors when sending notifications from Windows.

### Step 3: Get the Notification App and Topic
Before configuring the server, get the ntfy.sh app on your phone or computer.
1.  Follow the instructions at the [ntfy.sh documentation](https://docs.ntfy.sh/subscribe/phone/) to get the app.
2.  Inside the app, subscribe to a new topic. **Choose a long, random, unguessable name** for your topic to keep it private (e.g., `alarm-skUHvisapP2J382MDI2`).
3.  You will use the full URL of this topic (e.g., `https://ntfy.sh/alarm-skUHvisapP2J382MDI2`) in the configuration file.

### Step 4: Configure Your Alarm Panel
Log into your Galaxy Flex panel's installer menu and configure the Ethernet module. The numbers in parentheses are the menu codes for a Galaxy Flex 20.
-   **ARC IP Address:** The IP of the machine running `sia-server.py` (e.g., `192.168.128.10`). (Menu `56.1.1.1.4.1`)
-   **ARC Port:** The port for the `[SIA-Server]` and optionally the `[IP-Check]` server. (Menu `56.1.1.1.4.1`)
-   **Protocol:** SIA. Levels 0-3 are supported; Level 3 is recommended for the most detail. (Menu `56.1.1.1.4.2`)
-   **Account Number:** Your 4 or 6-digit alarm account number. SIA Level 3 requires 6 digits. (Menu `56.1.2.1.1`)
-   **Encryption:** Must be set to **Off**. The proprietary encryption is not supported. (Menu `56.3.3.5`)
-   **IP-Check:** (Optional) To use the heartbeat feature, enable it by setting a time interval (e.g., 00:30 for 30 minutes). `00:00` means disabled. (Menu `56.3.3.7.1`)
-   **Eng. Test:** Use this to send a test notification without generating a fault. (Menu `56.7.1`)

### Step 5: Configure the Server
Edit the `sia-server.conf` file to match your setup. The file is pre-populated with examples to guide you.
```bash
# On Linux
nano /path/to/your/sia-server/sia-server.conf
```
On Windows, simply edit the file with a text editor like Notepad.

## Configuration Explained

The primary configuration is done in `sia-server.conf`. This file is designed to be user-friendly and not sensitive to Python syntax. More advanced, technical constants (like character maps and command codes) are located in `galaxy/constants.py`.

-   **Site Sections (`[012345]`):** Each site is defined by a section where the header is the panel's unique **Account Number**.
    -   `SITE_NAME`: A friendly name for the site (e.g., "Main House"). If omitted, the account number itself is used.
    -   `NTFY_ENABLED`, `NTFY_TOPIC`, `NTFY_TITLE`: Configure notification delivery for this site.
    -   `NTFY_AUTH`: Can be `None`, `Token`, or `Userpass` for private topics. Provide the corresponding `NTFY_TOKEN` or `NTFY_USER`/`NTFY_PASS` keys.

-   **`[Default]` Section:** A special section for events from account numbers not specifically listed.

-   **`[SIA-Server]` & `[IP-Check]` Sections:** Configure the ports and addresses for the main server and the optional heartbeat server.

-   **`[Logging]` Section:** Control the log level, output, and file rotation.
    -   `LOG_LEVEL`: Set the verbosity of logs (`DEBUG`, `INFO`, `WARNING`, `ERROR`). `INFO` is recommended for normal use.
    -   `LOG_TO`: Choose `Screen` (for testing/`systemd` journal) or `File`.
    -   `LOG_FILE`: If `LOG_TO = File`, specify the full path to the log file.
    -   `LOG_MAX_MB`: The maximum size in Megabytes before the log file is rotated.
    -   `LOG_BACKUP_COUNT`: The number of old log files to keep.

-   **`[Notification]` Section:** Configures the server's resilient retry queue and event priorities.
    -   **Queue Settings:** `MAX_QUE_SIZE`, `MAX_RETRIES`, `MAX_RETRY_TIME` control the behavior of the retry queue for handling network outages.
    -   **Priority Settings:** `PRIORITY_1` through `PRIORITY_5` contain comma- or space-separated lists of the 2-character SIA Event Codes that should be assigned to that priority level.
    -   `DEFAULT_PRIORITY`: The priority level (1-5) to use for any event code not found in the specific priority lists.

## Usage
### For Linux

#### Manual Start (for testing)
> **Note:** It's convenient to set `LOG_TO = Screen` in `sia-server.conf` to see live events in your terminal.
```bash
cd /path/to/your/sia-server
python3 sia-server.py
```
Press `Ctrl+C` to stop.

#### As a Service (Recommended)
> **Note:** Set `LOG_TO = File` in `sia-server.conf` to keep a persistent log.
1.  **Create the Service File:** `sudo nano /etc/systemd/system/sia-server.service`
2.  **Paste this content**, changing the paths in `WorkingDirectory` and `ExecStart`.
    ```ini
    [Unit]
    Description=Galaxy SIA Alarm Server
    After=network.target
    [Service]
    Type=simple
    User=pi
    WorkingDirectory=/home/pi/Scripts/sia-server
    ExecStart=/usr/bin/python3 /home/pi/Scripts/sia-server/sia-server.py
    Restart=on-failure
    RestartSec=5s
    [Install]
    WantedBy=multi-user.target
    ```
    > **Note:** You may need to add firewall rules (e.g., via `ExecStartPre=` & `ExecStopPost=`). If your firewall commands require root, you may need to remove or comment out the `User=pi` directive.
3.  **Enable and Start:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable sia-server.service
    sudo systemctl start sia-server.service
    ```
4.  **Manage:**
    -   **Check status & recent logs:** `sudo systemctl status sia-server.service`
    -   **Stop the service:** `sudo systemctl stop sia-server.service`
    -   **Start the service:** `sudo systemctl start sia-server.service`
    -   **Restart the service:** `sudo systemctl restart sia-server.service`
    -   **View live logs:** `journalctl -u sia-server.service -f` (if not logging to a file) or `tail -f /path/to/your/log/file.log` (if logging to a file).

### For Windows

#### Manual Start (for testing)
> **Note:** Set `LOG_TO = Screen` in `sia-server.conf` to see live events.
```powershell
cd C:\path\to\your\sia-server
python sia-server.py
```
Press `Ctrl+C` to stop.

#### As a Service (Recommended)
> **Note:** Set `LOG_TO = File` in `sia-server.conf` to keep a persistent log.
1.  Download [**NSSM**](https://github.com/dkxce/NSSM/releases).
2.  Open a Command Prompt **as an Administrator**.
3.  Run the installer: `C:\path\to\nssm.exe install SIA-Server`
4.  In the GUI that pops up:
    -   **Path:** Browse to your Python executable (e.g., `C:\Python312\python.exe`).
    -   **Startup directory:** Browse to your script folder.
    -   **Arguments:** `sia-server.py`
5.  Click **Install service**. You can now manage it from the Windows Services app (`services.msc`).

## Security & Privacy Guidelines
Please read these guidelines carefully.

**1. Local Network Communication (Panel to Server)**

The communication between your alarm panel and this server is **unencrypted**. Run it on a trusted local network (LAN).

> **Warning:** Do not expose the server's listening ports directly to the public internet. If you must, use a **VPN** (e.g., WireGuard).

**2. Notification Privacy (Server to ntfy.sh)**

-   **Transport Security:** Communication to `ntfy.sh` uses **HTTPS** and is secure.
-   **Topic Privacy:** ntfy.sh topics are public by default. To secure them:
    -   **Use a long, unguessable topic name.**
    -   **Use a private, access-controlled topic.** You can get one by subscribing to `ntfy.sh Pro` or by self-hosting your own `ntfy.sh` server. This server fully supports authentication via the `NTFY_AUTH` settings.
    -   **Consider a generic Site Name** that cannot be linked to your address.
    -   Alternatively: **Subscribe to NTFY.sh PRO** to setup private channels with authentication.
    -   Alternatively: **Host NTFY yourself** to be able to setup private channels free of charge (Requires a machine with public ip)

**Disclaimer:** You are ultimately responsible for securing your own setup.

## Acknowledgments
-   This project was developed through a collaborative effort with Anthropic's AI assistant, Claude.
-   The initial socket server structure was inspired by the [nimnull/sia-server](https://github.com/nimnull/sia-server) project.
-   Some protocol information was found in [dklemm/FlexSIA2MQTT](https://github.com/dklemm/FlexSIA2MQTT) project.

## License
This project is licensed under the MIT License.
