import os
import requests

SF_HOST = os.getenv("SNOWFLAKE_HOST")
SF_PAT = os.getenv("SNOWFLAKE_PAT")
SF_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
SF_DATABASE = os.getenv("SNOWFLAKE_DATABASE", "CLEANING")
SF_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")
SF_ROLE = os.getenv("SNOWFLAKE_ROLE", "")

def snowflake_sql(statement: str, timeout: int = 20) -> dict:
    if not (SF_HOST and SF_PAT):
        raise RuntimeError("Snowflake env vars missing (SNOWFLAKE_HOST, SNOWFLAKE_PAT)")

    url = f"https://{SF_HOST}/api/v2/statements"
    headers = {
        "Authorization": f"Bearer {SF_PAT}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "statement": statement,
        "timeout": timeout,
        "warehouse": SF_WAREHOUSE,
        "database": SF_DATABASE,
        "schema": SF_SCHEMA,
    }
    if SF_ROLE:
        body["role"] = SF_ROLE

    r = requests.post(url, json=body, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()