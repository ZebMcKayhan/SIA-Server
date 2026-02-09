# Honywell Galaxy SIA Notification Server

A lightweight, self-hosted Python server to receive proprietary SIA protocol messages from Honeywell Galaxy Flex alarm systems and send rich, prioritized push notifications via [ntfy.sh](https://ntfy.sh/).

This project was created to replace the discontinued free push notification service, giving users full control over their alarm notifications without ongoing costs.

This was developed on a Honywell Galaxy Flex 20 alarm system. It is quite possible that it will work for other Honywell Galaxy alarm system but it has not been tested.

## Features

-   **Self-Hosted:** Runs on any local Linux machine, like a Raspberry Pi, it should also run on Windows but it has not been tested.
-   **Real-time Notifications:** Instantly forwards alarm events to your devices.
-   **Prioritized Alerts:** Uses ntfy.sh priorities to distinguish between urgent alarms (burglary, fire) and routine events (arm/disarm, tests).
-   **Multiple sites:** Ability to map different account numbers to different notification topics.
-   **Robust Protocol Handling:** Correctly parses the multi-message protocol used by Galaxy Flex panels, including handling multiple events in a single connection.
-   **Character Encoding Fixes:** Decodes the proprietary character set used by Galaxy panels to correctly display special characters (e.g., Å, Ä, Ö).
-   **Highly Configurable:** All settings, including account names, notification priorities, and logging, are in a single `config.py` file.

## Prerequisites

-   A Honeywell Galaxy Flex alarm system with an Ethernet module (A083-00-10 or E080-4).
-   A Linux (or Windows) machine on the same network as the alarm system (a Raspberry Pi running OMV or Raspberry Pi OS is perfect).
-   Python 3.
-   The `python3-requests` and the optional `python3-uvloop` package.

## File Structure

The project is structured to separate the server logic, protocol parsing, and configuration.

sia-server.py # The main server application

config.py # All user settings are here!

notification.py # Handles formatting and sending of notifications

galaxy/parser.py # Handles parsing of the Galaxy SIA protocol

galaxy/costants.py # Constants used in SIA protocol


## Installation & Setup (Linux)

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
-  Encryption: Off (for notifications) (encryption is not supported, not known)

## Configure the Server
Edit the `config.py` file to match your setup. This is the only file you need to modify.
```bash
nano config.py
```

### Configuration Explained
-  `LISTEN_ADDR` & `LISTEN_PORT`: The IP and port the server listens on. `0.0.0.0` allows it to accept connections from any device on your network.
-  `ACCOUNT_SITES`: Map your alarm's account number to a friendly site name. If not mapped the script will send the account number as it is.
```python
ACCOUNT_SITES = {
    '090909': 'Main House',
    '123456': 'Summer House', # Example for a second site
}
```
-  `NOTIFICATION_TITLE`: The title of your push notifications (e.g., "Galaxy FLEX", "Home Alarm").
-  `NTFY_ENABLED` & `NTFY_URL`: Set `NTFY_ENABLED` to `True` and change `NTFY_TOPICS` to your default ntfy.sh topic URL. You may also map different account numbers to different ntfy topics, see examples in the file.
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
Note: Depending on yor system you may need to add firewall rules in here, typically via `ExecStartPre=` and `ExecStop=` and if so, you may need to remove or comment the `User=` directive so it runs as root.

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


## Installation & Setup (Windows)
This have not been tested, but there is nothing known to me that would prevent this from working.
1. Download and install the latest Python 3 from the official Python website. Make sure to check the box that says "Add Python to PATH" during installation.
2. Install Dependencies:
Open a Command Prompt `cmd` or PowerShell and use `pip` (Python's package installer, which comes with the Windows installer).
```bash
pip install requests
```
(You would not install `uvloop` on Windows).

3. Configure config.py:
Use same procedure as for Linux, but when selecting log file path you will need to escape the backslash, like this:
```bash
LOG_FILE = 'C:\\Temp\\sia-server.log'
```
4. Running the Server on Windows
You have two main options, similar to Linux: manual testing or running as a background service.


### For Testing (Manual Start)

Just open a Command Prompt, navigate to your script's directory, and run it.
```bash
cd C:\path\to\your\sia-server
python sia-server.py
```
The server will run in that window. Pressing `Ctrl+C` will stop it.

### As a Service (Recommended for Production):

Windows doesn't have `systemd`. The equivalent is "Windows Services". Making a Python script a true Windows Service is more complex, but the easiest and most popular way is to use a helper tool.

The Easiest Method is using NSSM (the Non-Sucking Service Manager)
1. Download NSSM. It's a small, free command-line tool.
2. Place `nssm.exe` somewhere accessible (e.g., C:\NSSM).
3. Open a Command Prompt as an Administrator.
4. Run the NSSM installer for your service:
```bash
C:\NSSM\nssm.exe install SIA-Server
```
5. A GUI window will pop up. Fill in the tabs:
- Application Tab:
  - Path: Browse to your Python executable (e.g., `C:\Python312\python.exe`).
  - Startup directory: Browse to the folder containing your script (e.g., `C:\path\to\your\sia-server`).
  - Arguments: `sia-server.py`
- Details Tab:
  - You can set a Display Name and Description.
- Log on Tab:
  - Usually, you can leave this as Local System account.
6. Click Install service.
Now you can manage it from the Windows Services app (services.msc) or via the command line:
```bash
# Start the service
nssm start SIA-Server

# Stop the service
nssm stop SIA-Server

# Check status
nssm status SIA-Server
```

# Acknowledgments

-  This project was developed through a collaborative effort with Anthropic's AI assistant, Claude.
-  The initial socket server structure was inspired by the nimnull/sia-server project.

# License
This project is licensed under the MIT License.

