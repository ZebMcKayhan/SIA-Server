let configData = {};
let hasConfigFileComments = false;

// Complete README Documentation Help Catalog
const HELP_TEXTS = {
    // [SIA-Server]
    "ENABLED": "Controls whether the SIA Event Server or service starts. Set to No if running IP-Check only.",
    "LISTEN_ADDR": "Network IP address interface to bind and listen on (default 0.0.0.0).",
    "LISTEN_PORT": "TCP port for the main SIA event server listener (default 10000).",
    "REJECT_POLICY": "respond: Send SIA REJECT frame to client. drop: Silently close connection without sending anything.",
    "EVENT_HEARTBEAT_WATCHDOG": "Enables watchdog monitoring from SIA event heartbeats (e.g. Galaxy Dimension).",
    "EVENT_HEARTBEAT_EVENTTYPE": "Event type identifying an event heartbeat (Old or New). Default: Old.",
    "EVENT_HEARTBEAT_EVENTCODE": "2-character SIA event code identifying heartbeats. Default: RX.",
    "EVENT_HEARTBEAT_TEXT": "Text prefix in action_text identifying heartbeats. Default: [HEARTBT.].",

    // [IP-Check]
    "IP_CHECK_ENABLED": "Controls whether the optional IP Check Service starts. Default: No.",
    "IP_CHECK_LISTEN_ADDR": "IP address interface used by the IP Check Service.",
    "IP_CHECK_LISTEN_PORT": "TCP port used by the IP Check Service (default 10001).",

    // [WATCHDOG]
    "WATCHDOG_THRESHOLD": "Missed heartbeat multiplier before declaring lost connection (calculated as THRESHOLD x interval). Range 1.1 - 10.0. Set <= 1.0 to disable.",
    "MONITORING_STARTED_PRIO": "Notification priority (1-5) when monitoring starts for an account. Default: 2.",
    "CONNECTION_RESTORED_PRIO": "Notification priority (1-5) when a disconnected heartbeat is restored. Default: 2.",
    "INTERVAL_CHANGED_PRIO": "Notification priority (1-5) when panel changes its heartbeat interval. Default: 3.",
    "WATCHDOG_TIMEOUT_PRIO": "Notification priority (1-5) when watchdog detects a lost connection timeout. Default: 4.",
    "MONITORING_STARTED": "Message format when first valid heartbeat is received. Placeholders: %account, %site_name, %new_panel_time, %new_interval.",
    "CONNECTION_RESTORED": "Message format when connection is restored after timeout. Placeholders: %elapsed, %new_panel_time.",
    "INTERVAL_CHANGED": "Message format when heartbeat interval changes. Placeholders: %last_interval, %new_interval.",
    "WATCHDOG_TIMEOUT": "Message format when heartbeat is lost beyond threshold timeout. Placeholders: %last_panel_time, %elapsed.",

    // [Notification]
    "NOTIFICATION_FORMAT_ASCII": "Format for SIA Level 3 events with human-readable action_text. Placeholders: %time, %action_text, %group, %account, %site_name.",
    "NOTIFICATION_FORMAT_DATA": "Format for SIA Level 0-2 events. Placeholders: %time, %event_code, %event_description, %user_id, %zone, %group, %value.",
    "MAX_QUE_SIZE": "Maximum number of failed events to queue up (1 to 1000). Default: 50.",
    "MAX_RETRIES": "Maximum retry attempts before dropping (0 = infinite). Default: 10.",
    "MAX_RETRY_TIME": "Max minutes between exponential retries (1-1000). Default: 30.",
    "DEFAULT_PRIORITY": "Priority level (1-5) used for unlisted or unknown event codes. Default: 5.",
    "PRIORITY_1": "Very Low Priority SIA Event Codes (e.g., routine events).",
    "PRIORITY_2": "Low Priority SIA Event Codes (e.g. RX, RP, TS, TE).",
    "PRIORITY_3": "Normal Priority SIA Event Codes (e.g. CL, OP, CA, OA, BC, OR).",
    "PRIORITY_4": "High Priority SIA Event Codes (e.g. AR, XR).",
    "PRIORITY_5": "Urgent Priority SIA Event Codes (e.g. BA, BV, TA, FA, PA, AT, XT).",

    // [Logging]
    "LOG_LEVEL": "Log verbosity level (DEBUG, INFO, WARNING, ERROR). Default: INFO.",
    "LOG_TO": "Log output target: Screen (stdout), File (log file), or Syslog (system log/Windows event log).",
    "LOG_FILE": "Full file path for logs when LOG_TO = File (e.g. /tmp/sia-server.log or C:\\Logs\\sia.log).",
    "LOG_MAX_MB": "Maximum size per log file in MB before rotating (1-100). Default: 10.",
    "LOG_BACKUP_COUNT": "Number of rotated log files to retain (1-10). Default: 5.",
    "SYSLOG_SOCKET": "Socket path for Syslog written on Linux/Unix (default /dev/log).",
    "SYSLOG_FACILITY": "Syslog facility category (daemon, user, local0-local7). Default: user.",

    // Providers
    "NTFY_TOPIC": "Public or private ntfy.sh topic URL (e.g. https://ntfy.sh/your-topic).",
    "NTFY_TITLE": "Title header displayed in ntfy notifications. Default: Galaxy Alarm.",
    "NTFY_AUTH": "Authentication type for private topics: None, Token, or Userpass.",
    "NTFY_TOKEN": "Secret Bearer token required when NTFY_AUTH = Token.",
    "NTFY_USER": "Username required when NTFY_AUTH = Userpass.",
    "NTFY_PASS": "Password required when NTFY_AUTH = Userpass.",
    "TELEGRAM_TOKEN": "Telegram Bot Token obtained from @BotFather.",
    "TELEGRAM_CHAT_ID": "Target Telegram Chat or Channel ID.",
    "TELEGRAM_API_URL": "Optional Telegram API base URL endpoint (default: https://api.telegram.org).",
    "PUSHOVER_TOKEN": "Pushover Application API Token.",
    "PUSHOVER_USER": "Pushover User or Group Key.",
    "PUSHOVER_SOUND": "Notification alert sound choice (e.g. siren, alien, cosmic).",
    "PUSHOVER_RETRY": "Seconds between retry attempts for emergency priority (min 30).",
    "PUSHOVER_EXPIRE": "Seconds until emergency retries stop (max 10800).",
    "PUSHOVER_DEVICE": "Target specific device name only.",
    "WEBHOOK_URL": "Target HTTP Webhook Endpoint URL.",
    "WEBHOOK_METHOD": "HTTP Request Method: POST or PUT (default POST).",
    "WEBHOOK_AUTH": "Authentication type: None, Token, or Userpass."
};

const DEFAULTS_MAP = {
    "SIA-Server": {
        "ENABLED": "Yes",
        "LISTEN_ADDR": "0.0.0.0",
        "LISTEN_PORT": "10000",
        "REJECT_POLICY": "respond",
        "EVENT_HEARTBEAT_WATCHDOG": "No",
        "EVENT_HEARTBEAT_EVENTTYPE": "Old",
        "EVENT_HEARTBEAT_EVENTCODE": "RX",
        "EVENT_HEARTBEAT_TEXT": "[HEARTBT.]"
    },
    "IP-Check": {
        "ENABLED": "No",
        "LISTEN_ADDR": "0.0.0.0",
        "LISTEN_PORT": "10001"
    },
    "WATCHDOG": {
        "WATCHDOG_THRESHOLD": "2.1",
        "MONITORING_STARTED_PRIO": "2",
        "CONNECTION_RESTORED_PRIO": "2",
        "INTERVAL_CHANGED_PRIO": "3",
        "WATCHDOG_TIMEOUT_PRIO": "4",
        "MONITORING_STARTED": "(disabled)",
        "CONNECTION_RESTORED": "Heartbeat received [at %new_panel_time, ]after %elapsed, connection restored.",
        "INTERVAL_CHANGED": "(disabled)",
        "WATCHDOG_TIMEOUT": "Heartbeat lost, last heartbeat received was [at %last_panel_time, ]%elapsed ago."
    },
    "Notification": {
        "NOTIFICATION_FORMAT_ASCII": "%time %action_text [(Group: %group)]",
        "NOTIFICATION_FORMAT_DATA": "%time Event: %event_code [(%event_description)][ User: %user_id][ Zone: %zone][ Group: %group][ Peripheral: %peripheral][ Value: %value]",
        "MAX_QUE_SIZE": "50",
        "MAX_RETRIES": "10",
        "MAX_RETRY_TIME": "30",
        "DEFAULT_PRIORITY": "5",
        "PRIORITY_1": "(disabled)",
        "PRIORITY_2": "RX, RP, TS, TE",
        "PRIORITY_3": "CL, OP, CA, OA, BC, OR, OG, CG",
        "PRIORITY_4": "AR, XR",
        "PRIORITY_5": "BA, BV, TA, FA, PA, AT, XT"
    },
    "Logging": {
        "LOG_LEVEL": "INFO",
        "LOG_TO": "Screen",
        "SYSLOG_SOCKET": "/dev/log",
        "SYSLOG_FACILITY": "user",
        "LOG_FILE": "/tmp/sia-server.log",
        "LOG_MAX_MB": "10",
        "LOG_BACKUP_COUNT": "5"
    }
};

const PUSHOVER_SOUNDS = [
    "pushover", "bike", "bugle", "cashregister", "classical",
    "cosmic", "falling", "gamelan", "incoming", "intermission",
    "magic", "mechanical", "piano", "siren", "spacealarm",
    "tugboat", "alien", "climb", "persistent", "echo", "updown", "none"
];

document.addEventListener("DOMContentLoaded", () => {
    loadConfig();
});

function getValueCaseInsensitive(obj, keyName) {
    if (!obj) return undefined;
    const targetKey = Object.keys(obj).find(k => k.toLowerCase() === keyName.toLowerCase());
    return targetKey ? obj[targetKey] : undefined;
}

document.addEventListener("click", (evt) => {
    if (!evt.target.classList.contains("help-btn")) {
        document.querySelectorAll(".help-tooltip.show").forEach(el => el.classList.remove("show"));
    }
});

function toggleHelpTooltip(el) {
    evt = window.event;
    if (evt) evt.stopPropagation();
    
    const tooltip = el.nextElementSibling;
    if (tooltip) {
        const isShown = tooltip.classList.contains("show");
        document.querySelectorAll(".help-tooltip.show").forEach(t => t.classList.remove("show"));
        if (!isShown) {
            tooltip.classList.add("show");
        }
    }
}

async function loadConfig() {
    try {
        const response = await fetch("/api/config");
        if (!response.ok) throw new Error("Failed to load config file.");
        const data = await response.json();
        configData = data.config;
        hasConfigFileComments = data.has_comments;

        renderAccountsTable();
        renderSystemForms();
    } catch (err) {
        alert("Error loading config: " + err.message);
    }
}

function switchTab(tabName) {
    document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(el => el.classList.remove("active"));
    
    event.currentTarget.classList.add("active");
    document.getElementById("tab-" + tabName).classList.add("active");

    if (tabName === "logs") fetchLogs();
}

function renderAccountsTable() {
    const tbody = document.getElementById("accounts-table-body");
    tbody.innerHTML = "";

    const systemSections = ["SIA-Server", "IP-Check", "WATCHDOG", "Logging", "Notification", "WebGUI"];

    Object.keys(configData).forEach(section => {
        if (systemSections.some(s => s.toLowerCase() === section.toLowerCase())) return;

        const sec = configData[section];
        const tr = document.createElement("tr");

        const accountDisplay = section;
        const siteName = getValueCaseInsensitive(sec, "site_name") || accountDisplay;
        const enabled = getValueCaseInsensitive(sec, "enabled") || "Yes";
        const provider = getValueCaseInsensitive(sec, "provider") || "None";

        tr.innerHTML = `
            <td><strong>${accountDisplay}</strong></td>
            <td>${siteName}</td>
            <td>${enabled}</td>
            <td><span class="badge">${provider}</span></td>
            <td>
                <button class="btn btn-secondary" onclick="editAccount('${section}')">Edit</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function editAccount(section) {
    const data = configData[section] || {};

    document.getElementById("modal-title").innerText = `Edit Account: ${section || 'New'}`;
    document.getElementById("modal-account-id").value = section;
    document.getElementById("modal-site-name").value = getValueCaseInsensitive(data, "site_name") || "";

    const rawEnabled = getValueCaseInsensitive(data, "enabled") || "Yes";
    const enabledVal = rawEnabled.charAt(0).toUpperCase() + rawEnabled.slice(1).toLowerCase();
    document.getElementById("modal-enabled").value = ["Yes", "No", "Secure"].includes(enabledVal) ? enabledVal : "Yes";

    const providerVal = getValueCaseInsensitive(data, "provider") || "None";
    document.getElementById("modal-provider").value = providerVal;

    renderDynamicProviderFields(data);
    document.getElementById("account-modal").classList.add("active");
}

function openAccountModal() {
    editAccount("");
}

function closeAccountModal() {
    document.getElementById("account-modal").classList.remove("active");
}

function renderDynamicProviderFields(data = {}) {
    const provider = document.getElementById("modal-provider").value;
    const container = document.getElementById("dynamic-provider-fields");
    container.innerHTML = "";

    const getVal = (key) => getValueCaseInsensitive(data, key) || "";

    const createInput = (key, label, placeholder="") => {
        const helpText = HELP_TEXTS[key.toUpperCase()] || "Configuration setting for provider.";
        return `
            <div class="form-group">
                <label>
                    ${label}
                    <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                    <span class="help-tooltip">${helpText}</span>
                </label>
                <input type="text" id="field_${key}" value="${getVal(key)}" placeholder="${placeholder}">
            </div>
        `;
    };

    if (provider === "ntfy") {
        container.innerHTML += createInput("NTFY_TITLE", "NTFY_TITLE (Optional)", "Galaxy Alarm");
        container.innerHTML += createInput("NTFY_TOPIC", "NTFY_TOPIC", "https://ntfy.sh/topic");
        
        const currentAuth = getVal("NTFY_AUTH") || "None";
        container.innerHTML += `
            <div class="form-group">
                <label>
                    NTFY_AUTH
                    <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                    <span class="help-tooltip">${HELP_TEXTS['NTFY_AUTH']}</span>
                </label>
                <select id="field_NTFY_AUTH" onchange="toggleSubAuthFields('ntfy')">
                    <option value="None" ${currentAuth === 'None' ? 'selected' : ''}>None</option>
                    <option value="Token" ${currentAuth === 'Token' ? 'selected' : ''}>Token</option>
                    <option value="Userpass" ${currentAuth === 'Userpass' ? 'selected' : ''}>Userpass</option>
                </select>
            </div>
            <div id="sub_auth_ntfy"></div>
        `;
        setTimeout(() => toggleSubAuthFields('ntfy', data), 0);

    } else if (provider === "telegram") {
        container.innerHTML += createInput("TELEGRAM_TITLE", "TELEGRAM_TITLE (Optional)", "Galaxy Alarm");
        container.innerHTML += createInput("TELEGRAM_TOKEN", "TELEGRAM_TOKEN");
        container.innerHTML += createInput("TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID");
        container.innerHTML += createInput("TELEGRAM_API_URL", "TELEGRAM_API_URL (Optional)", "https://api.telegram.org");

    } else if (provider === "pushover") {
        container.innerHTML += createInput("PUSHOVER_TITLE", "PUSHOVER_TITLE (Optional)", "Galaxy Alarm");
        container.innerHTML += createInput("PUSHOVER_TOKEN", "PUSHOVER_TOKEN");
        container.innerHTML += createInput("PUSHOVER_USER", "PUSHOVER_USER");

        const soundVal = getVal("PUSHOVER_SOUND") || "siren";
        let soundOptions = PUSHOVER_SOUNDS.map(s => `<option value="${s}" ${s === soundVal ? 'selected' : ''}>${s}</option>`).join("");
        container.innerHTML += `
            <div class="form-group">
                <label>
                    PUSHOVER_SOUND (Optional)
                    <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                    <span class="help-tooltip">${HELP_TEXTS['PUSHOVER_SOUND']}</span>
                </label>
                <select id="field_PUSHOVER_SOUND">${soundOptions}</select>
            </div>
        `;

        container.innerHTML += createInput("PUSHOVER_RETRY", "PUSHOVER_RETRY (Optional)", "30");
        container.innerHTML += createInput("PUSHOVER_EXPIRE", "PUSHOVER_EXPIRE (Optional)", "3600");
        container.innerHTML += createInput("PUSHOVER_DEVICE", "PUSHOVER_DEVICE (Optional)");

    } else if (provider === "webhook") {
        container.innerHTML += createInput("WEBHOOK_URL", "WEBHOOK_URL");

        const methodVal = getVal("WEBHOOK_METHOD") || "POST";
        container.innerHTML += `
            <div class="form-group">
                <label>
                    WEBHOOK_METHOD
                    <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                    <span class="help-tooltip">${HELP_TEXTS['WEBHOOK_METHOD']}</span>
                </label>
                <select id="field_WEBHOOK_METHOD">
                    <option value="POST" ${methodVal === 'POST' ? 'selected' : ''}>POST</option>
                    <option value="PUT" ${methodVal === 'PUT' ? 'selected' : ''}>PUT</option>
                </select>
            </div>
        `;

        const authVal = getVal("WEBHOOK_AUTH") || "None";
        container.innerHTML += `
            <div class="form-group">
                <label>
                    WEBHOOK_AUTH
                    <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                    <span class="help-tooltip">${HELP_TEXTS['WEBHOOK_AUTH']}</span>
                </label>
                <select id="field_WEBHOOK_AUTH" onchange="toggleSubAuthFields('webhook')">
                    <option value="None" ${authVal === 'None' ? 'selected' : ''}>None</option>
                    <option value="Token" ${authVal === 'Token' ? 'selected' : ''}>Token</option>
                    <option value="Userpass" ${authVal === 'Userpass' ? 'selected' : ''}>Userpass</option>
                </select>
            </div>
            <div id="sub_auth_webhook"></div>
        `;
        setTimeout(() => toggleSubAuthFields('webhook', data), 0);
    }
}

function toggleSubAuthFields(type, data = {}) {
    const subContainer = document.getElementById(`sub_auth_${type}`);
    if (!subContainer) return;
    subContainer.innerHTML = "";

    const authChoice = document.getElementById(`field_${type.toUpperCase()}_AUTH`).value;
    const getVal = (key) => getValueCaseInsensitive(data, key) || "";

    if (authChoice === "Token") {
        subContainer.innerHTML = `
            <div class="form-group">
                <label>
                    ${type.toUpperCase()}_TOKEN
                    <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                    <span class="help-tooltip">${HELP_TEXTS[type.toUpperCase() + '_TOKEN']}</span>
                </label>
                <input type="text" id="field_${type.toUpperCase()}_TOKEN" value="${getVal(type.toUpperCase() + '_TOKEN')}">
            </div>
        `;
    } else if (authChoice === "Userpass") {
        subContainer.innerHTML = `
            <div class="form-group">
                <label>
                    ${type.toUpperCase()}_USER
                    <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                    <span class="help-tooltip">${HELP_TEXTS[type.toUpperCase() + '_USER']}</span>
                </label>
                <input type="text" id="field_${type.toUpperCase()}_USER" value="${getVal(type.toUpperCase() + '_USER')}">
            </div>
            <div class="form-group">
                <label>
                    ${type.toUpperCase()}_PASS
                    <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                    <span class="help-tooltip">${HELP_TEXTS[type.toUpperCase() + '_PASS']}</span>
                </label>
                <input type="password" id="field_${type.toUpperCase()}_PASS" value="${getVal(type.toUpperCase() + '_PASS')}">
            </div>
        `;
    }
}

function saveAccountModal() {
    const section = document.getElementById("modal-account-id").value.trim();
    if (!section) return alert("Account ID is required!");

    if (!configData[section]) configData[section] = {};

    configData[section]["SITE_NAME"] = document.getElementById("modal-site-name").value;
    configData[section]["ENABLED"] = document.getElementById("modal-enabled").value;
    configData[section]["PROVIDER"] = document.getElementById("modal-provider").value;

    document.querySelectorAll("[id^='field_']").forEach(input => {
        const key = input.id.replace("field_", "");
        configData[section][key] = input.value;
    });

    closeAccountModal();
    renderAccountsTable();
}

function renderSystemForms() {
    renderSectionForm("WATCHDOG", "watchdog-form");
    renderSectionForm("IP-Check", "ipcheck-form");
    renderSectionForm("Notification", "notifications-form");
    renderSectionForm("SIA-Server", "server-form");
    renderLoggingForm();
}

function renderSectionForm(sectionName, containerId) {
    const container = document.getElementById(containerId);
    container.innerHTML = "";

    const secKey = Object.keys(configData).find(k => k.toLowerCase() === sectionName.toLowerCase()) || sectionName;
    if (!configData[secKey]) configData[secKey] = {};

    const sec = configData[secKey];
    const defaults = DEFAULTS_MAP[sectionName] || {};

    const allKeys = Array.from(new Set([...Object.keys(sec), ...Object.keys(defaults)]));

    allKeys.forEach(key => {
        const currentValue = getValueCaseInsensitive(sec, key) !== undefined ? getValueCaseInsensitive(sec, key) : "";
        const defaultPlaceholder = defaults[key] || "(disabled)";
        const helpText = HELP_TEXTS[key.toUpperCase()] || "Configuration setting for " + sectionName;

        container.innerHTML += `
            <div class="form-group">
                <label>
                    ${key}
                    <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                    <span class="help-tooltip">${helpText}</span>
                </label>
                <input type="text" 
                       value="${currentValue}" 
                       placeholder="Default: ${defaultPlaceholder}" 
                       onchange="updateConfigValue('${secKey}', '${key}', this.value)">
            </div>
        `;
    });
}

function renderLoggingForm() {
    const container = document.getElementById("logging-form");
    container.innerHTML = "";

    const secKey = Object.keys(configData).find(k => k.toLowerCase() === "logging") || "Logging";
    if (!configData[secKey]) configData[secKey] = {};
    const sec = configData[secKey];

    const levelVal = getValueCaseInsensitive(sec, "LOG_LEVEL") || "INFO";
    container.innerHTML += `
        <div class="form-group">
            <label>
                LOG_LEVEL
                <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                <span class="help-tooltip">${HELP_TEXTS['LOG_LEVEL']}</span>
            </label>
            <select onchange="updateConfigValue('${secKey}', 'LOG_LEVEL', this.value)">
                ${['DEBUG', 'INFO', 'WARNING', 'ERROR'].map(l => `<option value="${l}" ${l === levelVal.toUpperCase() ? 'selected' : ''}>${l}</option>`).join('')}
            </select>
        </div>
    `;

    const logToVal = getValueCaseInsensitive(sec, "LOG_TO") || "Screen";
    const currentLogTo = logToVal.charAt(0).toUpperCase() + logToVal.slice(1).toLowerCase();
    container.innerHTML += `
        <div class="form-group">
            <label>
                LOG_TO
                <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                <span class="help-tooltip">${HELP_TEXTS['LOG_TO']}</span>
            </label>
            <select id="logging_log_to_select" onchange="updateConfigValue('${secKey}', 'LOG_TO', this.value); renderLoggingForm();">
                <option value="Screen" ${currentLogTo === 'Screen' ? 'selected' : ''}>Screen</option>
                <option value="File" ${currentLogTo === 'File' ? 'selected' : ''}>File</option>
                <option value="Syslog" ${currentLogTo === 'Syslog' ? 'selected' : ''}>Syslog</option>
            </select>
        </div>
    `;

    if (currentLogTo === "File") {
        container.innerHTML += createLoggingInput(secKey, "LOG_FILE", "/tmp/sia-server.log");
        container.innerHTML += createLoggingInput(secKey, "LOG_MAX_MB", "10");
        container.innerHTML += createLoggingInput(secKey, "LOG_BACKUP_COUNT", "5");
    } else if (currentLogTo === "Syslog") {
        container.innerHTML += createLoggingInput(secKey, "SYSLOG_SOCKET", "/dev/log");
        container.innerHTML += createLoggingInput(secKey, "SYSLOG_FACILITY", "user");
    }
}

function createLoggingInput(secKey, key, defaultVal) {
    const currentValue = getValueCaseInsensitive(configData[secKey], key) || "";
    const helpText = HELP_TEXTS[key.toUpperCase()] || "Logging configuration parameter.";
    return `
        <div class="form-group">
            <label>
                ${key}
                <span class="help-btn" onclick="toggleHelpTooltip(this)">?</span>
                <span class="help-tooltip">${helpText}</span>
            </label>
            <input type="text" value="${currentValue}" placeholder="Default: ${defaultVal}" onchange="updateConfigValue('${secKey}', '${key}', this.value)">
        </div>
    `;
}

function updateConfigValue(section, key, val) {
    if (!configData[section]) configData[section] = {};
    configData[section][key] = val;
}

async function promptSaveConfiguration() {
    let confirmMsg = "Overwrite existing config?";
    if (hasConfigFileComments) {
        confirmMsg = "Configuration will be stripped from comments and updated to latest type - Continue?";
    }

    if (confirm(confirmMsg)) {
        await saveConfiguration();
    }
}

async function saveConfiguration() {
    try {
        const res = await fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(configData)
        });
        const result = await res.json();
        alert(result.message);
        hasConfigFileComments = false;
    } catch (e) {
        alert("Save failed: " + e.message);
    }
}

async function triggerReload() {
    try {
        const res = await fetch("/api/reload", { method: "POST" });
        const result = await res.json();
        alert(result.message);
    } catch (e) {
        alert("Reload failed: " + e.message);
    }
}

async function fetchLogs() {
    try {
        const res = await fetch("/api/logs");
        const data = await res.json();
        document.getElementById("log-console").innerText = data.logs.join("\n");
    } catch (e) {
        document.getElementById("log-console").innerText = "Failed to load logs.";
    }
}
