"""
CleanSight Backend — app.py
Runs on Vultr. Wires Sphinx AI + Actian VectorAI DB into a single /analyze endpoint.

Start with:
    python app.py

Or with gunicorn (production):
    gunicorn -w 2 -b 0.0.0.0:5000 app:app
"""

import os
import json
import math
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

from sphinx_client import stream_sphinx_analysis
from vectorai_client import VectorAIClient

app = Flask(__name__)
CORS(app)  # Allow your frontend to call this from any origin

# ── Actian VectorAI DB client (singleton) ────────────────────────────────────
vectorai = VectorAIClient(
    host=os.getenv("VECTORAI_HOST", "localhost"),
    port=int(os.getenv("VECTORAI_PORT", 50051)),
)


# ── Risk logic (mirrors frontend) ────────────────────────────────────────────
def risk_level(coverage, high_touch):
    if high_touch and coverage == 0:   return "critical"
    if high_touch and coverage == 1:   return "high"
    if not high_touch and coverage == 0: return "medium"
    if high_touch and coverage >= 2:   return "low"
    return "clear"

RISK_SCORE = {"critical": 4, "high": 3, "medium": 2, "low": 1, "clear": 0}


def analyze_session(session: dict) -> dict:
    """Pure Python version of the frontend analyzeSession()."""
    grid_h = session["grid_h"]
    grid_w = session["grid_w"]
    coverage = session["coverage_count_grid"]
    ht_mask  = session["high_touch_mask"]

    cells = []
    counts = {k: 0 for k in ["critical", "high", "medium", "low", "clear"]}

    for r in range(grid_h):
        for c in range(grid_w):
            cov = coverage[r][c]
            ht  = ht_mask[r][c] == 1
            risk = risk_level(cov, ht)
            counts[risk] += 1
            cells.append({"r": r, "c": c, "coverage": cov, "highTouch": ht, "risk": risk})

    total  = grid_h * grid_w
    cleaned = sum(1 for cell in cells if cell["coverage"] > 0)
    ht_total = sum(1 for cell in cells if cell["highTouch"])
    ht_uncleaned = sum(1 for cell in cells if cell["highTouch"] and cell["coverage"] == 0)

    focus = sorted(
        [c for c in cells if c["risk"] in ("critical", "high")],
        key=lambda c: ["critical","high"].index(c["risk"])
    )

    return {
        "cells": cells,
        "totalCells": total,
        "cleaned": cleaned,
        "covPct": round((cleaned / total) * 100) if total else 0,
        "htTotal": ht_total,
        "htUncleaned": ht_uncleaned,
        "counts": counts,
        "focus": focus,
    }


def session_to_vector(session: dict) -> list[float]:
    """
    Flatten session grid data into a fixed-length float vector for VectorAI.

    Strategy: encode each cell as 3 features
        [coverage_normalized, is_high_touch, risk_score_normalized]
    then pad/truncate to MAX_CELLS * 3 = 144 dimensions (supports up to 6x8 grids).
    """
    MAX_CELLS = 48   # 6 rows × 8 cols — covers all test sessions
    analysis  = analyze_session(session)
    cells     = analysis["cells"]

    vector = []
    for cell in cells[:MAX_CELLS]:
        max_cov = 5.0  # normalise wipe count; clamp at 5
        vector.append(min(cell["coverage"], max_cov) / max_cov)
        vector.append(1.0 if cell["highTouch"] else 0.0)
        vector.append(RISK_SCORE[cell["risk"]] / 4.0)

    # Pad with zeros if grid is smaller than MAX_CELLS
    while len(vector) < MAX_CELLS * 3:
        vector.append(0.0)

    return vector[:MAX_CELLS * 3]


# ─────────────────────────────────────────────────────────────────────────────
# POST /analyze
# Body: CleanSight session JSON
# Returns: JSON with { analysis, similarSessions }
# Then the frontend separately calls /analyze/stream for Sphinx SSE.
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/analyze", methods=["POST"])
def analyze():
    session = request.get_json(force=True)
    if not session:
        return jsonify({"error": "No JSON body"}), 400

    required = ["session_id","surface_id","room_id","grid_h","grid_w",
                "coverage_count_grid","high_touch_mask"]
    for field in required:
        if field not in session:
            return jsonify({"error": f"Missing field: {field}"}), 400

    # ── 1. Analyse locally ───────────────────────────────────────────────────
    analysis = analyze_session(session)

    # ── 2. Build & store embedding in VectorAI DB ────────────────────────────
    vector = session_to_vector(session)
    metadata = {
        "session_id":   session["session_id"],
        "surface_type": session.get("surface_type", "unknown"),
        "room_id":      session.get("room_id", "unknown"),
        "risk_counts":  analysis["counts"],
        "cov_pct":      analysis["covPct"],
    }

    try:
        vectorai.upsert(
            id=session["session_id"],
            vector=vector,
            metadata=metadata,
        )
        # ── 3. Find top-3 most similar past sessions ─────────────────────────
        similar = vectorai.search(vector=vector, top_k=4)
        # Exclude the current session from results
        similar = [s for s in similar if s["id"] != session["session_id"]][:3]
    except Exception as e:
        print(f"[VectorAI] Error: {e}")
        similar = []

    return jsonify({
        "analysis": analysis,
        "similarSessions": similar,
    })


# ─────────────────────────────────────────────────────────────────────────────
# GET /analyze/stream?session=<URL-encoded JSON>
# Server-Sent Events stream of Sphinx AI reasoning tokens.
# The frontend opens an EventSource to this endpoint.
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/analyze/stream", methods=["POST"])
def analyze_stream():
    session  = request.get_json(force=True)
    analysis = analyze_session(session)

    def generate():
        for token in stream_sphinx_analysis(session, analysis):
            # SSE format: "data: <payload>\n\n"
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /health  — quick liveness check
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok", "vectorai": vectorai.ping()})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"[CleanSight] Backend starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
