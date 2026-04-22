# Honeywell Galaxy SIA Notification Server

SIA-Server is a lightweight, self-hosted Python service that receives SIA protocol messages from Honeywell Galaxy Flex alarm systems and forwards them as rich, prioritized push notifications via [ntfy.sh](https://ntfy.sh/).

It was created as a replacement for the discontinued free Honeywell push notification service, allowing users to regain full control over their alarm alerts without ongoing subscription costs.

This project was developed and tested on a Honeywell Galaxy Flex 20. It is likely compatible with other Honeywell Galaxy panels, but this has not been verified.

If your Galaxy Flex notifications suddenly stopped working, this project provides a self-hosted alternative.

> **SECURITY NOTICE**
> Please read the full [Security & Privacy Guidelines](#security--privacy-guidelines) before deployment. Both plaintext and encrypted panel communication are supported.

## Features

-   **Self-Hosted:** Runs on any local Windows or Linux machine, like a Raspberry Pi.
-   **Real-time Notifications:** Instantly forwards alarm events to your devices.
-   **Prioritized Alerts:** Uses ntfy.sh priorities to distinguish between urgent alarms and routine events.
-   **Advanced Notification Routing:** Route notifications for different accounts to different ntfy.sh topics, each with its own optional authentication (Bearer Token or User/Pass).
-   **Robust Protocol Handling:** Correctly parses the multi-message protocol used by Galaxy Flex panels.
-   **Broad SIA Level Support:** The flexible parser can correctly handle event data from SIA Levels 0, 1, 2, and 3. Encrypted communication (proprietary RSA+AES handshake) is fully supported.
-   **Optional Heartbeat Server:** Includes an optional server to handle the proprietary Honeywell "IP Check" heartbeat.
-   **Encrypted Communication:** Supports the proprietary Honeywell Galaxy encrypted ARC protocol (RSA-1024 + AES-128). Requires `pycryptodome`. Falls back to plaintext-only mode if not installed.
-   **Character Encoding Fixes:** Decodes the proprietary character set used by Galaxy panels (e.g., Å, Ä, Ö).
-   **Highly Configurable:** Most user settings are in a simple `sia-server.conf` file, with advanced protocol constants located in the `galaxy/` directory.

## Prerequisites

-   A Honeywell Galaxy Flex alarm system with an Ethernet module (e.g., A083-00-10 or E080-4).
-   A Linux or Windows machine on the same network as the alarm system (a Raspberry Pi running Raspberry Pi OS is perfect).
-   Python 3.
-   The `python3-requests` package (required).
-   The `pycryptodome` package (required for encrypted panel communication).
-   The optional `python3-uvloop` package (for Linux, performance enhancement).

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
├── PanelSetup.md           # Panel Configuration help.
├── requirements.txt        # Required python packages.
├── galaxy/
│   ├── __init__.py
│   ├── README.md           # Technical description of the protocol.  
│   ├── parser.py           # Handles parsing of the Galaxy SIA protocol.
│   ├── encryption.py       # Handles encrypted handshake and encrypted packets.
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
    sudo apt install python3-requests python3-uvloop python3-pycryptodome
    ```

#### For Windows
1.  **Install Python:** Download and install the latest Python 3 from the [official Python website](https://www.python.org/). **Important:** During installation, make sure to check the box that says "Add Python to PATH".
2.  **Install Dependencies:** Open a **PowerShell** or **Command Prompt**. It is strongly recommended to use `python -m pip` to ensure you are installing packages for the correct Python interpreter.
    ```powershell
    python -m pip install requests pycryptodome pyopenssl
    ```
    > **Note:** The extra package `pyopenssl` is optional but recommended to avoid potential HTTPS/SSL errors when sending notifications from Windows.

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
-   **Encryption:** Can be set to **On** or **Off**. Encrypted communication is fully supported and recommended. If enabled, ensure `pycryptodome` is installed. (Menu `56.3.3.5`)
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

The primary configuration is done in `sia-server.conf`. This file is designed to be user-friendly and not sensitive to Python syntax. Advanced, technical constants are located in `galaxy/constants.py`.

-   **Site Sections (`[012345]`):** Each site is defined by a section where the header is the panel's unique **Account Number**.
    -   `SITE_NAME`: A friendly name for the site (e.g., "Main House"). If omitted, the account number is used.
    -   `ENABLED`: Controls the connection policy for this account. Accepts `Yes`, `No`, or `Secure`.
        -   `Yes` — Accept both plaintext and encrypted connections (default).
        -   `No` — Reject all connections from this account.
        -   `Secure` — Only accept encrypted connections. Plaintext connections will be rejected.
    -   `NTFY_ENABLED`, `NTFY_TOPIC`, `NTFY_TITLE`: Configure notification delivery for this site.
    -   `NTFY_AUTH`: Set to `None`, `Token`, or `Userpass` for private topics and provide the corresponding `NTFY_TOKEN` or `NTFY_USER`/`NTFY_PASS` keys.

-   **`[Default]` Section:** A special section for events from account numbers not specifically listed.

-   **`[SIA-Server]` & `[IP-Check]` Sections:** Configure the ports and addresses for the main server and the optional heartbeat server.

-   **`[Logging]` Section:** Control the log level and output destination.
    -   `LOG_LEVEL`: Set the verbosity of logs (`DEBUG`, `INFO`, `WARNING`, `ERROR`). `INFO` is recommended for normal use.
    -   `LOG_TO`: Choose `Screen`, `File`, or `Syslog`.
        -   `Screen` is best for manual testing and standard `systemd` services.
        -   `File` is best for creating a dedicated log file (e.g., on Windows or for `cron` jobs).
    -   **File-Specific Settings:** `LOG_FILE`, `LOG_MAX_MB`, and `LOG_BACKUP_COUNT` are only used when `LOG_TO = File`.

<details>
<summary><b>Advanced Logging: Using LOG_TO = Syslog</b></summary>

Setting `LOG_TO = Syslog` integrates the server's logging with the native operating system logger. This is an advanced option recommended for embedded systems like routers.

-   **Log Format:** When using `Syslog`, the server uses a simpler log format (`SIA-Server: LEVEL - Message`) because the `syslog` service adds its own timestamps and hostname.

-   **On Linux/Unix Systems:**
    -   The server will attempt to write to the standard `/dev/log` socket.
    -   For non-standard systems, you can specify a different path with the optional `SYSLOG_SOCKET` key.
    -   You can also change the `syslog` "facility" (which controls how the system `syslogd` categorizes the messages) using the optional `SYSLOG_FACILITY` key. Common values are `daemon` or `local0` through `local7`. This can be useful for tailoring log filtering rules on your specific system.

-   **On Windows Systems:**
    -   This will log messages to the **Windows Event Log** under the "Application" section with the source name "SIA-Server".
    -   **Dependencies:** This feature requires the `pywin32` package. You must install it from an **Administrator** prompt: `python -m pip install pywin32`.
    -   **Permissions:** The very first time you run the server with this option, it must be run **as an Administrator** to register the "SIA-Server" source in the Windows Registry. After that, it can be run as a normal user.
    -   If either the dependency is missing or the registration fails due to permissions, the server will print a clear warning and automatically fall back to logging to the screen.

</details>

-   **`[Notification]` Section:** Configures the server's resilient retry queue for handling network outages.
    -   `MAX_QUE_SIZE`, `MAX_RETRIES`, `MAX_RETRY_TIME` control the queue and retry behavior.
    -   `PRIORITY_1` through `PRIORITY_5`: Assign SIA Event Codes to different priority levels.
    -   `DEFAULT_PRIORITY`: The priority to use for any unlisted event code.

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
> **Note:** If your network setting is set to public, instead of private, you may need to add a rule windows firewall to accept inbound connections on the port (i.e. 10000) you are using. Search online how to do this for your windows version.

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

Please read these guidelines carefully before deploying this server.

### 1. Panel-to-Server Communication

This server supports two modes of communication from the alarm panel:

**Plaintext Mode (Default panel setting)**
- All SIA event data is transmitted in **cleartext** over TCP.
- It is readable by anyone who can observe the network traffic.
- **Recommendation:** Only use this mode on a trusted local network (LAN).

**Encrypted Mode (Recommended)**
- When encryption is enabled on the panel, a proprietary RSA-1024 + AES-128
  handshake is performed before any SIA data is exchanged.
- All event data is encrypted and appears as random noise to an observer.
- This provides **confidentiality** (an eavesdropper cannot read your alarm events)
  and makes your traffic **unrecognizable** as alarm data to opportunistic scanners.
- **This is the recommended mode for any internet-facing deployment.**

**Known Limitations of the Encrypted Mode**
The encryption scheme used by the Honeywell Galaxy panel is proprietary and does
not meet all modern cryptographic standards:
- It uses **RSA with e=3** and **AES-128-ECB**, which are considered weak by
  current standards.
- There is **no mutual authentication**. The panel cannot verify it is talking
  to the correct server, and the server cannot verify the panel's identity.


**Recommendation: Enable Encryption on the Panel and set `ENABLED = secure` in
`sia-server.conf` for all accounts.** This combination:
- Makes your traffic unrecognizable to opportunistic internet scanners.
- Prevents false alarm injection from unauthenticated plaintext connections.
- Provides confidentiality for your alarm events.

> **Note:** If you must expose the server to the public internet and require the
> highest level of security, wrapping the connection in a **VPN** (e.g.,
> WireGuard) is the right way. A VPN adds the mutual authentication layer
> that this protocol lacks.

---

### 2. Notification Privacy (Server to ntfy.sh)

- **Transport Security:** All communication to `ntfy.sh` uses **HTTPS** and is
  fully encrypted in transit.
- **Topic Privacy:** ntfy.sh topics are **public by default**. Anyone who knows
  your topic URL can subscribe to your notifications.

**To secure your notifications, choose one or more of the following:**

- **Use a long, unguessable topic name.** A random 20+ character string is
  effectively a private topic. Configure this in `NTFY_TOPIC`.
- **Use a generic `NTFY_TITLE`** that cannot be linked to your address or
  identity (e.g., "Home Security" rather than "123 Main Street Alarm").
- **Use ntfy.sh authentication.** This server fully supports token-based and
  user/password authentication via the `NTFY_AUTH`, `NTFY_TOKEN`, `NTFY_USER`,
  and `NTFY_PASS` settings. Subscribe to **ntfy.sh PRO** to enable
  access-controlled topics.
- **Self-host ntfy.** Running your own ntfy instance gives you full control over
  privacy and access. This server is fully compatible with self-hosted ntfy
  instances.

---

### 3. Summary of Recommendations

| Scenario | Recommendation |
| :--- | :--- |
| **Local network only** | Plaintext or Encrypted mode, `ENABLED = yes` |
| **Internet-facing, basic security** | Encrypted mode on panel, `ENABLED = secure` |
| **Internet-facing, maximum security** | Encrypted mode + VPN (e.g. WireGuard) |
| **Unknown/untrusted panels** | `ENABLED = no` in `[Default]` section |

---

**Disclaimer:** You are ultimately responsible for securing your own deployment.
This server is provided as-is, for educational and interoperability purposes.
The authors make no warranties and accept no liability for its use.

## Acknowledgments
-   This project was developed through a collaborative effort with Anthropic's AI assistant, Claude.
-   The initial socket server structure was inspired by the [nimnull/sia-server](https://github.com/nimnull/sia-server) project.
-   Some protocol information was found in [dklemm/FlexSIA2MQTT](https://github.com/dklemm/FlexSIA2MQTT) project.

## License
This project is licensed under the MIT License.
