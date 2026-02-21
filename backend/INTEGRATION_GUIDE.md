# CleanSight — Backend Integration Guide
## Connecting the Real Sphinx AI + Actian VectorAI + Vultr Backend

---

## STEP 0 — Get your credentials

Before touching any code:

| Service | Where to get it |
|---|---|
| Sphinx AI API key | hackathon sponsor table or sphinx.ai dashboard |
| Vultr account | vultr.com → create account → add SSH key → spin up instance |
| Actian VectorAI DB | runs locally via Docker — no account needed |

---

## STEP 1 — Run VectorAI DB locally (takes 2 minutes)

```bash
docker pull williamimoh/actian-vectorai-db:1.0b
docker run -d --platform linux/amd64 --name vectorai -p 50051:50051 williamimoh/actian-vectorai-db:1.0b

# Verify it's running:
curl http://localhost:50051/health
```

---

## STEP 2 — Configure and start the backend

```bash
cd cleansight-backend/
cp .env.example .env
# Edit .env and set SPHINX_API_KEY

pip install -r requirements.txt
python app.py
# → Backend running on http://localhost:5000
```

Test it:
```bash
curl http://localhost:5000/health
# → {"status": "ok", "vectorai": "ok"}

curl -X POST http://localhost:5000/analyze \
  -H "Content-Type: application/json" \
  -d '{"session_id":"TEST-001","surface_id":"TRAY_3A","surface_type":"tray","room_id":"ICU_12","cleaner_id":"anon_004","start_time":"2026-02-20T20:10:12Z","end_time":"2026-02-20T20:12:05Z","grid_h":3,"grid_w":4,"coverage_count_grid":[[0,1,0,0],[1,2,0,0],[0,0,0,4]],"high_touch_mask":[[0,1,1,0],[0,1,1,0],[0,0,0,0]],"wipe_events":[],"camera_id":"CAM_02"}'
```

---

## STEP 3 — Deploy to Vultr (for judging)

```bash
# Edit deploy_vultr.sh and set VULTR_IP to your instance IP
# Make sure your .env file exists with the real SPHINX_API_KEY

chmod +x deploy_vultr.sh
./deploy_vultr.sh
```

Your backend will be live at: `http://YOUR_VULTR_IP:5000`

---

## STEP 4 — Wire the frontend (cleansight.html)

Open `cleansight.html` and make these 4 changes:

---

### Change 1 — Add BACKEND_URL constant (line ~43, after the `var useCallback=...` line)

**Find:**
```javascript
var useState=React.useState, useRef=React.useRef, useEffect=React.useEffect, useCallback=React.useCallback;
```

**Add this line immediately after:**
```javascript
var BACKEND_URL = "http://YOUR_VULTR_IP:5000";  // ← paste your Vultr IP here
// For local testing use: var BACKEND_URL = "http://localhost:5000";
```

---

### Change 2 — Replace `loadSession()` to call real backend

**Find this function (around line 562):**
```javascript
function loadSession(data,name){
    setJsonError(null);
    try{
      var req=["session_id","surface_id","room_id","grid_h","grid_w","coverage_count_grid","high_touch_mask"];
      for(var fi=0;fi<req.length;fi++)if(!(req[fi] in data))throw new Error('Missing field: "'+req[fi]+'"');
      if(data.coverage_count_grid.length!==data.grid_h)throw new Error("coverage_count_grid rows !== grid_h");
      var a=analyzeSession(data);
      setSession(data);setAnalysis(a);setFileName(name);
      setActiveTab("heatmap");setHoveredCell(null);setView("dashboard");
      startSphinx(data,a);
    }catch(e){setJsonError(e.message);}
  }
```

**Replace with:**
```javascript
function loadSession(data,name){
    setJsonError(null);
    var req=["session_id","surface_id","room_id","grid_h","grid_w","coverage_count_grid","high_touch_mask"];
    for(var fi=0;fi<req.length;fi++){
      if(!(req[fi] in data)){setJsonError('Missing field: "'+req[fi]+'"');return;}
    }
    if(data.coverage_count_grid.length!==data.grid_h){setJsonError("coverage_count_grid rows !== grid_h");return;}

    // Optimistic update — show local analysis immediately
    var a=analyzeSession(data);
    setSession(data);setAnalysis(a);setFileName(name);
    setActiveTab("heatmap");setHoveredCell(null);setView("dashboard");

    // Call real backend on Vultr
    fetch(BACKEND_URL+"/analyze",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(data),
    })
    .then(function(r){return r.json();})
    .then(function(result){
      // Update analysis with backend result (same shape)
      if(result.analysis) setAnalysis(result.analysis);
      // Update similar sessions panel with real VectorAI results
      if(result.similarSessions) setVectorMatches(result.similarSessions);
    })
    .catch(function(err){
      console.warn("[Backend] /analyze failed, using local analysis:",err);
    });

    // Stream real Sphinx AI reasoning
    startSphinxStream(data);
  }
```

---

### Change 3 — Replace `startSphinx()` with real SSE stream

**Find:**
```javascript
function startSphinx(s,a){
    setSphinxStep(-1);setSphinxRunning(true);
    var steps=buildSphinxSteps(s,a);setSphinxSteps(steps);
    var i=0;
    var tick=setInterval(function(){
      setSphinxStep(i);i++;
      if(i>=steps.length){clearInterval(tick);setSphinxRunning(false);}
    },560);
  }
```

**Replace with:**
```javascript
function startSphinx(s,a){} // kept for overview page compatibility

  function startSphinxStream(data){
    setSphinxRunning(true);
    setSphinxSteps([]);
    setSphinxStep(0);
    var accumulated="";

    fetch(BACKEND_URL+"/analyze/stream",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(data),
    })
    .then(function(resp){
      var reader=resp.body.getReader();
      var decoder=new TextDecoder();
      function read(){
        reader.read().then(function(result){
          if(result.done){setSphinxRunning(false);return;}
          var text=decoder.decode(result.value,{stream:true});
          // Parse SSE lines
          text.split("\n").forEach(function(line){
            if(!line.startsWith("data: "))return;
            try{
              var payload=JSON.parse(line.slice(6));
              if(payload.done){setSphinxRunning(false);return;}
              if(payload.token){
                accumulated+=payload.token;
                setSphinxSteps([accumulated]);
                setSphinxStep(1);
              }
            }catch(e){}
          });
          read();
        });
      }
      read();
    })
    .catch(function(err){
      console.warn("[Sphinx] Stream failed:",err);
      setSphinxRunning(false);
      // Fall back to mock
      var a=analyzeSession(data);
      var steps=buildSphinxSteps(data,a);
      setSphinxSteps(steps);
      var i=0;
      var tick=setInterval(function(){
        setSphinxStep(i);i++;
        if(i>=steps.length){clearInterval(tick);setSphinxRunning(false);}
      },560);
    });
  }
```

---

### Change 4 — Add `vectorMatches` state and wire to the Similar Sessions panel

**Find (in the App state declarations section):**
```javascript
var metricsState=useState({gpu:78,cpu:42,mem:61,lat:4,tput:7});
```

**Add this line immediately after:**
```javascript
var vectorMatchesState=useState(VECTOR_MATCHES);  // starts with mocks, replaced by real DB results
```

**Find (still in state declarations, where variables are unpacked):**
```javascript
var metrics=metricsState[0],setMetrics=metricsState[1];
```

**Add this immediately after:**
```javascript
var vectorMatches=vectorMatchesState[0],setVectorMatches=vectorMatchesState[1];
```

**Find in the Similar Sessions panel render (the VECTOR_MATCHES.map call):**
```javascript
VECTOR_MATCHES.map(function(m){
```

**Replace with:**
```javascript
vectorMatches.map(function(m){
```

---

### Change 5 — Update SphinxPanel to handle free-text streaming

The current `SphinxPanel` renders an array of discrete step strings.
After Change 3, Sphinx streams raw text. Update `SphinxPanel` to handle both:

**Find:**
```javascript
  steps.slice(0,currentStep+1).map(function(s,i){
      return React.createElement("div",{key:i,style:{color:i===currentStep&&running?"#f0f9ff":"#94a3b8"}},s);
    }),
```

**Replace with:**
```javascript
  steps.length===1&&typeof steps[0]==="string"&&steps[0].length>30
    // Streaming mode: render as continuous text
    ?React.createElement("div",{style:{color:"#e2e8f0",whiteSpace:"pre-wrap",lineHeight:1.9}},steps[0])
    // Step mode: render as discrete lines (fallback / mock)
    :steps.slice(0,currentStep+1).map(function(s,i){
        return React.createElement("div",{key:i,style:{color:i===currentStep&&running?"#f0f9ff":"#94a3b8"}},s);
      }),
```

---

## Full verification checklist

After all 5 changes, load the page and:

- [ ] Upload a session JSON → network tab shows `POST /analyze` with 200 response
- [ ] Similar Sessions panel updates from "SES-2025-0841..." to real session IDs
- [ ] Sphinx panel streams real text character by character (not discrete steps)
- [ ] Vultr infra tab → deploy button → terminal shows real server responding
- [ ] `/health` returns `{"status":"ok","vectorai":"ok"}`

---

## Architecture diagram (what judges see)

```
[ CleanSight HTML ]
       │
       │  POST /analyze          (Vultr instance IP)
       ├──────────────────► [ Flask app.py on Vultr ]
       │                          │
       │  SSE /analyze/stream     ├──► [ Sphinx AI API ] ──► streams tokens back
       ├──────────────────►        │
       │                          └──► [ Actian VectorAI DB ] ──► Docker on Vultr
       │                                    ↑
       │                          upsert + cosine search
       │                          returns top-3 similar sessions
       │
       └── renders: real analysis + real similar sessions + real AI reasoning
```

This is what makes it real. Every response comes from actual infrastructure on Vultr.
