/*
 * Static-site shim for GitHub Pages.
 * The live app talks to a Flask backend (/api/*). GitHub Pages can't run Python,
 * so this intercepts those calls: GETs are served from pre-baked JSON, and the
 * interactive POSTs (approve / search / free-text triage) are handled client-side.
 * The 5 pre-analyzed referrals (click any inbox row) work fully — identical output
 * to the deterministic keyword-fallback mode.
 */
(function () {
  const realFetch = window.fetch.bind(window);
  const PER = 18; // minutes credited per approval
  let approvals = 0;
  let rejects = 0;

  function jsonResponse(obj) {
    return new Response(JSON.stringify(obj), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  window.fetch = function (input, opts) {
    const url = typeof input === "string" ? input : (input && input.url) || "";

    // ---- GET: pre-baked data ----
    if (url.indexOf("/api/triage-all") !== -1) return realFetch("./data/triage-all.json");
    if (url.indexOf("/api/approvals") !== -1) return realFetch("./data/approvals.json");

    // ---- POST: free-text triage (needs the live backend) ----
    if (url.indexOf("/api/triage") !== -1) {
      return Promise.resolve(
        jsonResponse({
          referral: { id: "free-text", patient: "Custom referral (static demo)", specialty_requested: "—" },
          analysis: {
            readiness: "Needs Review",
            confidence: 0,
            urgency: "Low",
            present_items: [],
            missing_items: ["Live AI analysis of custom referrals runs on the backend server."],
            draft_email: "",
            next_action: "Run the full app locally to analyze your own referral text.",
            routing_suggestion: "—",
            safety_note: "This is a static demo. Click any of the 5 pre-analyzed referrals in the inbox to see full results.",
            source: "static",
          },
          patient_history: null,
          analysis_without_chart: null,
        })
      );
    }

    // ---- POST: semantic search (needs the live backend) ----
    if (url.indexOf("/api/search") !== -1) {
      return Promise.resolve(
        jsonResponse({
          matching_ids: [],
          explanation:
            "Live semantic search runs on the backend. In this static demo, click the inbox rows to explore the 5 referrals.",
          source: "static",
        })
      );
    }

    // ---- POST: approve / reject (handled client-side) ----
    if (url.indexOf("/api/approve") !== -1) {
      let body = {};
      try { body = JSON.parse((opts && opts.body) || "{}"); } catch (e) {}
      const isReject = body.action === "reject";
      if (isReject) rejects++; else approvals++;
      const minutes = approvals * PER;
      return Promise.resolve(
        jsonResponse({
          stats: {
            approvals,
            rejects,
            per_approval: PER,
            minutes_saved: minutes,
            hours: Math.floor(minutes / 60),
            minutes_remainder: minutes % 60,
          },
          entry: {
            action: body.action || "approve",
            timestamp: new Date().toISOString(),
            patient: body.patient || "",
            referral_id: body.referral_id || "",
            readiness: body.readiness || "",
            notes: body.notes || "",
            minutes_credited: isReject ? 0 : PER,
          },
        })
      );
    }

    // Everything else: real network.
    return realFetch(input, opts);
  };
})();
