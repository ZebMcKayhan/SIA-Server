let configData = {};
let activeAccountSection = null;

// Complete system defaults catalog extracted directly from configuration.py
const DEFAULTS_MAP = {
    "SIA-Server": {
        "enabled": "yes",
        "listen_addr": "0.0.0.0",
        "listen_port": "10000",
        "reject_policy": "respond",
        "event_heartbeat_watchdog": "no",
        "event_heartbeat_eventtype": "Old",
        "event_heartbeat_eventcode": "RX",
        "event_heartbeat_text": "[HEARTBT.]"
    },
    "IP-Check": {
        "enabled": "no",
        "listen_addr": "0.0.0.0",
        "listen_port": "10001"
    },
    "WATCHDOG": {
        "watchdog_threshold": "2.1",
        "monitoring_started_prio": "2",
        "connection_restored_prio": "2",
        "interval_changed_prio": "3",
        "watchdog_timeout_prio": "4",
        "monitoring_started": "(Disabled / Empty)",
        "connection_restored": "Heartbeat received [at %new_panel_time, ]after %elapsed, connection restored.",
        "interval_changed": "(Disabled / Empty)",
        "watchdog_timeout": "Heartbeat lost, last heartbeat received was [at %last_panel_time, ]%elapsed ago."
    },
    "Notification": {
        "notification_format_ascii": "%time %action_text [(Group: %group)]",
        "notification_format_data": "%time Event: %event_code [(%event_description)][ User: %user_id][ Zone: %zone][ Group: %group][ Peripheral: %peripheral][ Value: %value]",
        "max_que_size": "50",
        "max_retries": "10",
        "max_retry_time": "30",
        "default_priority": "5",
        "priority_1": "BA, BV, TA, FA",
        "priority_2": "PA, HA, QA",
        "priority_3": "CA, CL, OA, OP",
        "priority_4": "RP, TX",
        "priority_5": "(All other unmapped codes)"
    },
    "Logging": {
        "log_level": "INFO",
        "log_to": "Screen",
        "syslog_socket": "/dev/log",
        "syslog_facility": "user",
        "log_file": "/var/log/sia-server.log",
        "log_max_mb": "10",
        "log_backup_count": "5"
    }
};

document.addEventListener("DOMContentLoaded", () => {
    loadConfig();
});

async function loadConfig() {
    try {
        const response = await fetch("/api/config");
        if (!response.ok) throw new Error("Failed to load config file.");
        const data = await response.json();
        configData = data.config;
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

    Object.keys(configData).forEach(section => {
        if (["SIA-Server", "IP-Check", "WATCHDOG", "Logging", "Notification", "WebGUI"].includes(section)) return;

        const sec = configData[section];
        const tr = document.createElement("tr");

        tr.innerHTML = `
            <td><strong>[${section}]</strong></td>
            <td>${sec.SITE_NAME || sec.site_name || section}</td>
            <td>${sec.ENABLED || sec.enabled || 'yes'}</td>
            <td><span class="badge">${sec.PROVIDER || sec.provider || 'None'}</span></td>
            <td>
                <button class="btn btn-secondary" onclick="editAccount('${section}')">Edit</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function editAccount(section) {
    activeAccountSection = section;
    const data = configData[section] || {};

    document.getElementById("modal-title").innerText = `Edit Account: [${section}]`;
    document.getElementById("modal-account-id").value = section;
    document.getElementById("modal-site-name").value = data.SITE_NAME || data.site_name || "";
    document.getElementById("modal-enabled").value = data.ENABLED || data.enabled || "yes";
    document.getElementById("modal-provider").value = data.PROVIDER || data.provider || "None";

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

    const createInput = (key, label, placeholder="") => `
        <div class="form-group">
            <label>${label}</label>
            <input type="text" id="field_${key}" value="${data[key] || ''}" placeholder="${placeholder}">
        </div>
    `;

    if (provider === "ntfy") {
        container.innerHTML += createInput("NTFY_TOPIC", "NTFY Topic URL", "https://ntfy.sh/my-topic");
        container.innerHTML += createInput("NTFY_TITLE", "NTFY Title", "SIA Alert");
        container.innerHTML += createInput("NTFY_TOKEN", "NTFY Bearer Token (Optional)", "tk_...");
    } else if (provider === "telegram") {
        container.innerHTML += createInput("TELEGRAM_TOKEN", "Telegram Bot Token", "123456:ABC-DEF1234...");
        container.innerHTML += createInput("TELEGRAM_CHAT_ID", "Telegram Chat ID", "-100123456789");
        container.innerHTML += createInput("TELEGRAM_TITLE", "Title Header", "Security Alarm");
    } else if (provider === "pushover") {
        container.innerHTML += createInput("PUSHOVER_TOKEN", "Pushover App Token", "azg123...");
        container.innerHTML += createInput("PUSHOVER_USER", "Pushover User Key", "u123...");
    } else if (provider === "webhook") {
        container.innerHTML += createInput("WEBHOOK_URL", "Webhook Target URL", "https://api.example.com/endpoint");
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
    const renderSectionForm = (sectionName, containerId) => {
        const container = document.getElementById(containerId);
        container.innerHTML = "";
        
        if (!configData[sectionName]) configData[sectionName] = {};
        
        const sec = configData[sectionName];
        const defaults = DEFAULTS_MAP[sectionName] || {};

        // Merge set keys and default keys so missing keys display as grey placeholders
        const allKeys = Array.from(new Set([...Object.keys(sec), ...Object.keys(defaults)]));

        allKeys.forEach(key => {
            const currentValue = sec[key] !== undefined ? sec[key] : "";
            const defaultPlaceholder = defaults[key] || "Default value";

            container.innerHTML += `
                <div class="form-group">
                    <label>${key}</label>
                    <input type="text" 
                           value="${currentValue}" 
                           placeholder="Default: ${defaultPlaceholder}" 
                           onchange="configData['${sectionName}']['${key}'] = this.value">
                </div>
            `;
        });
    };

    renderSectionForm("WATCHDOG", "watchdog-form");
    renderSectionForm("IP-Check", "ipcheck-form");
    renderSectionForm("Notification", "notifications-form");
    renderSectionForm("SIA-Server", "server-form");
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
