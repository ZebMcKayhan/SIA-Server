# Galaxy SIA Notification Server

A lightweight, self-hosted Python server to receive proprietary SIA protocol messages from Honeywell Galaxy Flex alarm systems and send rich, prioritized push notifications via [ntfy.sh](https://ntfy.sh/).

This project was created to replace the discontinued free push notification service, giving users full control over their alarm notifications without ongoing costs.

## Features

-   **Self-Hosted:** Runs on any local Linux machine, like a Raspberry Pi.
-   **Real-time Notifications:** Instantly forwards alarm events to your devices.
-   **Prioritized Alerts:** Uses ntfy.sh priorities to distinguish between urgent alarms (burglary, fire) and routine events (arm/disarm, tests).
-   **Robust Protocol Handling:** Correctly parses the multi-message protocol used by Galaxy Flex panels, including handling multiple events in a single connection.
-   **Character Encoding Fixes:** Decodes the proprietary character set used by Galaxy panels to correctly display special characters (e.g., Å, Ä, Ö).
-   **Highly Configurable:** All settings, including account names, notification priorities, and logging, are in a single `config.py` file.

## Prerequisites

-   A Honeywell Galaxy Flex alarm system with an Ethernet module (E080-4).
-   A Linux machine on the same network as the alarm system (a Raspberry Pi running OMV or Raspberry Pi OS is perfect).
-   Python 3.
-   The `python3-requests` and the `python3-uvloop` package.

## File Structure

The project is structured to separate the server logic, protocol parsing, and configuration.

sia-server.py # The main server application

config.py # All user settings are here!

galaxy/parser.py # Handles parsing of the Galaxy SIA protocol

galaxy/notification.py # Handles formatting and sending of notifications


## Installation & Setup

### 1. Clone the Repository

Clone this project to a directory on your Linux machine (e.g., `/home/pi/Scripts/sia-server`).

```bash
git clone https://github.com/ZebMcKayhan/SIA-Server.git sia-server
cd sia-server
```

## Install Dependencies

The script relies on `requests` for sending notifications and `uvloop` for high-performance networking. Install them using `apt`:
```bash
sudo apt update
sudo apt install python3-requests python3-uvloop
```
Note: It is recommended to use `apt` instead of `pip` on Raspberry Pi OS / Debian systems to avoid environment conflicts.

## Configure Your Alarm Panel

Log into your Galaxy Flex panel's installer menu and configure the Ethernet module to send SIA notifications to your server:

-  ARC IP Address: The IP address of the machine running `sia-server.py` (e.g., `192.168.128.10`).
-  ARC Port: The port configured in `config.py` (default is `10000`).
-  Protocol: SIA (Level 2 or 3) - Level 3 is recommended.
-  Account Number: Your 4 or 6-digit alarm account number.

## Configure the Server
Edit the `config.py` file to match your setup. This is the only file you need to modify.
```bash
nano config.py
```

### Configuration Explained
-  `LISTEN_ADDR` & `LISTEN_PORT`: The IP and port the server listens on. `0.0.0.0` allows it to accept connections from any device on your network.
-  `ACCOUNT_SITES`: IMPORTANT! Map your alarm's account number to a friendly site name.
```python
ACCOUNT_SITES = {
    '090909': 'Main House',
    '123456': 'Summer House', # Example for a second site
}
```
-  `NOTIFICATION_TITLE`: The title of your push notifications (e.g., "Galaxy FLEX", "Home Alarm").
-  `NTFY_ENABLED` & `NTFY_URL`: Set `NTFY_ENABLED` to `True` and change `NTFY_URL` to your ntfy.sh topic URL.
-  `EVENT_PRIORITIES`: Customize the priority for different events. Any event code not listed here will default to `DEFAULT_PRIORITY`. This is pre-configured with safe defaults.
-  `UNKNOWN_CHAR_MAP`: If your alarm uses special characters that don't display correctly, you can add their byte-to-character mappings here. The common Swedish characters are already included.
-  `LOGGING`: For normal use, you can leave these as they are. For debugging, you can change `LOG_LEVEL` to `DEBUG` and set `LOG_TO_FILE` to `True` to log to a file.

# Usage
### For Testing (Manual Start)
You can run the server directly from your terminal to watch the logs in real-time.
```bash
python3 sia-server.py
```
Press `Ctrl+C` to stop the server.

### As a Service (Recommended for Production)
Setting up a `systemd` service is the best way to ensure the server runs reliably in the background and starts automatically on boot.
1. Create the Service File:
```bash
sudo nano /etc/systemd/system/sia-server.service
```
2. Paste this content. IMPORTANT: You must change the paths in `WorkingDirectory` and `ExecStart` to match where you cloned the repository.
```bash
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
3. Enable and Start the Service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sia-server.service
sudo systemctl start sia-server.service
```

### Managing the Service

-  Check status & recent logs: `sudo systemctl status sia-server.service`
-  Stop the service: `sudo systemctl stop sia-server.service`
-  Start the service: `sudo systemctl start sia-server.service`
-  Restart the service: `sudo systemctl restart sia-server.service`
-  View live logs: `journalctl -u sia-server.service -f` (if not logging to a file) or `tail -f /path/to/your/log/file.log` (if logging to a file).

# Acknowledgments

-  This project was developed through a collaborative effort with Anthropic's AI assistant, Claude.
-  The initial socket server structure was inspired by the nimnull/sia-server project.

# License
This project is licensed under the MIT License.

