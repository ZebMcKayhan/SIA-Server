# Honeywell Galaxy SIA Notification Server

A lightweight, self-hosted Python server to receive proprietary SIA protocol messages from Honeywell Galaxy Flex alarm systems and send rich, prioritized push notifications via [ntfy.sh](https://ntfy.sh/).

This project was created to replace the discontinued free push notification service, giving users full control over their alarm notifications without ongoing costs.

This was developed on a Honeywell Galaxy Flex 20 alarm system. It is highly likely that it will work for other Honeywell Galaxy alarm systems, but this has not been tested.

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
-   **Highly Configurable:** Most settings are in a simple `sia-server.conf` file, with advanced settings in `defaults.py`.

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

1.  **Install Python (if needed):** Most modern Linux systems come with Python 3 pre-installed. You can check with `python3 --version`.
2.  **Install Dependencies:** Use `apt` to install the required packages. `uvloop` is an optional performance enhancement.
    ```bash
    sudo apt update
    sudo apt install python3-requests python3-uvloop
    ```

#### For Windows

1.  **Install Python:** Download and install the latest Python 3 from the [official Python website](https://www.python.org/). **Important:** During installation, make sure to check the box that says "Add Python to PATH".
2.  **Install Dependencies:** Open a **PowerShell** or **Command Prompt** and use `pip`. It is strongly recommended to use `python -m pip` to ensure you are installing packages for the correct Python interpreter.
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

Log into your Galaxy Flex panel's installer menu and configure the Ethernet module to send SIA notifications to your server:

-   **ARC IP Address:** The IP address of the machine running `sia-server.py` (e.g., `192.168.128.10`).
-   **ARC Port:** The port for the `[SIA-Server]` configured in `sia-server.conf` (default is `10000`).
-   **Protocol:** SIA (Levels 0-3 are supported). Level 3 is recommended for the most detailed notifications.
-   **Account Number:** Your 4 or 6-digit alarm account number.
-   **Encryption:** Must be set to **Off**. The proprietary encryption is not supported.

### Step 5: Configure the Server

Change your configuration file from the provided example and edit it to match your setup.

```bash
# On Linux
nano sia-server.conf

# On Windows, just edit the sia-server.conf file.
```

Refer to the **Configuration Explained** section below for details on each setting.

## Configuration Explained

The primary configuration is done in `sia-server.conf`. Advanced settings can be found in `defaults.py`.

-   **Site Sections (`[012345]`):** Each site is defined by a section where the header is the panel's unique **Account Number**. Inside each section:
    -   `SITE_NAME`: A friendly name for the site (e.g., "Main House"). If omitted, the account number will be used.
    -   `NTFY_ENABLED`: Set to `Yes` or `No`.
    -   `NTFY_TOPIC`: The full URL for the ntfy.sh topic for this site.
    -   `NTFY_TITLE`: The title for notifications from this site (e.g., "Galaxy FLEX").
    -   `NTFY_AUTH`: Can be `None`, `Token`, or `Userpass` for private topics. If not `None`, provide the corresponding `NTFY_TOKEN` or `NTFY_USER`/`NTFY_PASS` keys.
-   **`[Default]` Section:** A special section for events from account numbers not specifically listed.
-   **`[SIA-Server]` & `[IP-Check]` Sections:** Configure the ports and addresses for the main server and the optional heartbeat server.
-   **`[Logging]` Section:** Control the log level and whether output goes to the `Screen` or a `File`.

## Usage

### For Linux

#### Manual Start (for testing)
Run the server directly from your terminal to watch the logs in real-time.
```bash
cd /path/to/your/sia-server
python3 sia-server.py
```
Press `Ctrl+C` to stop.

#### As a Service (Recommended)
Using `systemd` ensures the server runs reliably in the background.

1.  **Create the Service File:**
    ```bash
    sudo nano /etc/systemd/system/sia-server.service
    ```
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
3.  **Enable and Start:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable sia-server.service
    sudo systemctl start sia-server.service
    ```
4.  **Manage:**
    -   Check status: `sudo systemctl status sia-server.service`
    -   View live logs: `journalctl -u sia-server.service -f`

### For Windows

#### Manual Start (for testing)
Open PowerShell, navigate to your script's directory, and run it.
```powershell
cd C:\path\to\your\sia-server
python sia-server.py
```
Press `Ctrl+C` to stop.

#### As a Service (Recommended)
A popular tool for this is NSSM (the Non-Sucking Service Manager).

1.  Download **NSSM**.
2.  Open a Command Prompt **as an Administrator**.
3.  Run the NSSM installer:
    ```powershell
    C:\path\to\nssm.exe install SIA-Server
    ```
4.  In the GUI that pops up:
    -   **Path:** Browse to your Python executable (e.g., `C:\Python312\python.exe`).
    -   **Startup directory:** Browse to your script folder.
    -   **Arguments:** `sia-server.py`
5.  Click **Install service**.
6.  You can now manage it from the Windows Services app (`services.msc`).

## Security & Privacy Guidelines
Please read these guidelines carefully.

**1. Local Network Communication (Panel to Server)**

The communication between your alarm panel and the `sia-server` is **unencrypted**. Run this server on the same trusted, local network (LAN) as your alarm panel.

> **Warning:** Do not expose the server's listening ports directly to the public internet.

If you host this server on a cloud machine, you **must** secure the connection using a **VPN** (e.g., WireGuard).

**2. Notification Privacy (Server to ntfy.sh)**

-   **Transport Security:** Communication to `ntfy.sh` uses **HTTPS** and is secure in transit.
-   **Topic Privacy:** ntfy.sh topics are public by default. To secure them:
    -   **Use a long, unguessable topic name.** Treat it like a password.
    -   **Consider a generic Site Name** that cannot be linked to your address.
    -   **Use a private, access-controlled topic.** For the highest level of security, use a topic that requires authentication. You can get an access-controlled topic in two ways:
        1.  **Subscribe to `ntfy.sh Pro`** on their managed service.
        2.  **Self-host your own `ntfy.sh` server** where you can configure access control for free.
        > This server fully supports sending to private topics using either Token or User/Pass authentication via the `NTFY_AUTH` settings in `sia-server.conf`.

**Disclaimer:** You are ultimately responsible for securing your own setup.

## Acknowledgments
-   This project was developed through a collaborative effort with Anthropic's AI assistant, Claude.
-   The initial socket server structure was inspired by the [nimnull/sia-server](https://github.com/nimnull/sia-server) project.

## License
This project is licensed under the MIT License.
