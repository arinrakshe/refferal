// Referral Ready — frontend logic.
// Loads sample referrals, sends triage requests to the Flask backend,
// and renders the AI analysis with a human approval checklist.

const state = {
    referrals: [],
    selectedReferral: null,
    lastAnalysis: null,
};

const el = (id) => document.getElementById(id);

// ─────────────────────────── boot ───────────────────────────
window.addEventListener("DOMContentLoaded", async () => {
    await loadReferrals();
    bindUi();
});

async function loadReferrals() {
    setStatus("busy", "Loading referrals…");
    try {
        const res = await fetch("/api/referrals");
        const data = await res.json();
        state.referrals = data.referrals || [];
        renderReferralList();
        setStatus("idle", "Idle");
    } catch (err) {
        console.error(err);
        setStatus("err", "Failed to load");
        el("referral-list").innerHTML =
            '<li class="referral-list__loading">Could not load referrals. Check the server log.</li>';
    }
}

function bindUi() {
    el("analyze-free").addEventListener("click", () => {
        const text = el("free-text").value.trim();
        if (!text) {
            shakeInput();
            return;
        }
        clearListSelection();
        triage({ free_text: text });
    });

    el("approve-btn").addEventListener("click", onApprove);
    el("reject-btn").addEventListener("click", onReject);
    el("reset-btn").addEventListener("click", resetResult);

    document.querySelectorAll(".approve-check").forEach((cb) => {
        cb.addEventListener("change", updateApproveButton);
    });
}

// ─────────────────────────── referral list ───────────────────────────
function renderReferralList() {
    const list = el("referral-list");
    list.innerHTML = "";
    state.referrals.forEach((ref) => {
        const li = document.createElement("li");
        li.className = "item";
        li.dataset.refId = ref.id;
        li.innerHTML = `
            <div class="item-title">${escapeHtml(ref.patient)}</div>
            <div class="item-sub">${escapeHtml(ref.specialty_requested)} · ${escapeHtml(ref.referring_provider)}</div>
            <div class="item-tag">${escapeHtml(ref.label || "Sample")}</div>
        `;
        li.addEventListener("click", () => onReferralClick(ref, li));
        list.appendChild(li);
    });
}

function onReferralClick(ref, li) {
    clearListSelection();
    li.classList.add("active");
    el("free-text").value = "";
    triage({ referral: ref });
}

function clearListSelection() {
    document.querySelectorAll(".referral-list .item").forEach((node) => {
        node.classList.remove("active");
    });
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
        renderResult(data.referral, data.analysis);
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
function renderResult(referral, analysis) {
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
        analysis.source === "azure_openai" ? "Azure GPT-4o" : "Fallback rules";

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
    try {
        await fetch("/api/approve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                referral_id: state.selectedReferral.id,
                action: "approve",
            }),
        });
    } catch (err) {
        console.warn("approval log failed", err);
    }
    const readiness = state.lastAnalysis ? state.lastAnalysis.readiness : "";
    let message;
    if (readiness === "Ready") {
        message = "✅ Approved. Forwarded to scheduling.";
    } else if (readiness === "Missing Info") {
        message = "✅ Approved. Draft email queued for the referring office.";
    } else {
        message = "✅ Approved. Escalated to clinical reviewer.";
    }
    showToast(message, "ok");
}

async function onReject() {
    if (!state.selectedReferral) return;
    try {
        await fetch("/api/approve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                referral_id: state.selectedReferral.id,
                action: "reject",
            }),
        });
    } catch (err) {
        console.warn("reject log failed", err);
    }
    showToast("Rejected. Routed back to intake queue for manual review.", "reject");
}

function resetResult() {
    state.selectedReferral = null;
    state.lastAnalysis = null;
    clearListSelection();
    el("free-text").value = "";
    el("result").classList.add("hidden");
    el("empty-state").classList.remove("hidden");
    setStatus("idle", "Idle");
    hideToast();
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
    el("next-action-text").textContent = "";
    el("draft-email").value = "";
    el("email-block").classList.add("hidden");
    el("safety-note-text").textContent = "";
    document.querySelectorAll(".approve-check").forEach((cb) => (cb.checked = false));
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
