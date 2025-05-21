from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os
import logging

client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

def send_message(channel_id, message_text):
    """
    Sends a message to a specified Slack channel using the Slack Web API.
    
    Args:
    	channel_id: The ID of the Slack channel to send the message to.
    	message_text: The text content of the message to send.
    """
    try:
        response = client.chat_postMessage(
            channel=channel_id,
            text=message_text
        )
        logging.info(f"✅ Message sent to {channel_id}: {response['ts']}")
    except SlackApiError as e:
        logging.error(f"❌ Error sending message: {e.response['error']}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    send_message("C08T4A9S3BK", "👋 Hello from DMARC Agent!")
