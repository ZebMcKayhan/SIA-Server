# Honeywell Galaxy SIA Notification Server

A lightweight, self-hosted Python server to receive proprietary SIA protocol messages from Honeywell Galaxy Flex alarm systems and send rich, prioritized push notifications via [ntfy.sh](https://ntfy.sh/).

This project was created to replace the discontinued free push notification service, giving users full control over their alarm notifications without ongoing costs.

This was developed on a Honeywell Galaxy Flex 20 alarm system. It is quite possible that it will work for other Honeywell Galaxy alarm systems, but this has not been tested.

> **IMPORTANT SECURITY NOTICE**
> The communication between the alarm panel and this server is **unencrypted**. This server is designed to be run on a trusted local network only. Please read the full [Security & Privacy Guidelines](#security--privacy-guidelines) before installation.

## Features

-   **Self-Hosted:** Runs on any local Windows or Linux machine, like a Raspberry Pi.
-   **Real-time Notifications:** Instantly forwards alarm events to your devices.
-   **Prioritized Alerts:** Uses ntfy.sh priorities to distinguish between urgent alarms (burglary, fire) and routine events (arm/disarm, tests).
-   **Advanced Notification Routing:** Route notifications for different accounts to different ntfy.sh topics, each with its own authentication (Bearer Token or User/Pass).
-   **Robust Protocol Handling:** Correctly parses the multi-message protocol used by Galaxy Flex panels, including handling multiple events in a single connection.
-   **Broad SIA Level Support:** The flexible parser can correctly handle event data from SIA Levels 0, 1, 2, and 3.
-   **Optional Heartbeat Server:** Includes a separate, optional server to correctly handle the proprietary Honeywell "IP Check" heartbeat, ensuring full panel compatibility without generating errors.
-   **Character Encoding Fixes:** Decodes the proprietary character set used by Galaxy panels to correctly display special characters (e.g., Å, Ä, Ö).
-   **Highly Configurable:** Most user settings are in a simple `sia-server.conf` file, with advanced settings in `defaults.py`.

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
├── sia-server.conf         # User configuration file.
├── defaults.py             # Advanced settings and constants.
├── configuration.py        # Loads and validates all configuration.
├── notification.py         # Handles formatting and sending of notifications.
├── ip_check.py             # Optional subprocess for answering heartbeats.
├── README.md               # This file.
└── galaxy/
    ├── README.md           # Technical description of the protocol.  
    ├── parser.py           # Handles parsing of the Galaxy SIA protocol.
    └── constants.py        # Constants used in the SIA protocol.
```

## Installation & Setup (Linux)

### 1. Download the Code
You have two options for downloading the code.

**Option A: Download the Latest Stable Release (Recommended)**
1.  Go to the [Releases page](https://github.com/ZebMcKayhan/SIA-Server/releases) on GitHub.
2.  Under the latest release, download the `Source code (zip)` file.
3.  Unzip the file on your server.

**Option B: Clone via Git (for developers)**
This will get you the very latest development version from the `main` branch.
```bash
git clone https://github.com/ZebMcKayhan/SIA-Server.git sia-server
cd sia-server
```

### 2. Install Dependencies
The script relies on `requests` for sending notifications and `uvloop` (optional on Linux) for high-performance networking. Install them using `apt`.
```bash
sudo apt update
sudo apt install python3-requests python3-uvloop
```
> **Note:** It is recommended to use `apt` instead of `pip` on Raspberry Pi OS / Debian systems to avoid environment conflicts.

### 3. Configure Your Alarm Panel
Log into your Galaxy Flex panel's installer menu and configure the Ethernet module to send SIA notifications to your server:
-   **ARC IP Address:** The IP address of the machine running `sia-server.py` (e.g., `192.168.128.10`).
-   **ARC Port:** The port configured in `sia-server.conf` (default is `10000`).
-   **Protocol:** SIA (Level 0-3 are supported) Level 3 is recommended for best notification details.
-   **Account Number:** Your 4 or 6-digit alarm account number (SIA level 3 requires 6-digit).
-   **Encryption:** Must be set to **Off**. The proprietary encryption is not supported.

### 4. Get the notification app and subscribe to a topic
Follow [this link](https://docs.ntfy.sh/#step-1-get-the-app) and follow the instructions for downloading the app and subscribe to a topic. The topic name you choose will be the last part of the address you put in ```sia-server.conf``` file

### 5. Configure the Server
Edit the `sia-server.conf` file to match your setup. There are several examples in the file to follow.
```bash
nano sia-server.conf
```

## Configuration Explained
The primary configuration is done in `sia-server.conf`. This file is designed to be user-friendly and not sensitive to Python syntax. Advanced settings can be found in `defaults.py`.

-   **Site Sections (`[012345]`):** Each site is defined by a section. The number in brackets links to the panel account number. Inside each section:
    -   `SITE_NAME`: The site name to be linked to this panel.
    -   `NTFY_ENABLED`: Set to `Yes` or `No`.
    -   `NTFY_TOPIC`: The URL for the ntfy.sh topic.
    -   `NTFY_TITLE`: The title for notifications from this site.
    -   `NTFY_AUTH`: Can be `None`, `Token`, or `Userpass`. If not `None`, you must also provide the corresponding `NTFY_TOKEN` or `NTFY_USER`/`NTFY_PASS` keys.
-   **`[Default]` Section:** A special section for any events from account numbers not specifically listed. Site name will always be the account number.
-   **`[SIA-Server]` & `[IP-Check]` Sections:** Configure the ports and addresses for the main server and the optional heartbeat server.
-   **`[Logging]` Section:** Control the log level and whether output goes to the `Screen` or a `File`.

## Security & Privacy Guidelines
Please read these guidelines carefully to ensure you are using this software securely.

**1. Local Network Communication (Alarm Panel to Server)**

The communication between your alarm panel and the `sia-server` is **unencrypted**. Therefore, it is strongly recommended to run this server on the same trusted, local network (LAN) as your alarm panel.

> **Warning:** Do not expose the `sia-server`'s listening port directly to the public internet. Doing so would allow an attacker to potentially monitor when your alarm is armed or disarmed, or to send fake alarm/disarm events.

If you plan on hosting this server on a cloud machine, you **must** secure the connection using a **VPN (Virtual Private Network)** like WireGuard or OpenVPN.

**2. Notification Privacy (Server to ntfy.sh)**

-   **Transport Security:** The communication from the server to ntfy.sh uses **HTTPS**, so it is encrypted in transit.
-   **Topic Privacy:** By default, ntfy.sh topics are public. To secure them:
    -   **Use a long, unguessable topic name.** Treat it like a password.
    -   **Use a private topic** with authentication (supported via the `NTFY_AUTH` settings in `sia-server.conf`).
    -   **Consider a generic Site Name** that cannot be linked to your address.

**Disclaimer:** You are ultimately responsible for securing your own setup.

## Usage

### For Testing (Manual Start)
You can run the server directly from your terminal.
```bash
python3 sia-server.py
```
Press `Ctrl+C` to stop the server.

### As a Service (Recommended for Production)
Setting up a `systemd` service ensures the server runs reliably in the background.

**1. Create the Service File:**
```bash
sudo nano /etc/systemd/system/sia-server.service
```
**2. Paste this content.** **IMPORTANT:** You must change the paths in `WorkingDirectory` and `ExecStart` to match your installation.
```ini
[Unit]
Description=Galaxy SIA Alarm Server
After=network.target

[Service]
Type=simple
User=pi

# IMPORTANT: Change this path
WorkingDirectory=/home/pi/Scripts/sia-server

# IMPORTANT: Change this path
ExecStart=/usr/bin/python3 /home/pi/Scripts/sia-server/sia-server.py

Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```
> **Note:** Depending on your system, you may need to add firewall rules. This can typically be done via `ExecStartPre=`. If your firewall commands require root, you may need to remove or comment out the `User=pi` directive.

**3. Enable and Start the Service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable sia-server.service
sudo systemctl start sia-server.service
```

### Managing the Service
-   **Check status & recent logs:** `sudo systemctl status sia-server.service`
-   **Stop the service:** `sudo systemctl stop sia-server.service`
-   **Start the service:** `sudo systemctl start sia-server.service`
-   **Restart the service:** `sudo systemctl restart sia-server.service`
-   **View live logs:** `journalctl -u sia-server.service -f` (if not logging to a file) or `tail -f /path/to/your/log/file.log`.

## Installation & Setup (Windows)

1.  Install Python 3 from the [official Python website](https://www.python.org/).
2.  Install dependencies: Open PowerShell and run:
    ```powershell
    pip install requests pyopenssl cryptography ndg-httpsclient
    ```
    > **Note:** The extra packages are highly recommended to avoid HTTPS issues on Windows.
3.  Configure `sia-server.conf`: Use standard Windows paths for `LOG_FILE`, e.g., `C:\Logs\sia-server.log`.
4.  You may need to add inbound firewall rules for the ports (`10000`, `10001`).
5.  Run manually (`python sia-server.py`) or set it up as a service using a tool like **NSSM**.

### As a Service on Windows (using NSSM)
1.  Download **NSSM**.
2.  Open a Command Prompt **as an Administrator**.
3.  Run the NSSM installer:
    ```powershell
    C:\path\to\nssm.exe install SIA-Server
    ```
4.  A GUI window will pop up. Fill in the tabs:
    -   **Application Tab:**
        -   **Path:** Browse to your Python executable (e.g., `C:\Python312\python.exe`).
        -   **Startup directory:** Browse to the folder containing your script (e.g., `C:\path\to\your\sia-server`).
        -   **Arguments:** `sia-server.py`
    -   **Details Tab:** Set a Display Name and Description.
5.  Click **Install service**.

You can now manage it from the Windows Services app (`services.msc`) or via the `nssm` command line (e.g., `nssm start SIA-Server`).

## Acknowledgments
-   This project was developed through a collaborative effort with Anthropic's AI assistant, Claude.
-   The initial socket server structure was inspired by the [nimnull/sia-server](https://github.com/nimnull/sia-server) project.

## License
This project is licensed under the MIT License.
