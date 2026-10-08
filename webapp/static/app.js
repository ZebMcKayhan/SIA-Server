let configData = {};
let activeAccountSection = null;

// Initial load
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
        // Exclude system sections from accounts list
        if (["SIA-Server", "WATCHDOG", "IP-Check", "Logging", "Notification", "WebGUI"].includes(section)) return;

        const sec = configData[section];
        const tr = document.createElement("tr");

        tr.innerHTML = `
            <td><strong>[${section}]</strong></td>
            <td>${sec.SITE_NAME || section}</td>
            <td>${sec.ENABLED || 'Yes'}</td>
            <td><span class="badge">${sec.PROVIDER || 'None'}</span></td>
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
    document.getElementById("modal-site-name").value = data.SITE_NAME || "";
    document.getElementById("modal-enabled").value = data.ENABLED || "Yes";
    document.getElementById("modal-provider").value = data.PROVIDER || "None";

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

    const createInput = (key, label, type="text") => `
        <div class="form-group">
            <label>${label}</label>
            <input type="${type}" id="field_${key}" value="${data[key] || ''}">
        </div>
    `;

    if (provider === "ntfy") {
        container.innerHTML += createInput("NTFY_TOPIC", "NTFY Topic (e.g. https://ntfy.sh/topic)");
        container.innerHTML += createInput("NTFY_TITLE", "NTFY Title");
        container.innerHTML += createInput("NTFY_TOKEN", "NTFY Token (Optional)");
    } else if (provider === "telegram") {
        container.innerHTML += createInput("TELEGRAM_TOKEN", "Telegram Bot Token");
        container.innerHTML += createInput("TELEGRAM_CHAT_ID", "Telegram Chat ID");
        container.innerHTML += createInput("TELEGRAM_TITLE", "Title");
    } else if (provider === "pushover") {
        container.innerHTML += createInput("PUSHOVER_TOKEN", "Pushover Token");
        container.innerHTML += createInput("PUSHOVER_USER", "Pushover User Key");
        container.innerHTML += createInput("PUSHOVER_SOUND", "Sound (optional)");
    } else if (provider === "webhook") {
        container.innerHTML += createInput("WEBHOOK_URL", "Webhook Endpoint URL");
        container.innerHTML += createInput("WEBHOOK_TOKEN", "Auth Token (optional)");
    }
}

function saveAccountModal() {
    const section = document.getElementById("modal-account-id").value.trim();
    if (!section) return alert("Account ID is required!");

    if (!configData[section]) configData[section] = {};

    configData[section]["SITE_NAME"] = document.getElementById("modal-site-name").value;
    configData[section]["ENABLED"] = document.getElementById("modal-enabled").value;
    const provider = document.getElementById("modal-provider").value;
    configData[section]["PROVIDER"] = provider;

    // Collect dynamic inputs
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
        const sec = configData[sectionName] || {};

        Object.keys(sec).forEach(key => {
            container.innerHTML += `
                <div class="form-group">
                    <label>${key}</label>
                    <input type="text" value="${sec[key]}" onchange="configData['${sectionName}']['${key}'] = this.value">
                </div>
            `;
        });
    };

    renderSectionForm("WATCHDOG", "watchdog-form");
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
