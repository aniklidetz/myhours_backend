# myhours/logging_filters.py
import logging
import re
from typing import Any, Mapping

REDACTION = "****"
SENSITIVE_KEYS = {
    "password", "pass", "pwd",
    "token", "access", "refresh", "authorization",
    "email", "phone", "ssn", "id_number",
}

_email_re = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_token_like_re = re.compile(r"(?:Bearer\s+)?[A-Za-z0-9\-_]{20,}")

def _redact_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    s = str(value)
    s = _email_re.sub(r"***@\2", s)
    s = _token_like_re.sub(REDACTION, s)
    return s

def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            k: (REDACTION if isinstance(k, str) and k.lower() in SENSITIVE_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return type(value)(_redact(v) for v in value)
    return _redact_scalar(value)

class PIIRedactorFilter(logging.Filter):
    """Redact common PII in log records (msg/args)."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # redact format string itself (rarely contains PII, but safe)
            record.msg = _redact(record.msg)

            args = getattr(record, "args", None)
            if args:
                if isinstance(args, Mapping):
                    record.args = _redact(args)  # dict of named args
                elif isinstance(args, (tuple, list)):
                    # typical case for logger.info("..%s..%s", a, b)
                    record.args = tuple(_redact(a) for a in args)
                else:
                    # any other scalar/container
                    record.args = _redact(args)
        except Exception:
            # never break logging
            pass
        return True