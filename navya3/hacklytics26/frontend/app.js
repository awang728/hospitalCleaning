// frontend/app.js

// Load real summary stats automatically when page loads
async function loadSummary() {
    const coverageEl = document.getElementById("coverage");
    const aiReportEl = document.getElementById("ai-report");

    try {
        coverageEl.innerText = "Loading summary...";

        const response = await fetch("http://127.0.0.1:8000/analytics/summary");
        
        if (!response.ok) {
            throw new Error(`Server responded with ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        // Display real stats
        coverageEl.innerText = 
            `Average Coverage: ${data.average_coverage_percent?.toFixed(1) || "N/A"}%  |  ` +
            `Total Sessions: ${data.total_sessions || 0}  |  ` +
            `High-Stress Sessions: ${data.high_stress_sessions || 0}`;

        aiReportEl.innerText = "Ready — click the button for AI-powered insights";
    } catch (error) {
        console.error("Failed to load summary:", error);
        coverageEl.innerText = "Error loading data. Make sure backend is running and has sessions saved.";
        aiReportEl.innerText = "Error: " + error.message;
    }
}

// Generate Gemini AI report when button is clicked
async function getSummary() {
    const aiReportEl = document.getElementById("ai-report");

    aiReportEl.innerText = "Generating AI insight...";

    try {
        const response = await fetch("http://127.0.0.1:8000/ai/summary", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                room_id: "Demo Room",          // you can make dynamic later
                coverage_percent: 82.0,
                duration: 120,
                stress_level: 0.6
            })
        });

        if (!response.ok) {
            throw new Error(`AI endpoint error: ${response.status}`);
        }

        const data = await response.json();

        // Show the Gemini-generated text (adjust field name if your endpoint returns differently)
        aiReportEl.innerText = data.summary || 
                              data.error || 
                              "No summary returned from AI. Check Gemini key and endpoint.";
    } catch (error) {
        console.error("Failed to get AI summary:", error);
        aiReportEl.innerText = "Error generating report: " + error.message + 
                              "\n(Check console for details or make sure GEMINI_API_KEY is set)";
    }
}

// Run loadSummary when the page fully loads
window.onload = loadSummary;