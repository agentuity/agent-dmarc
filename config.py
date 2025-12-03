import os
from typing import Optional

class Config:
    """Centralized configuration for DMARC agent"""

    # OpenAI Configuration
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1")
    OPENAI_MAX_RETRIES: int = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
    OPENAI_TIMEOUT: int = int(os.getenv("OPENAI_TIMEOUT", "60"))

    # Slack Configuration
    SLACK_BOT_TOKEN: Optional[str] = os.getenv("SLACK_BOT_TOKEN")
    DMARC_CHANNEL_ID: Optional[str] = os.getenv("DMARC_CHANNEL_ID")
    SLACK_MAX_RETRIES: int = int(os.getenv("SLACK_MAX_RETRIES", "3"))

    # Processing Limits
    MAX_ATTACHMENT_SIZE_MB: int = int(os.getenv("MAX_ATTACHMENT_SIZE_MB", "25"))
    MAX_ATTACHMENTS_PER_EMAIL: int = int(os.getenv("MAX_ATTACHMENTS_PER_EMAIL", "10"))

    # Storage
    KV_STORE_NAME: str = "dmarc-reports"

    @classmethod
    def validate(cls) -> list[str]:
        """Validates required configuration and returns list of errors"""
        errors = []
        if not cls.SLACK_BOT_TOKEN:
            errors.append("SLACK_BOT_TOKEN environment variable is required")
        if not cls.DMARC_CHANNEL_ID:
            errors.append("DMARC_CHANNEL_ID environment variable is required")
        return errors

config = Config()
