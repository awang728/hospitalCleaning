import requests

def low_performance_rooms():
    query = """
    SELECT room_id, AVG(coverage_percent)
    FROM cleaning_sessions
    GROUP BY room_id
    HAVING AVG(coverage_percent) < 85;
    """

    # Send query to Snowflake REST endpoint
    # (Use Snowflake trial credentials)
    return {"query": query}
