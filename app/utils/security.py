"""Security utilities for webhook verification."""

import hashlib
import hmac
import time

from structlog import get_logger

logger = get_logger()


def verify_ashby_signature(
    secret: str,
    body: bytes,
    provided_signature: str,
) -> bool:
    """
    Verify Ashby webhook signature using HMAC-SHA256.

    Uses constant-time comparison to prevent timing attacks.

    Ashby signature format: "sha256=<hex_digest>"

    Args:
        secret: Webhook secret from environment
        body: Raw request body
        provided_signature: Ashby-Signature header (format: "sha256=...")

    Returns:
        True if signature valid, False otherwise
    """
    # Compute expected signature
    h = hmac.new(secret.encode(), body, hashlib.sha256)
    expected_digest = h.hexdigest()
    expected_signature = f"sha256={expected_digest}"

    # Constant-time comparison (security critical!)
    is_valid = hmac.compare_digest(expected_signature, provided_signature)

    if not is_valid:
        logger.warning(
            "webhook_signature_invalid",
            expected_prefix=expected_signature[:15],
            provided_prefix=provided_signature[:15] if provided_signature else None,
        )

    return is_valid


def verify_slack_signature(
    secret: str,
    body: str,
    timestamp: str,
    provided_signature: str,
) -> bool:
    """
    Verify Slack request signature using HMAC-SHA256.

    Uses constant-time comparison to prevent timing attacks.
    Also validates timestamp is within 5 minutes to prevent replay attacks.

    Slack signature format: "v0=<hex_digest>"
    Basestring: "v0:{timestamp}:{body}"

    Args:
        secret: Slack signing secret from environment
        body: Raw request body as string
        timestamp: X-Slack-Request-Timestamp header
        provided_signature: X-Slack-Signature header (format: "v0=...")

    Returns:
        True if signature valid and timestamp fresh, False otherwise
    """
    # Validate timestamp (prevent replay attacks)
    try:
        request_timestamp = int(timestamp)
    except (ValueError, TypeError):
        logger.warning("slack_signature_invalid_timestamp", timestamp=timestamp)
        return False

    current_timestamp = int(time.time())
    time_diff = abs(current_timestamp - request_timestamp)

    # Reject requests older than 5 minutes (Slack's recommended threshold)
    if time_diff > 300:
        logger.warning(
            "slack_signature_timestamp_too_old",
            time_diff=time_diff,
            max_allowed=300,
        )
        return False

    # Compute expected signature
    sig_basestring = f"v0:{timestamp}:{body}"
    h = hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256)
    expected_signature = f"v0={h.hexdigest()}"

    # Constant-time comparison (security critical!)
    is_valid = hmac.compare_digest(expected_signature, provided_signature)

    if not is_valid:
        logger.warning(
            "slack_signature_invalid",
            expected_prefix=expected_signature[:15],
            provided_prefix=provided_signature[:15] if provided_signature else None,
        )

    return is_valid
