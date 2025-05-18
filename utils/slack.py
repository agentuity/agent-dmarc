from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import os

client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

def send_message(channel_id, message_text):
    try:
        response = client.chat_postMessage(
            channel=channel_id,
            text=message_text
        )
        print(f"✅ Message sent to {channel_id}: {response['ts']}")
    except SlackApiError as e:
        print(f"❌ Error sending message: {e.response['error']}")

if __name__ == "__main__":
    send_message("C08T4A9S3BK", "👋 Hello from DMARC Agent!")
