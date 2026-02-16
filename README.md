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
-   **Highly Configurable:** All settings, including account names, notification priorities, and logging, are in a single `config.py` file.

## Prerequisites

-   A Honeywell Galaxy Flex alarm system with an Ethernet module (A083-00-10 or E080-4).
-   A Linux or Windows machine on the same network as the alarm system (a Raspberry Pi running Raspberry Pi OS is perfect).
-   Python 3.
-   The `python3-requests` package and the optional `python3-uvloop` package (for Linux).

## File Structure

The project is structured to separate the server logic, protocol parsing, and configuration.
```
.
├── sia-server.py           # The main server application
├── config.py               # All user settings are here!
├── notification.py         # Handles formatting and sending of notifications
├── ip_check.py             # Subprocess for answering the panel IP-Checks (Heartbeats)
├── README.md               # Installation and usage instructions.
└── galaxy/
    ├── README.md           # Description of the SIA over TCP protocol.  
    ├── parser.py           # Handles parsing of the Galaxy SIA protocol
    └── constants.py        # Constants used in the SIA protocol
```

## Installation & Setup (Linux)

### 1. Clone the Repository
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
The script relies on `requests` for sending notifications and `uvloop` (optional for Linux) for high-performance networking. Install them using `apt`.
```bash
sudo apt update
sudo apt install python3-requests python3-uvloop
```
> **Note:** It is recommended to use `apt` instead of `pip` on Raspberry Pi OS / Debian systems to avoid environment conflicts.

### 3. Configure Your Alarm Panel
Log into your Galaxy Flex panel's installer menu and configure the Ethernet module to send SIA notifications to your server:
-   **ARC IP Address:** The IP address of the machine running `sia-server.py` (e.g., `192.168.128.10`).
-   **ARC Port:** The port configured in `config.py` (default is `10000`).
-   **Protocol:** SIA (Level 2 or 3 are supported).
-   **Account Number:** Your 4 or 6-digit alarm account number.
-   **Encryption:** Must be set to **Off**. The proprietary encryption is not supported.

### 4. Configure the Server
Edit the `config.py` file to match your setup. This is the only file you need to modify.
```bash
nano config.py
```

## Configuration Explained
-   `LISTEN_ADDR` & `LISTEN_PORT`: The IP and port the main SIA event server listens on.
-   `IP_CHECK_ENABLED`, `IP_CHECK_ADDR`, `IP_CHECK_PORT`: (Optional) Settings to enable and configure the separate heartbeat server for compatibility with the panel's "IP Check" feature.
-   `ACCOUNT_SITES`: Map your alarm's account number to a friendly site name. If an account is not mapped, the script will use the account number as the site name.
    ```python
    ACCOUNT_SITES = {
        '090909': 'Main House',
        '123456': 'Summer House', # Example for a second site
    }
    ```
-   `NOTIFICATION_TITLE`: The title of your push notifications (e.g., "Galaxy FLEX", "Home Alarm").
-   `NTFY_TOPICS`: Configure your ntfy.sh notification destinations. This flexible dictionary allows you to set up a simple 'default' topic for all alerts, or define specific topics for each account number. You can also configure authentication (Bearer Token or User/Pass) on a per-topic basis for private channels.
-   `EVENT_PRIORITIES`: Customize the priority for different events. Any event code not listed here will default to `DEFAULT_PRIORITY`. This is pre-configured with safe defaults.
-   `UNKNOWN_CHAR_MAP`: If your alarm uses special characters that don't display correctly, you can add their byte-to-character mappings here. The common Swedish characters are already included.
-   `LOGGING`: Configure logging level and output for the main SIA server.

## Security & Privacy Guidelines
Please read these guidelines carefully to ensure you are using this software securely.

**1. Local Network Communication (Alarm Panel to Server)**

The communication between your alarm panel and the `sia-server` is **unencrypted**. Therefore, it is strongly recommended to run this server on the same trusted, local network (LAN) as your alarm panel.

> **Warning:** Do not expose the `sia-server`'s listening port directly to the public internet. Doing so would allow an attacker to potentially monitor when your alarm is armed or disarmed, or to send fake alarm/disarm events.

If you plan on hosting this server on a cloud machine for yourself or for friends, you **must** secure the connection using a **VPN (Virtual Private Network)** like WireGuard or OpenVPN. The alarm panel should connect to the server through the secure VPN tunnel, not over the public internet.

**2. Notification Privacy (Server to ntfy.sh)**

-   **Transport Security:** The communication from the server to ntfy.sh uses **HTTPS**, so the content of your notifications is encrypted and secure in transit.
-   **Topic Privacy:** By default, ntfy.sh topics are public. Anyone who knows your topic name can subscribe to your notifications. To secure this:
    -   **Use a long, unguessable topic name.** Treat your ntfy.sh topic name like a password. Instead of `my-home-alarm`, use a randomly generated string like `alarm-skUHvisapP2J382MDI2`.
    -   **Consider your Site Name.** For added privacy, you can choose a generic `site_name` in your `config.py` (e.g., "Site A") that cannot be easily linked back to your physical address.
    -   **Alternatively, host ntfy.sh yourself** By hosting the notification server yourself you could secure your topics.
    -   **Alternatively, purchase ntfy.sh pro** By paying a subscription you can use login or token to create and access private topics. `config.py` and `notification.py` is prepared for this already.

**Disclaimer:** By following these guidelines, you can significantly improve the security and privacy of your notification system. However, you are ultimately responsible for securing your own setup.

## Usage

### For Testing (Manual Start)
You can run the server directly from your terminal to watch the logs in real-time.
```bash
python3 sia-server.py
```
Press `Ctrl+C` to stop the server.

### As a Service (Recommended for Production)
Setting up a `systemd` service is the best way to ensure the server runs reliably in the background and starts automatically on boot.

**1. Create the Service File:**
```bash
sudo nano /etc/systemd/system/sia-server.service
```
**2. Paste this content.** **IMPORTANT:** You must change the paths in `WorkingDirectory` and `ExecStart` to match where you cloned the repository.
```ini
[Unit]
Description=Galaxy SIA Alarm Server
After=network.target

[Service]
Type=simple
User=pi

# IMPORTANT: Change this path to where your sia-server.py is located
WorkingDirectory=/home/pi/Scripts/sia-server

# IMPORTANT: Change this path to your Python interpreter and script
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
-   **View live logs:** `journalctl -u sia-server.service -f` (if not logging to a file) or `tail -f /path/to/your/log/file.log` (if logging to a file).

## Installation & Setup (Windows)

The optional `uvloop` dependency is not available on Windows, and the server will automatically fall back to the standard `asyncio` loop. There are some issues with SSL (HTTPS) with windows, so some additional packages are required for HTTPS to work properly.

1.  Download and install the latest Python 3 from the [official Python website](https://www.python.org/). Make sure to check the box that says "Add Python to PATH" during installation.
2.  Install Dependencies: Open a Command Prompt (`cmd`) or PowerShell and use `pip`.
    ```powershell
    pip install requests pyopenssl cryptography ndg-httpsclient
    ```
    >**Note:** The extra packages are to update SSL to the standard ntfy.sh uses to avoid HTTPS issues. They may not be needed for your particular system.
    >
    >**Note2:** Depending on how your windows is setup on the network (trusted/public) you may need to add an inbound firewall rule to accept incooming connection on port 10000, 10001.
3.  Configure `config.py`: Use the same procedure as for Linux, but when selecting a log file path, you will need to use Windows-style paths with escaped backslashes.
    ```python
    LOG_FILE = 'C:\\Temp\\sia-server.log'
    ```
4.  Running the Server on Windows: You have two main options, similar to Linux.

### For Testing (Manual Start)
Just open a Command Prompt, navigate to your script's directory, and run it.
```powershell
cd C:\path\to\your\sia-server
python sia-server.py
```
Pressing `Ctrl+C` will stop the server.

### As a Service (Recommended for Production)
Windows uses "Services" instead of `systemd`. A popular tool for this is NSSM (the Non-Sucking Service Manager).

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

You can now manage it from the Windows Services app (`services.sc`) or via the `nssm` command line (e.g., `nssm start SIA-Server`).

## Acknowledgments
-   This project was developed through a collaborative effort with Anthropic's AI assistant, Claude.
-   The initial socket server structure was inspired by the [nimnull/sia-server](https://github.com/nimnull/sia-server) project.

## License
This project is licensed under the MIT License.

