"""
vectorai_client.py — Actian VectorAI DB integration for CleanSight

The VectorAI DB Docker container exposes a REST API.
Pull and run it before starting the backend:

    docker pull williamimoh/actian-vectorai-db:1.0b
    docker run -d -p 50051:50051 --name vectorai williamimoh/actian-vectorai-db:1.0b

This client:
  1. upsert()  — stores a session vector + metadata
  2. search()  — finds top-K most similar past sessions
  3. ping()    — health check

Set the host/port via environment variables:
    export VECTORAI_HOST=localhost
    export VECTORAI_PORT=50051
"""

import os
import math
import requests
from typing import Optional

COLLECTION = "cleansight_sessions"   # VectorAI collection name
VECTOR_DIM  = 144                    # must match session_to_vector() in app.py


class VectorAIClient:
    def __init__(self, host: str = "localhost", port: int = 50051):
        self.base = f"http://{host}:{port}"
        self._ensure_collection()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    def _ensure_collection(self):
        """
        Create the collection if it doesn't exist yet.
        VectorAI DB uses collections (namespaces) for logical separation.
        """
        try:
            resp = requests.get(self._url(f"/collections/{COLLECTION}"), timeout=5)
            if resp.status_code == 404:
                requests.post(
                    self._url("/collections"),
                    json={
                        "name": COLLECTION,
                        "dimension": VECTOR_DIM,
                        "distance": "cosine",   # cosine similarity for grid patterns
                    },
                    timeout=5,
                ).raise_for_status()
                print(f"[VectorAI] Created collection '{COLLECTION}' (dim={VECTOR_DIM})")
            else:
                print(f"[VectorAI] Collection '{COLLECTION}' already exists")
        except requests.exceptions.ConnectionError:
            print("[VectorAI] WARNING: Cannot connect — is the Docker container running?")

    # ── Public API ────────────────────────────────────────────────────────────

    def upsert(self, id: str, vector: list[float], metadata: dict) -> bool:
        """
        Insert or update a session vector.

        VectorAI DB REST format (adjust if the API schema differs):
        POST /collections/{name}/vectors
        {
            "id": "TEST-001",
            "vector": [0.1, 0.0, ...],
            "metadata": { "room_id": "ICU_12", ... }
        }
        """
        payload = {
            "id": id,
            "vector": vector,
            "metadata": metadata,
        }
        try:
            resp = requests.post(
                self._url(f"/collections/{COLLECTION}/vectors"),
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            print(f"[VectorAI] Upserted session '{id}'")
            return True
        except requests.exceptions.RequestException as e:
            print(f"[VectorAI] Upsert failed for '{id}': {e}")
            return False

    def search(self, vector: list[float], top_k: int = 4) -> list[dict]:
        """
        Find the top_k most similar sessions by cosine similarity.

        POST /collections/{name}/search
        { "vector": [...], "top_k": 4 }

        Returns a list of:
        {
            "id":         "TEST-001",
            "score":      0.96,           # cosine similarity 0–1
            "metadata":   { ... }
        }

        Transformed for the frontend into:
        {
            "id":       "TEST-001",
            "room":     "ICU_12",
            "surface":  "tray",
            "sim":      0.96,
            "risk":     "critical",
            "note":     "...",
            "protocol": "UV-C + double wipe"
        }
        """
        payload = {"vector": vector, "top_k": top_k}
        try:
            resp = requests.post(
                self._url(f"/collections/{COLLECTION}/search"),
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            raw_results = resp.json().get("results", [])
            return [self._format_result(r) for r in raw_results]
        except requests.exceptions.RequestException as e:
            print(f"[VectorAI] Search failed: {e}")
            return []

    def ping(self) -> str:
        """Returns 'ok' or an error string — used by /health endpoint."""
        try:
            resp = requests.get(self._url("/health"), timeout=3)
            return "ok" if resp.ok else f"error {resp.status_code}"
        except Exception as e:
            return f"unreachable: {str(e)}"

    # ── Result formatting ─────────────────────────────────────────────────────

    @staticmethod
    def _format_result(raw: dict) -> dict:
        """
        Convert VectorAI DB raw search result into the shape the frontend expects
        for the 'Similar Sessions' panel.
        """
        meta = raw.get("metadata", {})
        counts = meta.get("risk_counts", {})

        # Determine worst risk level from stored metadata
        worst = "clear"
        for level in ["critical", "high", "medium", "low", "clear"]:
            if counts.get(level, 0) > 0:
                worst = level
                break

        # Auto-generate a clinical note from the metadata
        note = VectorAIClient._generate_note(counts, meta.get("cov_pct", 0))

        # Auto-recommend protocol based on risk
        protocol_map = {
            "critical": "UV-C sweep + double wipe",
            "high":     "Microfiber spray + re-wipe",
            "medium":   "Standard microfiber wipe",
            "low":      "Spot clean",
            "clear":    "Verification scan only",
        }

        return {
            "id":       raw.get("id", "unknown"),
            "room":     meta.get("room_id", "unknown"),
            "surface":  meta.get("surface_type", "unknown"),
            "sim":      round(raw.get("score", 0), 2),
            "risk":     worst,
            "note":     note,
            "protocol": protocol_map.get(worst, "Standard protocol"),
        }

    @staticmethod
    def _generate_note(counts: dict, cov_pct: float) -> str:
        """Generate a one-line clinical summary from risk counts."""
        parts = []
        if counts.get("critical", 0) > 0:
            parts.append(f"{counts['critical']} high-touch zone(s) unwiped")
        if counts.get("high", 0) > 0:
            parts.append(f"{counts['high']} zone(s) with single wipe only")
        if cov_pct < 60:
            parts.append(f"low overall coverage ({cov_pct}%)")
        if not parts:
            parts.append("adequate coverage, minor gaps")
        return ", ".join(parts).capitalize()
