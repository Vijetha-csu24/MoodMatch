let state = {
    jobId: null,
    certType: null,
    placeholders: [],
    columns: [],
    rowCount: 0,
    autoMatches: {},
    columnMapping: {},
    internalMapping: {},
};

// --- Step 1: Certificate Type ---
document.getElementById("cert-type-select").addEventListener("change", function () {
    const val = this.value;
    state.certType = val;

    const infoBox = document.getElementById("cert-type-info");
    if (val) {
        fetch("/api/cert-types")
            .then((r) => r.json())
            .then((types) => {
                const t = types[val];
                let info = `<strong>${t.label}</strong>`;
                if (t.has_instructor) info += " &mdash; Requires instructor name";
                if (t.has_expiration) info += " &mdash; Expiration auto-calculated (award + 2 years)";
                infoBox.innerHTML = info;
                infoBox.classList.remove("hidden");
                enableStep(2);
            });
    } else {
        infoBox.classList.add("hidden");
        disableStepsFrom(2);
    }
});

// --- Step 2: Upload Template ---
document.getElementById("template-file").addEventListener("change", function () {
    const file = this.files[0];
    if (!file) return;

    document.getElementById("template-filename").textContent = file.name;

    const formData = new FormData();
    formData.append("template", file);

    showLoading("template-upload-area");

    fetch("/api/upload-template", { method: "POST", body: formData })
        .then((r) => r.json())
        .then((data) => {
            hideLoading("template-upload-area");

            if (data.error) {
                showError(data.error);
                return;
            }

            state.jobId = data.job_id;
            state.placeholders = data.placeholders;

            const resultBox = document.getElementById("placeholders-result");
            resultBox.innerHTML = `
                <h3>Detected Placeholders (${data.placeholders.length})</h3>
                <ul class="placeholder-list">
                    ${data.placeholders.map((p) => `<li class="placeholder-tag">{{${p}}}</li>`).join("")}
                </ul>
            `;
            resultBox.classList.remove("hidden");

            markCompleted(2);
            enableStep(3);
        })
        .catch((err) => {
            hideLoading("template-upload-area");
            showError("Failed to upload template: " + err.message);
        });
});

// --- Step 3: Upload Data ---
document.getElementById("data-file").addEventListener("change", function () {
    const file = this.files[0];
    if (!file) return;

    document.getElementById("data-filename").textContent = file.name;

    const formData = new FormData();
    formData.append("data", file);
    formData.append("job_id", state.jobId);

    showLoading("data-upload-area");

    fetch("/api/upload-data", { method: "POST", body: formData })
        .then((r) => r.json())
        .then((data) => {
            hideLoading("data-upload-area");

            if (data.error) {
                showError(data.error);
                return;
            }

            state.columns = data.columns;
            state.rowCount = data.row_count;
            state.autoMatches = data.auto_matches;
            state.columnMapping = { ...data.auto_matches };
            state.internalMapping = data.internal_matches || {};

            const resultBox = document.getElementById("mapping-result");
            let tableRows = state.placeholders
                .map((ph) => {
                    const matched = state.autoMatches[ph];
                    const isComputed = matched === "__computed__";
                    const statusClass = matched ? "matched" : "unmatched";

                    if (isComputed) {
                        return `
                            <tr>
                                <td><code>{{${ph}}}</code></td>
                                <td><em style="color:#888">Auto-generated</em></td>
                                <td><span class="match-status matched">Computed automatically</span></td>
                            </tr>
                        `;
                    }

                    const statusText = matched ? `Matched: "${matched}"` : "No match found";
                    const options = state.columns
                        .map((col) => {
                            const selected = matched === col ? "selected" : "";
                            return `<option value="${col}" ${selected}>${col}</option>`;
                        })
                        .join("");

                    return `
                        <tr>
                            <td><code>{{${ph}}}</code></td>
                            <td>
                                <select class="column-select" data-placeholder="${ph}" onchange="updateMapping('${ph}', this.value)">
                                    <option value="">-- Select column --</option>
                                    ${options}
                                </select>
                            </td>
                            <td><span class="match-status ${statusClass}">${statusText}</span></td>
                        </tr>
                    `;
                })
                .join("");

            resultBox.innerHTML = `
                <h3>Column Mapping (${data.row_count} rows found)</h3>
                <table class="mapping-table">
                    <thead>
                        <tr>
                            <th>Placeholder</th>
                            <th>Excel Column</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>${tableRows}</tbody>
                </table>
            `;
            resultBox.classList.remove("hidden");

            markCompleted(3);
            enableStep(4);
            updateSummary();
        })
        .catch((err) => {
            hideLoading("data-upload-area");
            showError("Failed to upload data: " + err.message);
        });
});

function updateMapping(placeholder, column) {
    if (column) {
        state.columnMapping[placeholder] = column;
    } else {
        delete state.columnMapping[placeholder];
    }
    updateSummary();
}

function updateSummary() {
    const summary = document.getElementById("summary");
    const matchedCount = Object.keys(state.columnMapping).length;
    const totalPlaceholders = state.placeholders.length;

    summary.innerHTML = `
        <p><strong>Certificate Type:</strong> ${document.getElementById("cert-type-select").selectedOptions[0].text}</p>
        <p><strong>Rows to Process:</strong> <span class="cert-count">${state.rowCount}</span></p>
        <p><strong>Placeholders Matched:</strong> ${matchedCount} / ${totalPlaceholders}</p>
        <p><strong>Output:</strong> ${state.rowCount} protected .docx files + manifest.xlsx in a ZIP</p>
    `;
}

// --- Step 4: Generate ---
function generateCertificates() {
    const btn = document.getElementById("generate-btn");
    const progress = document.getElementById("progress");

    btn.disabled = true;
    progress.classList.remove("hidden");

    fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            job_id: state.jobId,
            cert_type: state.certType,
            column_mapping: Object.fromEntries(
                Object.entries(state.internalMapping).filter(([_, v]) => v !== "__computed__")
            ),
        }),
    })
        .then((r) => r.json())
        .then((data) => {
            btn.disabled = false;
            progress.classList.add("hidden");

            if (data.error) {
                let msg = data.error;
                if (data.details) {
                    msg += "\n" + data.details.join("\n");
                }
                showError(msg);
                return;
            }

            enableStep(5);
            markCompleted(4);

            const resultBox = document.getElementById("generation-result");
            let errorHtml = "";
            if (data.errors && data.errors.length > 0) {
                errorHtml = `
                    <p style="color: #ef4444; margin-top: 8px;">
                        ${data.total_errors} error(s) occurred:
                    </p>
                    <div class="error-details">
                        ${data.errors.map((e) => `<div>${e}</div>`).join("")}
                    </div>
                `;
            }

            resultBox.innerHTML = `
                <p>Successfully generated <span class="cert-count">${data.total_generated}</span> certificate(s)</p>
                ${errorHtml}
            `;

            const downloadLink = document.getElementById("download-link");
            downloadLink.href = `/api/download/${state.jobId}`;
            downloadLink.classList.remove("hidden");
            markCompleted(5);
        })
        .catch((err) => {
            btn.disabled = false;
            progress.classList.add("hidden");
            showError("Generation failed: " + err.message);
        });
}

// --- UI Helpers ---
function enableStep(n) {
    document.getElementById(`step-${n}`).classList.remove("disabled");
    const dot = document.getElementById(`dot-${n}`);
    if (dot) dot.classList.add("active");
}

function disableStepsFrom(n) {
    for (let i = n; i <= 5; i++) {
        const step = document.getElementById(`step-${i}`);
        step.classList.add("disabled");
        step.classList.remove("completed");
        const dot = document.getElementById(`dot-${i}`);
        if (dot) {
            dot.classList.remove("active", "completed");
            dot.innerHTML = i;
        }
        const line = document.getElementById(`line-${i - 1}`);
        if (line) line.classList.remove("completed");
    }
    const resultBoxes = ["placeholders-result", "mapping-result", "generation-result"];
    for (const id of resultBoxes) {
        const el = document.getElementById(id);
        if (el) {
            el.innerHTML = "";
            el.classList.add("hidden");
        }
    }
    const downloadLink = document.getElementById("download-link");
    if (downloadLink) {
        downloadLink.classList.add("hidden");
        downloadLink.href = "#";
    }
    const summary = document.getElementById("summary");
    if (summary) summary.innerHTML = "";
}

function markCompleted(n) {
    document.getElementById(`step-${n}`).classList.add("completed");
    const dot = document.getElementById(`dot-${n}`);
    if (dot) {
        dot.classList.remove("active");
        dot.classList.add("completed");
        dot.innerHTML = "✓";
    }
    const line = document.getElementById(`line-${n}`);
    if (line) line.classList.add("completed");
}

function resetWorkflow() {
    state = {
        jobId: null,
        certType: null,
        placeholders: [],
        columns: [],
        rowCount: 0,
        autoMatches: {},
        columnMapping: {},
        internalMapping: {},
    };
    document.getElementById("cert-type-select").value = "";
    document.getElementById("cert-type-info").classList.add("hidden");
    document.getElementById("template-filename").textContent = "";
    document.getElementById("data-filename").textContent = "";
    document.getElementById("template-file").value = "";
    document.getElementById("data-file").value = "";
    disableStepsFrom(2);
}

function showError(message) {
    const banner = document.getElementById("error-banner");
    banner.textContent = message;
    banner.classList.remove("hidden");
    setTimeout(() => banner.classList.add("hidden"), 8000);
}

function showLoading(elementId) {
    const el = document.getElementById(elementId);
    if (el) el.style.opacity = "0.6";
}

function hideLoading(elementId) {
    const el = document.getElementById(elementId);
    if (el) el.style.opacity = "1";
}
