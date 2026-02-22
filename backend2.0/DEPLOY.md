# CleanSight — Hackathon Deployment Guide
## From mocked → real in ~45 minutes

---

## STEP 0 — Project structure

```
cleansight-backend/
  app.py                    ← Flask server (Sphinx AI + VectorAI + /analyze)
  vector_client.py          ← Actian VectorAI gRPC wrapper
  requirements.txt
  Dockerfile
  docker-compose.yml        ← Local dev: Flask + VectorAI in one command
  .env.example              ← Copy to .env, fill in API keys
  cleansight-integration.js ← Exact frontend changes explained
```

---

## STEP 1 — Discover the VectorAI gRPC API (10 min)

The container is a black box until you inspect it.

```bash
# Pull and start the container
docker pull williamimoh/actian-vectorai-db:1.0b
docker run -d -p 50051:50051 --name vectorai williamimoh/actian-vectorai-db:1.0b

# Check what ports are actually open
docker logs vectorai
docker port vectorai

# Use grpcurl to discover the service definition automatically
pip install grpcurl    # or: brew install grpcurl
grpcurl -plaintext localhost:50051 list                 # list services
grpcurl -plaintext localhost:50051 describe             # show all methods + fields
grpcurl -plaintext localhost:50051 list <ServiceName>   # list methods of a service
```

Once you see the service name and method names, update `vector_client.py`:
- Line `vectorai_pb2_grpc.VectorDBStub` → use the real stub class name
- Line `vectorai_pb2.UpsertRequest` → use the real request message name
- Line `response.matches` → use the real response field name

### Generate proto stubs from the running container:
```bash
pip install grpcio-tools grpcio-reflection

# Save the proto to file
grpcurl -plaintext localhost:50051 describe <ServiceName> > vectorai_discovered.txt

# Or use buf to pull the full proto:
brew install buf
buf connect grpc://localhost:50051 --list-methods
```

Then compile:
```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. vectorai.proto
# This generates vectorai_pb2.py and vectorai_pb2_grpc.py
```

---

## STEP 2 — Get Sphinx AI working (10 min)

1. Sign up at the Sphinx AI portal, grab your API key
2. Copy `.env.example` → `.env`, set `SPHINX_API_KEY`
3. Check the actual model name and base URL in their docs
   - Update `SPHINX_BASE_URL` in `.env`
   - Update `"model": "sphinx-reasoning-v1"` in `app.py` line ~120
4. Test the stream locally:
   ```bash
   curl -X POST http://localhost:8080/sphinx/stream \
     -H "Content-Type: application/json" \
     -d @test_session.json
   ```

---

## STEP 3 — Run everything locally (5 min)

```bash
cd cleansight-backend
cp .env.example .env
# fill in SPHINX_API_KEY and SPHINX_BASE_URL in .env

# Option A: Docker Compose (starts both Flask + VectorAI)
docker-compose up --build

# Option B: Manually
docker run -d -p 50051:50051 williamimoh/actian-vectorai-db:1.0b
pip install -r requirements.txt
python app.py

# Test the health endpoint
curl http://localhost:8080/health
# → {"status": "ok", "service": "cleansight-backend"}

# Test analyze
curl -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"session_id":"TEST-001","surface_id":"TRAY_3A","surface_type":"tray","room_id":"ICU_12","cleaner_id":"anon_004","start_time":"2026-02-20T20:10:12Z","end_time":"2026-02-20T20:12:05Z","grid_h":3,"grid_w":4,"coverage_count_grid":[[0,1,0,0],[1,2,0,0],[0,0,0,4]],"high_touch_mask":[[0,1,1,0],[0,1,1,0],[0,0,0,0]],"wipe_events":[],"camera_id":"CAM_02"}'
```

---

## STEP 4 — Deploy to Vultr (15 min)

```bash
# 1. Create a $6/mo Vultr instance (Cloud Compute, 1 vCPU, 1GB RAM — enough for demo)
#    Or a GPU instance for the real Sphinx embedding story
#    Note your server IP: e.g. 45.63.xxx.xxx

# 2. SSH in
ssh root@45.63.xxx.xxx

# 3. Install Docker
curl -fsSL https://get.docker.com | sh

# 4. Copy your backend files to the server
scp -r cleansight-backend/ root@45.63.xxx.xxx:/opt/cleansight/

# 5. On the server: set env vars and start
cd /opt/cleansight
cp .env.example .env
nano .env   # fill in SPHINX_API_KEY etc.
docker-compose up -d --build

# 6. Open firewall port 8080
ufw allow 8080

# 7. Verify
curl http://45.63.xxx.xxx:8080/health
```

---

## STEP 5 — Wire the frontend (5 min)

Open `cleansight.html` and make **6 targeted changes** as described in
`cleansight-integration.js`. They are clearly marked with section numbers.

Key change — at the top of the Babel script, add:
```js
const BACKEND_URL = "http://45.63.xxx.xxx:8080";  // your Vultr IP
```

Then for each of the 3 mocked functions, paste in the real versions from
`cleansight-integration.js`.

---

## JUDGE DEMO FLOW

1. Open the dashboard → click **"Vultr Infra"** tab
2. Click **"One-Click Deploy"** → terminal shows real `/health` ping to Vultr
3. Go to **"Session View"** → click any session card
4. **Sphinx AI panel** streams a real structured reasoning response token by token
5. **Similar Sessions panel** shows real VectorAI DB results (cosine similarity)
6. Upload a custom JSON → get real analysis + new similar sessions

This proves:
- ✅ Vultr: real server, real endpoint, real response
- ✅ Sphinx AI: real API call, streamed reasoning over healthcare grid data
- ✅ Actian VectorAI: real embeddings stored + real similarity search

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `grpc._channel._InactiveRpcError` | VectorAI container not running or wrong port |
| `KeyError: choices` in Sphinx stream | Check model name + base URL in .env |
| CORS error in browser | Flask-CORS is set up; check `BACKEND_URL` matches your server |
| Port 8080 refused on Vultr | Run `ufw allow 8080` on the server |
| `ModuleNotFoundError: vectorai_pb2` | Run grpc_tools.protoc to generate stubs |
