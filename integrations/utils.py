import json


def safe_to_json(payload):
    """
    Safe JSON parser that handles bytes, strings, dicts, and response objects.
    Prevents encoding/decoding errors in API responses.
    """
    # dict – return as is
    if isinstance(payload, dict):
        return payload

    # bytes – decode safely
    if isinstance(payload, (bytes, bytearray)):
        try:
            return json.loads(payload.decode("utf-8"))
        except UnicodeDecodeError:
            # Handle broken bytes with error ignore
            return json.loads(payload.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError:
            # If can't parse as JSON, return empty dict
            return {}

    # str – parse normally
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            # If string is not JSON, return empty dict
            return {}

    # response object – use json() method if available
    if hasattr(payload, "json") and callable(getattr(payload, "json")):
        try:
            return payload.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Fallback to content parsing
            return safe_to_json(getattr(payload, "content", "{}"))

    # response with content attribute
    if hasattr(payload, "content"):
        return safe_to_json(payload.content)

    # response with text attribute
    if hasattr(payload, "text"):
        return safe_to_json(payload.text)

    # final fallback
    try:
        return json.loads(str(payload))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
