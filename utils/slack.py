from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import config
import logging
import time

_client = None

def get_slack_client() -> WebClient:
    """
    Lazy-load Slack client to avoid import-time failures.

    Returns:
        WebClient: Configured Slack WebClient instance

    Raises:
        ValueError: If SLACK_BOT_TOKEN is not configured
    """
    global _client
    if _client is None:
        if not config.SLACK_BOT_TOKEN:
            raise ValueError("SLACK_BOT_TOKEN not configured")
        _client = WebClient(token=config.SLACK_BOT_TOKEN)
    return _client

def send_message(channel_id: str, message_text: str):
    """
    Sends a message to a specified Slack channel with retry logic.
    Implements exponential backoff for retryable errors (rate_limited, timeout).

    Args:
        channel_id: The ID of the Slack channel to send the message to.
        message_text: The text content of the message to send.

    Raises:
        SlackApiError: If all retry attempts fail or error is non-retryable
        ValueError: If SLACK_BOT_TOKEN is not configured
    """
    logger = logging.getLogger("slack")
    client = get_slack_client()

    for attempt in range(config.SLACK_MAX_RETRIES):
        try:
            response = client.chat_postMessage(channel=channel_id, text=message_text)
            logger.info(f"Message sent to {channel_id}")
            return response
        except SlackApiError as e:
            error_type = e.response.get('error', 'unknown_error')

            # Check if this is the last attempt
            if attempt == config.SLACK_MAX_RETRIES - 1:
                logger.error(f"Failed after {config.SLACK_MAX_RETRIES} attempts: {error_type}")
                raise

            # Check if error is retryable
            if error_type in ['rate_limited', 'timeout', 'service_unavailable']:
                delay = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(f"Attempt {attempt + 1} failed: {error_type}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                # Non-retryable error, fail immediately
                logger.error(f"Non-retryable Slack error: {error_type}")
                raise
