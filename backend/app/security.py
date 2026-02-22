import os
from fastapi import Header, HTTPException

INGEST_API_KEY = os.getenv("INGEST_API_KEY", "")

def require_ingest_key(x_api_key: str | None = Header(default=None)) -> None:
    if not INGEST_API_KEY:
        # If you forget to set it, don't lock yourself out during dev.
        return
    if x_api_key != INGEST_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")