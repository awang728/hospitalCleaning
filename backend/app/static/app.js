const API_BASE = "";

async function loadSummary() {
    const coverageEl = document.getElementById("coverage");
    try {
        const response = await fetch(`${API_BASE}/analytics/summary`);
        if (!response.ok) throw new Error(`${response.status}`);
        const data = await response.json();
        coverageEl.innerText =
            `Average Coverage: ${data.average_coverage_percent?.toFixed(1) || "N/A"}%  |  ` +
            `Total Sessions: ${data.total_sessions || 0}`;
    } catch (error) {
        console.error("Failed to load summary:", error);
        if (coverageEl) coverageEl.innerText = "Error loading data.";
    }
}

async function loadLiveStats() {
    const covEl = document.getElementById("live-coverage");
    const htEl = document.getElementById("live-hightouch");
    try {
        const res = await fetch(`${API_BASE}/analytics/live`);
        if (!res.ok) return;
        const data = await res.json();
        if (covEl) covEl.innerText = `${data.coverage_percent}%`;
        if (htEl) htEl.innerText = data.high_touch_done ? "✅ Yes" : "⏳ In progress";
    } catch (e) {
        console.error("Live stats error:", e);
    }
}

async function getSummary() {
    const aiReportEl = document.getElementById("ai-report");
    aiReportEl.innerText = "Generating AI insight...";
    try {
        const response = await fetch(`${API_BASE}/ai/summary`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                room_id: "Demo Room",
                coverage_percent: 82.0,
                duration: 120,
                stress_level: 0.6
            })
        });
        if (!response.ok) throw new Error(`AI endpoint error: ${response.status}`);
        const data = await response.json();
        aiReportEl.innerText = data.summary || "No summary returned.";
    } catch (error) {
        aiReportEl.innerText = "Error generating report: " + error.message;
    }
}

window.onload = () => {
    loadSummary();
    loadLiveStats();
    // Poll live stats every 2 seconds
    setInterval(loadLiveStats, 2000);
    // Refresh summary every 30 seconds
    setInterval(loadSummary, 30000);
};