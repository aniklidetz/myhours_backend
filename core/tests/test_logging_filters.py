# core/tests/test_logging_filters.py
import logging
from io import StringIO

from myhours.logging_filters import PIIRedactorFilter


def test_email_and_token_are_redacted_stream():
    # Arrange: isolated logger + in-memory stream handler with our filter
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    handler.addFilter(PIIRedactorFilter())
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger("test.pii")
    logger.setLevel(logging.INFO)
    logger.handlers = []  # isolate from global handlers
    logger.propagate = False  # don't bubble to root
    logger.addHandler(handler)

    # Act
    logger.info(
        "email=%s token=%s", "john.doe@example.com", "Bearer eyJhbGciOiVeryLongToken..."
    )

    # Assert
    value = stream.getvalue()
    assert "***@example.com" in value
    assert "****" in value
    assert "john.doe@example.com" not in value
