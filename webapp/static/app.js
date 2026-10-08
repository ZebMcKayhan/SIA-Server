let configData = {};
let activeAccountSection = null;

// System defaults map using lowercase keys
const DEFAULTS_MAP = {
    "sia-server": {
        "enabled": "yes",
        "listen_addr": "0.0.0.0",
        "listen_port": "10000",
        "reject_policy": "respond",
        "event_heartbeat_watchdog": "no",
        "event_heartbeat_eventtype": "Old",
        "event_heartbeat_eventcode": "RX",
        "event_heartbeat_text": "[HEARTBT.]"
    },
    "ip-check": {
        "enabled": "no",
        "listen_addr": "0.0.0.0",
        "listen_port": "10001"
    },
    "watchdog": {
        "watchdog_threshold": "2.1",
        "monitoring_started_prio": "2",
        "connection_restored_prio": "2",
        "interval_changed_prio": "3",
        "watchdog_timeout_prio": "4",
        "monitoring_started": "(Disabled)",
        "connection_restored": "Heartbeat received [at %new_panel_time, ]after %elapsed, connection restored.",
        "interval_changed": "(Disabled)",
        "watchdog_timeout": "Heartbeat lost, last heartbeat received was [at %last_panel_time, ]%elapsed ago."
    },
    "notification": {
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
    "logging": {
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

    const systemSections = ["sia-server", "ip-check", "watchdog", "logging", "notification", "webgui"];

    Object.keys(configData).forEach(section => {
        if (systemSections.includes(section.toLowerCase())) return;

        const sec = configData[section];
        const tr = document.createElement("tr");

        // Clean Account Number display without [] brackets
        const accountDisplay = section.toLowerCase() === 'default' ? 'Default' : section;

        tr.innerHTML = `
            <td><strong>${accountDisplay}</strong></td>
            <td>${sec.site_name || accountDisplay}</td>
            <td>${sec.enabled || 'yes'}</td>
            <td><span class="badge">${sec.provider || 'None'}</span></td>
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

    const accountDisplay = section.toLowerCase() === 'default' ? 'Default' : section;
    document.getElementById("modal-title").innerText = `Edit Account: ${accountDisplay}`;
    document.getElementById("modal-account-id").value = section;
    document.getElementById("modal-site-name").value = data.site_name || "";
    document.getElementById("modal-enabled").value = data.enabled || "yes";
    document.getElementById("modal-provider").value = data.provider || "None";

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
        container.innerHTML += createInput("ntfy_topic", "ntfy_topic", "https://ntfy.sh/my-topic");
        container.innerHTML += createInput("ntfy_title", "ntfy_title", "SIA Alert");
        container.innerHTML += createInput("ntfy_token", "ntfy_token", "tk_...");
    } else if (provider === "telegram") {
        container.innerHTML += createInput("telegram_token", "telegram_token", "123456:ABC-DEF1234...");
        container.innerHTML += createInput("telegram_chat_id", "telegram_chat_id", "-100123456789");
        container.innerHTML += createInput("telegram_title", "telegram_title", "Security Alarm");
    } else if (provider === "pushover") {
        container.innerHTML += createInput("pushover_token", "pushover_token", "azg123...");
        container.innerHTML += createInput("pushover_user", "pushover_user", "u123...");
    } else if (provider === "webhook") {
        container.innerHTML += createInput("webhook_url", "webhook_url", "https://api.example.com/endpoint");
    }
}

function saveAccountModal() {
    const section = document.getElementById("modal-account-id").value.trim();
    if (!section) return alert("Account ID is required!");

    if (!configData[section]) configData[section] = {};

    configData[section]["site_name"] = document.getElementById("modal-site-name").value;
    configData[section]["enabled"] = document.getElementById("modal-enabled").value;
    configData[section]["provider"] = document.getElementById("modal-provider").value;

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

    renderSectionForm("watchdog", "watchdog-form");
    renderSectionForm("ip-check", "ipcheck-form");
    renderSectionForm("notification", "notifications-form");
    renderSectionForm("sia-server", "server-form");
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
