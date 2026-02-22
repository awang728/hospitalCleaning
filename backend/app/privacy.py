import os
import hashlib

ANON_SALT = os.getenv("ANON_SALT", "dev-salt")

def anon_id(raw: str) -> str:
    """
    Deterministic anonymization of identifiers.
    Same input -> same output, but not reversible without salt.
    """
    raw = (raw or "").strip().lower()
    return hashlib.sha256((ANON_SALT + raw).encode("utf-8")).hexdigest()[:16]