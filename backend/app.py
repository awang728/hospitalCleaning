"""
CleanSight Backend — app.py
Runs on Vultr · calls Sphinx AI · stores/queries Actian VectorAI DB

Start:  python app.py
Env vars needed (copy .env.example → .env):
  SPHINX_API_KEY      — from Sphinx AI dashboard
  SPHINX_BASE_URL     — e.g. https://api.sphinx-ai.io/v1   (confirm with docs)
  VECTORAI_HOST       — defaults to localhost
  VECTORAI_PORT       — defaults to 50051
  VECTORAI_COLLECTION — defaults to cleansight_sessions
"""

import os, json, math, time
import numpy as np
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import requests
from dotenv import load_dotenv

load_dotenv()

from vector_client import VectorAIClient   # our gRPC wrapper (vector_client.py)

app = Flask(__name__)
CORS(app)   # allow your dashboard HTML to call this from any origin

# ── Clients ──────────────────────────────────────────────────────────────────

vector_client = VectorAIClient(
    host=os.getenv("VECTORAI_HOST", "localhost"),
    port=int(os.getenv("VECTORAI_PORT", 50051)),
    collection=os.getenv("VECTORAI_COLLECTION", "cleansight_sessions"),
)
vector_client.ensure_collection(dimension=202)

SPHINX_API_KEY = os.getenv("SPHINX_API_KEY", "")

# ── Helpers ───────────────────────────────────────────────────────────────────

RISK_ORDER = ["critical", "high", "medium", "low", "clear"]

def risk_level(coverage: int, high_touch: bool) -> str:
    if high_touch and coverage == 0: return "critical"
    if high_touch and coverage == 1: return "high"
    if not high_touch and coverage == 0: return "medium"
    if high_touch and coverage >= 2: return "low"
    return "clear"

def analyze_session(s: dict) -> dict:
    """Mirror of the JS analyzeSession() in the frontend."""
    cells = []
    for r in range(s["grid_h"]):
        for c in range(s["grid_w"]):
            cov = s["coverage_count_grid"][r][c]
            ht  = s["high_touch_mask"][r][c] == 1
            cells.append({"r": r, "c": c, "coverage": cov, "highTouch": ht, "risk": risk_level(cov, ht)})

    total_cells = s["grid_h"] * s["grid_w"]
    cleaned     = sum(1 for cell in cells if cell["coverage"] > 0)
    cov_pct     = round((cleaned / total_cells) * 100)
    ht_total    = sum(1 for cell in cells if cell["highTouch"])
    ht_uncleaned= sum(1 for cell in cells if cell["highTouch"] and cell["coverage"] == 0)

    dur_secs    = (time.mktime(time.strptime(s["end_time"], "%Y-%m-%dT%H:%M:%SZ")) -
                   time.mktime(time.strptime(s["start_time"], "%Y-%m-%dT%H:%M:%SZ")))
    dur_str     = f"{int(dur_secs//60)}m {int(dur_secs%60)}s"

    counts      = {k: 0 for k in RISK_ORDER}
    for cell in cells:
        counts[cell["risk"]] += 1

    focus       = sorted(
        [c for c in cells if c["risk"] in ("critical", "high")],
        key=lambda c: RISK_ORDER.index(c["risk"])
    )

    return {
        "cells": cells, "totalCells": total_cells, "cleaned": cleaned,
        "covPct": cov_pct, "htTotal": ht_total, "htUncleaned": ht_uncleaned,
        "durStr": dur_str, "counts": counts, "focus": focus,
    }

def session_to_vector(s: dict) -> list[float]:
    """
    Flatten the session grid into a fixed-length embedding vector.
    We normalise coverage (max clamp 5) and interleave with high_touch.
    Returns a list of floats ready to insert into VectorAI DB.
    """
    h, w = s["grid_h"], s["grid_w"]
    MAX_GRID = 10  # pad to 10×10 = 100 cells, 200 floats total (cov + ht)
    vec = []
    for r in range(MAX_GRID):
        for c in range(MAX_GRID):
            if r < h and c < w:
                cov = min(s["coverage_count_grid"][r][c], 5) / 5.0   # normalise 0-1
                ht  = float(s["high_touch_mask"][r][c])
            else:
                cov, ht = 0.0, 0.0    # padding
            vec.extend([cov, ht])
    # also append summary stats as extra dimensions
    a = analyze_session(s)
    vec.append(a["covPct"] / 100.0)
    vec.append(a["htUncleaned"] / max(a["htTotal"], 1))
    return vec


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "cleansight-backend"})


@app.route("/analyze", methods=["POST"])
def analyze():
    """
    Accepts a session JSON, returns analysis + similar sessions from VectorAI.
    Called by the frontend when a user uploads or selects a session.
    """
    s = request.get_json(force=True)
    a = analyze_session(s)

    # ── Store embedding in VectorAI ──────────────────────────────────────────
    vec = session_to_vector(s)
    print(f"[DEBUG] Upserting session {s['session_id']}, vector length {len(vec)}")
    print(f"[DEBUG] VectorAI stub: {vector_client._stub}")
    try:
        upsert_ok = vector_client.upsert(
            id=s["session_id"],
            vector=vec,
            metadata={
                "session_id":   s["session_id"],
                "room_id":      s["room_id"],
                "surface_type": s["surface_type"],
                "surface_id":   s["surface_id"],
                "cov_pct":      str(a["covPct"]),
                "risk_counts":  json.dumps(a["counts"]),
                "worst_risk":   next((k for k in RISK_ORDER if a["counts"][k] > 0), "clear"),
                "protocol":     "UV-C + double wipe" if a["counts"]["critical"] > 0 else
                                "Microfiber spray"   if a["counts"]["high"] > 0    else
                                "Standard wipe-down",
            }
        )
        print(f"[DEBUG] Upsert result: {upsert_ok}")
    except Exception as e:
        print(f"[DEBUG] Upsert EXCEPTION: {e}")

    # ── Query similar sessions ────────────────────────────────────────────────
    similar = []
    try:
        results = vector_client.query(vec, top_k=4)
        print(f"[DEBUG] Query returned {len(results)} results: {results}")
        for r in results:
            meta = r.get("metadata", {})
            if meta.get("session_id") != s["session_id"]:   # exclude self
                similar.append({
                    "id":       meta.get("session_id", r["id"]),
                    "room":     meta.get("room_id", "—"),
                    "surface":  meta.get("surface_type", "—"),
                    "sim":      round(r["score"], 3),
                    "risk":     meta.get("worst_risk", "unknown"),
                    "note":     f"Coverage {meta.get('cov_pct','?')}% · similar session",
                    "protocol": meta.get("protocol", "Standard wipe-down"),
                })
    except Exception as e:
        print(f"[DEBUG] Query EXCEPTION: {e}")

    return jsonify({
        "session_id":    s["session_id"],
        "analysis":      a,
        "similar":       similar,
        "vector_length": len(vec),
    })


@app.route("/sphinx/stream", methods=["POST"])
def sphinx_stream():
    """
    Runs Sphinx CLI on a generated notebook and streams its reasoning
    back to the dashboard as Server-Sent Events (SSE).

    Sphinx CLI receives:
      - An auto-generated .ipynb notebook with the session data pre-loaded
      - A clinical reasoning prompt
      - An output schema so it returns structured JSON at the end

    The frontend reads the stream and renders tokens in real time.
    """
    from sphinx_runner import run_sphinx_stream
    s = request.get_json(force=True)
    a = analyze_session(s)

    return Response(
        stream_with_context(run_sphinx_stream(s, a)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering on Vultr
        }
    )


@app.route("/similar", methods=["POST"])
def similar_sessions():
    """Standalone endpoint — just query VectorAI, no re-analysis."""
    s   = request.get_json(force=True)
    vec = session_to_vector(s)
    try:
        results = vector_client.query(vec, top_k=5)
        return jsonify({"similar": [r for r in results if r["id"] != s["session_id"]][:3]})
    except Exception as e:
        return jsonify({"error": str(e), "similar": []}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)