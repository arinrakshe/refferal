// Referral Ready — frontend logic.
// Loads sample referrals, sends triage requests to the Flask backend,
// and renders the AI analysis with a human approval checklist.

const state = {
    bulk: [], // array of { referral, patient_history, analysis, analysis_without_chart, aging }
    selectedReferral: null,
    lastAnalysis: null,
    stats: { approvals: 0, rejects: 0, minutes_saved: 0, per_approval: 18 },
};

const el = (id) => document.getElementById(id);

// ─────────────────────────── boot ───────────────────────────
window.addEventListener("DOMContentLoaded", async () => {
    bindUi();
    await Promise.all([loadBulk(), loadApprovals()]);
});

async function loadApprovals() {
    try {
        const res = await fetch("/api/approvals");
        const data = await res.json();
        if (data.stats) updateStats(data.stats, { animate: false });
        if (data.log) renderApprovalLog(data.log);
    } catch (err) {
        console.warn("approval log load failed", err);
    }
}

async function loadBulk() {
    setStatus("busy", "Pre-analyzing inbox…");
    try {
        const res = await fetch("/api/triage-all");
        const data = await res.json();
        state.bulk = data.results || [];
        renderInboxTable();
        renderAgingTable();
        const usingAzure = state.bulk.some(
            (r) => r.analysis && r.analysis.source === "azure_openai"
        );
        setStatus(
            usingAzure ? "ok" : "err",
            usingAzure
                ? "Azure OpenAI · GPT-5.4-mini"
                : "Fallback rules (Azure unreachable)"
        );
    } catch (err) {
        console.error(err);
        setStatus("err", "Failed to load");
        el("inbox-rows").innerHTML =
            '<tr class="inbox-error"><td colspan="6">Could not load the inbox. Check the server log.</td></tr>';
    }
}

function bindUi() {
    bindSearchUi();

    el("analyze-free").addEventListener("click", () => {
        const text = el("free-text").value.trim();
        if (!text) {
            shakeInput();
            return;
        }
        clearInboxSelection();
        triage({ free_text: text });
    });

    el("approve-btn").addEventListener("click", onApprove);
    el("reject-btn").addEventListener("click", onReject);
    el("reset-btn").addEventListener("click", resetResult);

    document.querySelectorAll(".approve-check").forEach((cb) => {
        cb.addEventListener("change", updateApproveButton);
    });
}

// ─────────────────────────── global AI search ───────────────────────────
function bindSearchUi() {
    const form = el("search-form");
    const input = el("search-input");
    const clearBtn = el("search-clear");

    form.addEventListener("submit", (e) => {
        e.preventDefault();
        runSearch(input.value);
    });

    clearBtn.addEventListener("click", () => clearSearch());

    el("search-result-clear").addEventListener("click", () => clearSearch());

    document.querySelectorAll(".search-chip").forEach((chip) => {
        chip.addEventListener("click", () => {
            input.value = chip.textContent;
            runSearch(input.value);
        });
    });

    input.addEventListener("input", () => {
        clearBtn.classList.toggle("hidden", !input.value);
    });
}

async function runSearch(rawQuery) {
    const query = (rawQuery || "").trim();
    if (!query) return;

    const resultBox = el("search-result");
    const sendBtn = el("search-send");
    sendBtn.disabled = true;
    resultBox.classList.remove("hidden");
    resultBox.classList.add("is-loading");
    el("search-count").textContent = "Searching…";
    el("search-explanation").textContent = "Asking GPT-5.4-mini to filter the queue…";
    el("search-match-list").innerHTML = "";

    setStatus("busy", `Searching: ${query}`);

    try {
        const res = await fetch("/api/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query }),
        });
        if (!res.ok) {
            const errBody = await res.json().catch(() => ({}));
            throw new Error(errBody.error || `HTTP ${res.status}`);
        }
        const data = await res.json();
        renderSearchResult(data);
        applySearchHighlight(data.matching_ids || []);
        setStatus(
            data.source === "azure_openai" ? "ok" : "err",
            data.source === "azure_openai"
                ? "Azure OpenAI · GPT-5.4-mini"
                : "Keyword fallback (Azure unreachable)"
        );
    } catch (err) {
        console.error(err);
        renderSearchError(err.message || "Search failed.");
        setStatus("err", "Search failed");
    } finally {
        sendBtn.disabled = false;
        resultBox.classList.remove("is-loading");
    }
}

function renderSearchResult(data) {
    const count = (data.matching_ids || []).length;
    const countEl = el("search-count");
    countEl.textContent = `${count} match${count === 1 ? "" : "es"}`;
    countEl.classList.toggle("search-result__count--zero", count === 0);

    el("search-explanation").textContent =
        data.explanation || "No explanation returned.";

    const list = el("search-match-list");
    list.innerHTML = "";
    (data.matching_ids || []).forEach((refId) => {
        const idx = state.bulk.findIndex((r) => r.referral.id === refId);
        if (idx === -1) return;
        const patient = state.bulk[idx].referral.patient;
        const li = document.createElement("li");
        li.textContent = patient;
        li.title = `Open ${patient}'s referral`;
        li.addEventListener("click", () => selectByIndex(idx, null, "#inbox-rows"));
        list.appendChild(li);
    });
}

function renderSearchError(message) {
    el("search-count").textContent = "Error";
    el("search-explanation").textContent = message;
    el("search-match-list").innerHTML = "";
    applySearchHighlight([]);
}

function applySearchHighlight(matchingIds) {
    const matchSet = new Set(matchingIds);
    const allRows = document.querySelectorAll(
        "#inbox-rows tr[data-ref-idx], #aging-rows tr[data-ref-id]"
    );
    allRows.forEach((row) => {
        const refId =
            row.dataset.refId ||
            (state.bulk[row.dataset.refIdx] &&
                state.bulk[row.dataset.refIdx].referral.id);
        if (matchSet.has(refId)) {
            row.classList.add("is-search-match");
            row.classList.remove("is-search-dim");
        } else if (matchSet.size > 0) {
            row.classList.add("is-search-dim");
            row.classList.remove("is-search-match");
        } else {
            row.classList.remove("is-search-match", "is-search-dim");
        }
    });
}

function clearSearch() {
    el("search-input").value = "";
    el("search-clear").classList.add("hidden");
    el("search-result").classList.add("hidden");
    applySearchHighlight([]);
    setStatus("idle", "Idle");
}

// ─────────────────────────── inbox table ───────────────────────────
function renderInboxTable() {
    const tbody = el("inbox-rows");
    tbody.innerHTML = "";
    const totals = { ready: 0, missing: 0, review: 0 };

    state.bulk.forEach((result, idx) => {
        const ref = result.referral;
        const analysis = result.analysis || {};
        const readiness = analysis.readiness || "Needs Review";

        if (readiness === "Ready") totals.ready++;
        else if (readiness === "Missing Info") totals.missing++;
        else totals.review++;

        const topMissing =
            (analysis.missing_items && analysis.missing_items[0]) ||
            (readiness === "Ready" ? "—" : "(unspecified)");
        const urgencyKey = (analysis.urgency || "Low").toLowerCase();

        const tr = document.createElement("tr");
        tr.dataset.refIdx = idx;
        tr.dataset.refId = ref.id;
        tr.innerHTML = `
            <td class="cell-patient">
                ${escapeHtml(ref.patient)}
                <span class="meta">${escapeHtml(ref.referring_provider || "")}</span>
            </td>
            <td>${escapeHtml(ref.specialty_requested || "")}</td>
            <td><span class="badge ${badgeClass(readiness)}">${escapeHtml(readiness)}</span></td>
            <td class="urgency-cell"><span class="urgency-icon urgency-icon--${urgencyKey}">${escapeHtml(analysis.urgency || "—")}</span></td>
        `;
        tr.addEventListener("click", () => onInboxRowClick(idx, tr));
        tbody.appendChild(tr);
    });

    el("inbox-count").textContent = state.bulk.length;
    el("inbox-count-ready").textContent = totals.ready;
    el("inbox-count-missing").textContent = totals.missing;
    el("inbox-count-review").textContent = totals.review;
}

function onInboxRowClick(idx, tr) {
    selectByIndex(idx, tr, "#inbox-rows");
}

function selectByIndex(idx, tr, tableSelector) {
    clearInboxSelection();
    // Mark active row in BOTH tables for the same referral
    const result = state.bulk[idx];
    if (!result) return;
    const refId = result.referral.id;
    document.querySelectorAll(`#inbox-rows tr[data-ref-idx="${idx}"]`).forEach((n) => n.classList.add("active"));
    document.querySelectorAll(`#aging-rows tr[data-ref-id="${refId}"]`).forEach((n) => n.classList.add("active"));
    if (tr) tr.classList.add("active");

    el("free-text").value = "";
    state.selectedReferral = result.referral;
    state.lastAnalysis = result.analysis;

    el("empty-state").classList.add("hidden");
    el("result").classList.remove("hidden");

    renderResult(
        result.referral,
        result.analysis,
        result.patient_history,
        result.analysis_without_chart
    );

    el("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

function clearInboxSelection() {
    document.querySelectorAll("#inbox-rows tr, #aging-rows tr").forEach((node) => {
        node.classList.remove("active");
    });
}

// ─────────────────────────── aging dashboard ───────────────────────────
function renderAgingTable() {
    const tbody = el("aging-rows");
    tbody.innerHTML = "";
    const totals = { red: 0, yellow: 0, green: 0 };

    // Pair each result with its original bulk index, then sort by days_idle desc.
    const rows = state.bulk
        .map((result, idx) => ({ idx, result }))
        .filter(({ result }) => result.aging && result.aging.days_idle !== null)
        .sort((a, b) => b.result.aging.days_idle - a.result.aging.days_idle);

    rows.forEach(({ idx, result }) => {
        const ref = result.referral;
        const aging = result.aging;
        const stale = aging.staleness; // red | yellow | green
        if (totals[stale] !== undefined) totals[stale]++;

        const daysWord = aging.days_idle === 1 ? "day" : "days";
        const riskPill = aging.leakage_risk
            ? '<span class="risk-pill risk-pill--red">Leakage risk</span>'
            : stale === "yellow"
                ? '<span class="risk-pill risk-pill--yellow">Watch</span>'
                : '<span class="risk-pill risk-pill--green">Recent</span>';

        const tr = document.createElement("tr");
        tr.dataset.refId = ref.id;
        tr.dataset.refIdx = idx;
        if (stale === "red") tr.classList.add("is-red");
        tr.innerHTML = `
            <td class="cell-patient">
                ${escapeHtml(ref.patient)}
                <span class="meta">${escapeHtml(aging.received_display)}</span>
            </td>
            <td>${escapeHtml(ref.specialty_requested || "")}</td>
            <td class="u-right"><span class="days-idle">${aging.days_idle}</span> <span class="days-idle__sub">${daysWord} idle</span></td>
            <td>${riskPill}</td>
        `;
        tr.addEventListener("click", () => selectByIndex(idx, tr, "#aging-rows"));
        tbody.appendChild(tr);
    });

    el("aging-count-red").textContent = totals.red;
    el("aging-count-yellow").textContent = totals.yellow;
    el("aging-count-green").textContent = totals.green;
}

// ─────────────────────────── triage call ───────────────────────────
async function triage(body) {
    setStatus("busy", "Analyzing referral…");
    showEmpty(false);
    showLoadingResult();

    try {
        const res = await fetch("/api/triage", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const errBody = await res.json().catch(() => ({}));
            throw new Error(errBody.error || `HTTP ${res.status}`);
        }
        const data = await res.json();
        state.selectedReferral = data.referral;
        state.lastAnalysis = data.analysis;
        renderResult(
            data.referral,
            data.analysis,
            data.patient_history,
            data.analysis_without_chart
        );
        setStatus(
            data.analysis.source === "azure_openai" ? "ok" : "err",
            data.analysis.source === "azure_openai"
                ? "Azure OpenAI · GPT-4o"
                : "Fallback rules (Azure unreachable)"
        );
    } catch (err) {
        console.error(err);
        setStatus("err", "Analysis failed");
        showError(err.message);
    }
}

// ─────────────────────────── render result ───────────────────────────
function renderResult(referral, analysis, patientHistory, analysisWithoutChart) {
    el("empty-state").classList.add("hidden");
    el("result").classList.remove("hidden");

    el("result-patient").textContent = referral.patient;
    el("result-specialty").textContent =
        `${referral.specialty_requested} · referred by ${referral.referring_provider}`;

    // Badge
    const badge = el("readiness-badge");
    badge.textContent = analysis.readiness;
    badge.className = "badge " + badgeClass(analysis.readiness);

    // Meta cards
    el("confidence-value").textContent = analysis.confidence;
    el("urgency-value").textContent = analysis.urgency;
    el("source-value").textContent =
        analysis.source === "azure_openai" ? "Azure GPT-5.4-mini" : "Fallback rules";

    // Routing recommendation card
    renderRoutingCard(analysis.routing_suggestion);

    // Patient history panel
    renderPatientHistory(patientHistory);

    // Before / After comparison panel
    renderComparePanel(analysis, analysisWithoutChart, !!patientHistory);

    // Present / missing lists
    renderList("present-list", analysis.present_items);
    renderList("missing-list", analysis.missing_items);

    // Next action
    el("next-action-text").textContent =
        analysis.next_action || "No specific next action returned.";

    // Email block — hide if nothing to send
    const emailBlock = el("email-block");
    if (analysis.draft_email && analysis.draft_email.trim().length > 0) {
        emailBlock.classList.remove("hidden");
        el("draft-email").value = analysis.draft_email;
    } else {
        emailBlock.classList.add("hidden");
        el("draft-email").value = "";
    }

    el("safety-note-text").textContent = analysis.safety_note;

    // Reset checklist + approval
    document.querySelectorAll(".approve-check").forEach((cb) => (cb.checked = false));
    updateApproveButton();
    hideToast();
}

function renderComparePanel(withChart, withoutChart, hasHistory) {
    const panel = el("compare-panel");
    if (!hasHistory || !withoutChart) {
        panel.classList.add("hidden");
        return;
    }
    panel.classList.remove("hidden");

    // Before column
    const beforeBadge = el("cmp-before-badge");
    beforeBadge.textContent = withoutChart.readiness;
    beforeBadge.className = "badge " + badgeClass(withoutChart.readiness);
    el("cmp-before-urgency").textContent = withoutChart.urgency;
    el("cmp-before-confidence").textContent = withoutChart.confidence;
    renderList("cmp-before-missing", withoutChart.missing_items);
    el("cmp-before-next").textContent = withoutChart.next_action || "—";

    // After column
    const afterBadge = el("cmp-after-badge");
    afterBadge.textContent = withChart.readiness;
    afterBadge.className = "badge " + badgeClass(withChart.readiness);
    el("cmp-after-urgency").textContent = withChart.urgency;
    el("cmp-after-confidence").textContent = withChart.confidence;
    renderList("cmp-after-missing", withChart.missing_items);
    el("cmp-after-next").textContent = withChart.next_action || "—";

    // Auto-generated "what changed" callout
    renderDelta(withChart, withoutChart);
}

function renderDelta(withChart, withoutChart) {
    const delta = el("compare-delta");
    const changes = [];
    if (withChart.readiness !== withoutChart.readiness) {
        changes.push(
            `<strong>Readiness</strong> shifted from <em>${withoutChart.readiness}</em> to <em>${withChart.readiness}</em>`
        );
    }
    if (withChart.urgency !== withoutChart.urgency) {
        changes.push(
            `<strong>Urgency</strong> changed from <em>${withoutChart.urgency}</em> to <em>${withChart.urgency}</em>`
        );
    }
    const confDiff = withChart.confidence - withoutChart.confidence;
    if (Math.abs(confDiff) >= 5) {
        const sign = confDiff > 0 ? "+" : "";
        changes.push(`<strong>Confidence</strong> ${sign}${confDiff} pts`);
    }
    const beforeMissing = (withoutChart.missing_items || []).length;
    const afterMissing = (withChart.missing_items || []).length;
    if (beforeMissing !== afterMissing) {
        changes.push(
            `<strong>Missing-info flags</strong> ${beforeMissing} → ${afterMissing}`
        );
    }
    if (changes.length === 0) {
        delta.classList.add("hidden");
        return;
    }
    delta.classList.remove("hidden");
    delta.innerHTML =
        "✨ Patient history changed the analysis: " + changes.join(" · ") + ".";
}

function renderRoutingCard(suggestion) {
    const card = el("routing-card");
    const text = (suggestion || "").trim();
    if (!text) {
        card.classList.add("hidden");
        return;
    }
    card.classList.remove("hidden");
    el("routing-text").textContent = text;
}

function renderPatientHistory(history) {
    const panel = el("history-panel");
    const banner = el("no-history-banner");
    if (!history) {
        panel.classList.add("hidden");
        banner.classList.remove("hidden");
        return;
    }
    banner.classList.add("hidden");
    panel.classList.remove("hidden");

    el("history-id").textContent = history.patient_id || "";
    el("history-age").textContent = history.age ? `${history.age}` : "—";
    el("history-doctor").textContent = history.referring_doctor || "—";
    el("history-insurance").textContent = history.insurance || "Not on file";

    renderList("history-conditions", history.conditions || []);
    renderList("history-medications", history.medications || []);
    renderList("history-visits", history.recent_visits || []);
}

function renderList(id, items) {
    const node = el(id);
    node.innerHTML = "";
    (items || []).forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        node.appendChild(li);
    });
}

function badgeClass(readiness) {
    switch ((readiness || "").toLowerCase()) {
        case "ready":
            return "badge--ready";
        case "missing info":
            return "badge--missing";
        default:
            return "badge--review";
    }
}

// ─────────────────────────── approval flow ───────────────────────────
function updateApproveButton() {
    const allChecked = Array.from(document.querySelectorAll(".approve-check")).every(
        (cb) => cb.checked
    );
    el("approve-btn").disabled = !allChecked;
}

async function onApprove() {
    if (!state.selectedReferral) return;
    const notes = el("coord-notes-input").value.trim();
    const readiness = state.lastAnalysis ? state.lastAnalysis.readiness : "";
    try {
        const res = await fetch("/api/approve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                referral_id: state.selectedReferral.id,
                patient: state.selectedReferral.patient,
                action: "approve",
                readiness,
                notes,
            }),
        });
        const data = await res.json();
        if (data.stats) updateStats(data.stats, { animate: true });
        if (data.entry) prependApprovalLogEntry(data.entry);
    } catch (err) {
        console.warn("approval log failed", err);
    }
    let message;
    if (readiness === "Ready") {
        message = "✅ Approved. Forwarded to scheduling. (+18 min saved)";
    } else if (readiness === "Missing Info") {
        message = "✅ Approved. Draft email queued for the referring office. (+18 min saved)";
    } else {
        message = "✅ Approved. Escalated to clinical reviewer. (+18 min saved)";
    }
    showToast(message, "ok");
    el("coord-notes-input").value = "";
}

async function onReject() {
    if (!state.selectedReferral) return;
    const notes = el("coord-notes-input").value.trim();
    const readiness = state.lastAnalysis ? state.lastAnalysis.readiness : "";
    try {
        const res = await fetch("/api/approve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                referral_id: state.selectedReferral.id,
                patient: state.selectedReferral.patient,
                action: "reject",
                readiness,
                notes,
            }),
        });
        const data = await res.json();
        if (data.stats) updateStats(data.stats, { animate: false });
        if (data.entry) prependApprovalLogEntry(data.entry);
    } catch (err) {
        console.warn("reject log failed", err);
    }
    showToast("Rejected. Routed back to intake queue for manual review.", "reject");
    el("coord-notes-input").value = "";
}

function resetResult() {
    state.selectedReferral = null;
    state.lastAnalysis = null;
    clearInboxSelection();
    el("free-text").value = "";
    el("result").classList.add("hidden");
    el("empty-state").classList.remove("hidden");
    setStatus("idle", "Idle");
    hideToast();
}

// ─────────────────────────── stats + approval log ───────────────────────────
function updateStats(newStats, opts = {}) {
    const oldMinutes = state.stats.minutes_saved || 0;
    state.stats = { ...state.stats, ...newStats };

    const minutesEl = el("stats-minutes");
    const approvalsEl = el("stats-approvals");
    const rejectsEl = el("stats-rejects");
    const subEl = el("stats-hours-sub");

    if (opts.animate && newStats.minutes_saved !== oldMinutes) {
        animateCount(minutesEl, oldMinutes, newStats.minutes_saved, 600);
        const bumpTarget = minutesEl.closest(".topstat__value") || minutesEl;
        bumpTarget.classList.add("bump");
        setTimeout(() => bumpTarget.classList.remove("bump"), 280);
    } else {
        minutesEl.textContent = newStats.minutes_saved;
    }
    approvalsEl.textContent = newStats.approvals;
    rejectsEl.textContent = newStats.rejects;
    const h = newStats.hours ?? Math.floor(newStats.minutes_saved / 60);
    const m = newStats.minutes_remainder ?? newStats.minutes_saved % 60;
    subEl.textContent = `${h}h ${m}m · ${newStats.per_approval || 18} min saved per approval`;
}

function animateCount(node, from, to, durationMs) {
    const start = performance.now();
    const step = (now) => {
        const t = Math.min(1, (now - start) / durationMs);
        const eased = 1 - Math.pow(1 - t, 3);
        const v = Math.round(from + (to - from) * eased);
        node.textContent = v;
        if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}

function renderApprovalLog(entries) {
    const list = el("approval-log");
    const pill = el("log-empty-pill");
    list.innerHTML = "";
    if (!entries.length) {
        list.innerHTML =
            '<li class="approval-log__empty">When you approve or reject a referral below, it shows up here.</li>';
        pill.textContent = "No actions yet";
        return;
    }
    pill.textContent = `${entries.length} action${entries.length === 1 ? "" : "s"} logged`;
    entries.forEach((entry) => list.appendChild(buildApprovalLogNode(entry)));
}

function prependApprovalLogEntry(entry) {
    const list = el("approval-log");
    const pill = el("log-empty-pill");
    // Drop the empty-state placeholder if present.
    const placeholder = list.querySelector(".approval-log__empty");
    if (placeholder) placeholder.remove();
    list.prepend(buildApprovalLogNode(entry));
    const count = list.querySelectorAll(".approval-log__entry").length;
    pill.textContent = `${count} action${count === 1 ? "" : "s"} logged`;
}

function buildApprovalLogNode(entry) {
    const li = document.createElement("li");
    li.className =
        "approval-log__entry approval-log__entry--" + (entry.action || "approve");
    const time = (entry.timestamp || "").split("T")[1]?.slice(0, 5) || "";
    const icon = entry.action === "reject" ? "✕" : "✓";
    const creditClass =
        entry.action === "reject"
            ? "approval-log__credit--reject"
            : "approval-log__credit";
    const creditLabel =
        entry.action === "reject"
            ? "no credit"
            : `+${entry.minutes_credited || 18} min`;
    const verb = entry.action === "reject" ? "Rejected" : "Approved";
    const notesBlock = entry.notes
        ? `<div class="approval-log__notes">${escapeHtml(entry.notes)}</div>`
        : "";
    li.innerHTML = `
        <div class="approval-log__icon">${icon}</div>
        <div class="approval-log__body">
            <div class="approval-log__title">${verb} · ${escapeHtml(entry.patient || "Unknown patient")}</div>
            <div class="approval-log__meta">
                ${escapeHtml(entry.referral_id || "")}
                · ${escapeHtml(entry.readiness || "—")}
                · ${time || ""}
            </div>
            ${notesBlock}
        </div>
        <div class="${creditClass}">${creditLabel}</div>
    `;
    return li;
}

// ─────────────────────────── status + UI helpers ───────────────────────────
function setStatus(kind, text) {
    const dot = el("ai-status");
    dot.className = "status-dot status-dot--" + kind;
    el("ai-status-text").textContent = text;
}

function showEmpty(visible) {
    el("empty-state").classList.toggle("hidden", !visible);
    el("result").classList.toggle("hidden", visible);
}

function showLoadingResult() {
    el("result").classList.remove("hidden");
    el("empty-state").classList.add("hidden");
    el("result-patient").textContent = "Analyzing…";
    el("result-specialty").textContent = "Sending to Azure OpenAI (with fallback ready)";
    const badge = el("readiness-badge");
    badge.textContent = "…";
    badge.className = "badge";
    el("confidence-value").textContent = "—";
    el("urgency-value").textContent = "—";
    el("source-value").textContent = "—";
    el("present-list").innerHTML = "";
    el("missing-list").innerHTML = "";
    el("routing-card").classList.add("hidden");
    el("history-panel").classList.add("hidden");
    el("no-history-banner").classList.add("hidden");
    el("compare-panel").classList.add("hidden");
    el("compare-delta").classList.add("hidden");
    el("next-action-text").textContent = "";
    el("draft-email").value = "";
    el("email-block").classList.add("hidden");
    el("safety-note-text").textContent = "";
    document.querySelectorAll(".approve-check").forEach((cb) => (cb.checked = false));
    const notesField = el("coord-notes-input");
    if (notesField) notesField.value = "";
    updateApproveButton();
    hideToast();
}

function showError(message) {
    const badge = el("readiness-badge");
    badge.textContent = "Error";
    badge.className = "badge badge--review";
    el("result-patient").textContent = "Could not analyze referral";
    el("result-specialty").textContent = message || "Unknown error";
}

function showToast(message, kind) {
    const t = el("toast");
    t.textContent = message;
    t.className = "toast" + (kind === "reject" ? " toast--reject" : "");
    t.classList.remove("hidden");
}

function hideToast() {
    el("toast").classList.add("hidden");
}

function shakeInput() {
    const ta = el("free-text");
    ta.focus();
    ta.style.borderColor = "#b91c1c";
    setTimeout(() => (ta.style.borderColor = ""), 800);
}

function escapeHtml(s) {
    return String(s ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
