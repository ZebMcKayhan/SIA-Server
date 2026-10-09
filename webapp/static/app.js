let configData = {};
let hasConfigFileComments = false;

// Canonical defaults catalog
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

    const createInput = (key, label, placeholder="") => `
        <div class="form-group">
            <label>${label}</label>
            <input type="text" id="field_${key}" value="${getVal(key)}" placeholder="${placeholder}">
        </div>
    `;

    if (provider === "ntfy") {
        container.innerHTML += createInput("NTFY_TITLE", "NTFY_TITLE (Optional)", "Galaxy Alarm");
        container.innerHTML += createInput("NTFY_TOPIC", "NTFY_TOPIC", "https://ntfy.sh/topic");
        
        const currentAuth = getVal("NTFY_AUTH") || "None";
        container.innerHTML += `
            <div class="form-group">
                <label>NTFY_AUTH</label>
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
                <label>PUSHOVER_SOUND (Optional)</label>
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
                <label>WEBHOOK_METHOD</label>
                <select id="field_WEBHOOK_METHOD">
                    <option value="POST" ${methodVal === 'POST' ? 'selected' : ''}>POST</option>
                    <option value="PUT" ${methodVal === 'PUT' ? 'selected' : ''}>PUT</option>
                </select>
            </div>
        `;

        const authVal = getVal("WEBHOOK_AUTH") || "None";
        container.innerHTML += `
            <div class="form-group">
                <label>WEBHOOK_AUTH</label>
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
                <label>${type.toUpperCase()}_TOKEN</label>
                <input type="text" id="field_${type.toUpperCase()}_TOKEN" value="${getVal(type.toUpperCase() + '_TOKEN')}">
            </div>
        `;
    } else if (authChoice === "Userpass") {
        subContainer.innerHTML = `
            <div class="form-group">
                <label>${type.toUpperCase()}_USER</label>
                <input type="text" id="field_${type.toUpperCase()}_USER" value="${getVal(type.toUpperCase() + '_USER')}">
            </div>
            <div class="form-group">
                <label>${type.toUpperCase()}_PASS</label>
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

        container.innerHTML += `
            <div class="form-group">
                <label>${key}</label>
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
            <label>LOG_LEVEL</label>
            <select onchange="updateConfigValue('${secKey}', 'LOG_LEVEL', this.value)">
                ${['DEBUG', 'INFO', 'WARNING', 'ERROR'].map(l => `<option value="${l}" ${l === levelVal.toUpperCase() ? 'selected' : ''}>${l}</option>`).join('')}
            </select>
        </div>
    `;

    const logToVal = getValueCaseInsensitive(sec, "LOG_TO") || "Screen";
    const currentLogTo = logToVal.charAt(0).toUpperCase() + logToVal.slice(1).toLowerCase();
    container.innerHTML += `
        <div class="form-group">
            <label>LOG_TO</label>
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
    return `
        <div class="form-group">
            <label>${key}</label>
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
