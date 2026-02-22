import json
from .snowflake_client import snowflake_sql

def push_summary(summary: dict, room_id: str, surface_type: str):
    flags_json = json.dumps(summary.get("flags", []))

    stmt = f"""
    INSERT INTO CLEANING.PUBLIC.SESSION_SUMMARIES
    (SESSION_ID, ROOM_ID, SURFACE_TYPE, QUALITY_SCORE, COVERAGE_PERCENT, OVERWIPE_RATIO, UNIFORMITY_STD, FLAGS)
    VALUES
    ('{summary["session_id"]}', '{room_id}', '{surface_type}',
     {float(summary.get("quality_score", 0))},
     {float(summary.get("coverage_percent", 0))},
     {float(summary.get("overwipe_ratio", 0))},
     {float(summary.get("uniformity_std", 0))},
     PARSE_JSON('{flags_json}')
    );
    """
    return snowflake_sql(stmt)