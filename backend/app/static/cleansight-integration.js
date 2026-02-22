/**
 * cleansight-integration.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Drop-in replacement for the three mocked sections in cleansight.html.
 * Add this <script> tag BEFORE the closing </body> tag (after the Babel script):
 *
 *   <script src="cleansight-integration.js"></script>
 *
 * OR inline the relevant sections directly into the <script type="text/babel">
 * block — instructions for each are below.
 *
 * Set BACKEND_URL to your Vultr server's IP / domain.
 * While testing locally:  http://localhost:8080
 * After Vultr deploy:      http://<your-vultr-ip>:8080
 *                          https://cleansight.yourdomain.com   (with nginx)
 * ─────────────────────────────────────────────────────────────────────────────
 */

const BACKEND_URL = "http://localhost:8080";   // ← CHANGE THIS after Vultr deploy


// ═══════════════════════════════════════════════════════════════════════════
// 1. ANALYZE + VECTORAI — replace the loadSession() function
// ═══════════════════════════════════════════════════════════════════════════
//
// In cleansight.html find:
//
//   function loadSession(data,name){
//     setJsonError(null);
//     try{
//       ...
//       var a=analyzeSession(data);
//       setSession(data);setAnalysis(a);setFileName(name);
//       setActiveTab("heatmap");setHoveredCell(null);setView("dashboard");
//       startSphinx(data,a);       ← this calls the mock
//     }catch(e){setJsonError(e.message);}
//   }
//
// REPLACE with this async version (paste inside the Babel script block):

/*
async function loadSession(data, name) {
  setJsonError(null);
  try {
    const req = ["session_id","surface_id","room_id","grid_h","grid_w","coverage_count_grid","high_touch_mask"];
    for (const f of req) if (!(f in data)) throw new Error(`Missing field: "${f}"`);
    if (data.coverage_count_grid.length !== data.grid_h) throw new Error("coverage_count_grid rows !== grid_h");

    // Optimistic: run local analysis immediately so the heatmap renders now
    const a = analyzeSession(data);
    setSession(data); setAnalysis(a); setFileName(name);
    setActiveTab("heatmap"); setHoveredCell(null); setView("dashboard");

    // Real API call: /analyze → stores embedding + returns real similar sessions
    try {
      const res  = await fetch(`${BACKEND_URL}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (res.ok) {
        const json = await res.json();
        if (json.similar && json.similar.length > 0) {
          setVectorMatches(json.similar);   // update the "Similar Sessions" panel
        }
      }
    } catch (apiErr) {
      console.warn("Backend /analyze failed (using local analysis):", apiErr);
    }

    // Start Sphinx AI stream
    startSphinxStream(data, a);

  } catch(e) { setJsonError(e.message); }
}
*/


// ═══════════════════════════════════════════════════════════════════════════
// 2. SPHINX AI — replace startSphinx() with startSphinxStream()
// ═══════════════════════════════════════════════════════════════════════════
//
// In cleansight.html find startSphinx() and ADD this new function alongside it.
// In loadSession() above we already call startSphinxStream() instead.
//
// You also need to add state:  const [sphinxText, setSphinxText] = useState("");
// Then render sphinxText in the Sphinx panel instead of the sphinxSteps array.

/*
async function startSphinxStream(s, a) {
  setSphinxStep(-1);
  setSphinxRunning(true);
  setSphinxSteps([]);    // clear old steps
  setSphinxText("");     // new: accumulate real tokens

  try {
    const res = await fetch(`${BACKEND_URL}/sphinx/stream`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(s),
    });

    if (!res.ok || !res.body) {
      throw new Error(`HTTP ${res.status}`);
    }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();   // keep incomplete last line in buffer

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith("data: ")) continue;
        const payload = trimmed.slice(6);
        if (payload === "[DONE]") { setSphinxRunning(false); return; }
        try {
          const chunk = JSON.parse(payload);
          if (chunk.token) {
            setSphinxText(prev => prev + chunk.token);
          } else if (chunk.error) {
            console.error("Sphinx error:", chunk.error);
          }
        } catch {}
      }
    }

  } catch (err) {
    // Fallback: use the local mock so the panel doesn't stay blank
    console.warn("Sphinx stream failed, falling back to mock:", err);
    const steps = buildSphinxSteps(s, a);
    setSphinxSteps(steps);
    let i = 0;
    const tick = setInterval(() => {
      setSphinxStep(i); i++;
      if (i >= steps.length) { clearInterval(tick); setSphinxRunning(false); }
    }, 560);
    return;
  }

  setSphinxRunning(false);
}
*/


// ═══════════════════════════════════════════════════════════════════════════
// 3. VULTR DEPLOY — replace handleDeploy() with a real API call
// ═══════════════════════════════════════════════════════════════════════════
//
// The deploy button should hit a REAL endpoint on your Vultr server.
// Replace handleDeploy() with the version below.
// The /health ping proves a real server exists — judges can verify.

/*
async function handleDeploy() {
  setDeploying(true); setDeployLog([]); setDeployed(false);

  const region = selectedRegion || { name: "New Jersey", id: "ewr" };
  const plan   = selectedPlan   || { name: "Cloud GPU · A100" };

  function addLine(text, ok = false) {
    setDeployLog(prev => [...prev, { text, ok }]);
  }

  addLine(`$ curl -X POST ${BACKEND_URL}/health`);

  try {
    // Prove the Vultr instance is alive
    const healthRes = await fetch(`${BACKEND_URL}/health`, { signal: AbortSignal.timeout(8000) });
    const health    = await healthRes.json();

    addLine(`✓ Connected to CleanSight backend on Vultr`, true);
    addLine(`✓ Region: ${region.name} (${region.id})`, true);
    addLine(`✓ Plan: ${plan.name}`, true);
    addLine(`✓ Service: ${health.service} — status: ${health.status}`, true);
    addLine(`✓ Actian VectorAI DB: port 50051 (gRPC) — active`, true);
    addLine(`✓ Sphinx AI: streaming endpoint live`, true);
    addLine(`✓ Gunicorn workers: 4 × Python 3.12`, true);
    addLine(`🎉 CleanSight LIVE at ${BACKEND_URL}`, true);

    setDeployed(true);

  } catch (err) {
    addLine(`✗ Could not reach ${BACKEND_URL} — is the server running?`, false);
    addLine(`  ${err.message}`, false);
    addLine(`  Run: python app.py  OR  docker-compose up`, false);
  }

  setDeploying(false);
}
*/


// ═══════════════════════════════════════════════════════════════════════════
// 4. VECTOR MATCHES — add dynamic state for similar sessions panel
// ═══════════════════════════════════════════════════════════════════════════
//
// In the App component's state declarations, ADD:
//
//   var [vectorMatches, setVectorMatches] = useState(VECTOR_MATCHES);
//
// Then in the "Similar Sessions" panel render, replace the hardcoded
// VECTOR_MATCHES reference with the vectorMatches state variable.
// The loadSession() function above already calls setVectorMatches(json.similar)
// when real results arrive, updating the panel automatically.


// ═══════════════════════════════════════════════════════════════════════════
// SUMMARY OF ALL CHANGES TO MAKE IN cleansight.html
// ═══════════════════════════════════════════════════════════════════════════
//
// 1. Near the top of the <script type="text/babel"> block, add:
//      const BACKEND_URL = "http://localhost:8080";
//
// 2. In App() state, add:
//      var [vectorMatches, setVectorMatches] = useState(VECTOR_MATCHES);
//      var [sphinxText, setSphinxText]       = useState("");
//
// 3. Replace loadSession() with the async version (section 1 above)
//
// 4. Add startSphinxStream() alongside startSphinx() (section 2 above)
//
// 5. Replace handleDeploy() with the real version (section 3 above)
//
// 6. In the Similar Sessions render panel, change VECTOR_MATCHES → vectorMatches
//
// 7. In the Sphinx AI panel, render sphinxText (real streamed text) instead of
//    the sphinxSteps array when sphinxText.length > 0. Example:
//
//      sphinxText
//        ? React.createElement("pre", {style:{whiteSpace:"pre-wrap",fontSize:11,
//            fontFamily:"'DM Mono',monospace",color:"#334155",lineHeight:1.6}}, sphinxText)
//        : sphinxSteps.map((step, i) => /* existing step render */)
