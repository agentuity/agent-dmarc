import os
import os.path
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']
ATTACHMENT_DIR = '/tmp/email_attachments/'

def authenticate_gmail():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def fetch_emails(service):
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], q="has:attachment").execute()
    messages = results.get('messages', [])
    return messages

def save_attachments(service, message_id):
    msg = service.users().messages().get(userId='me', id=message_id).execute()
    payload = msg.get('payload', {})
    parts = payload.get('parts', [])
    if not os.path.exists(ATTACHMENT_DIR):
        os.makedirs(ATTACHMENT_DIR)
    for part in parts:
        filename = part.get('filename')
        body = part.get('body', {})
        data = body.get('data')
        attachment_id = body.get('attachmentId')
        if filename:
            if attachment_id:
                attachment = service.users().messages().attachments().get(
                    userId='me', messageId=message_id, id=attachment_id
                ).execute()
                data = attachment.get('data')
            if data:
                file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
                file_path = os.path.join(ATTACHMENT_DIR, filename)
                with open(file_path, 'wb') as f:
                    f.write(file_data)
                print(f"Saved attachment: {file_path}")

def main():
    try:
        service = authenticate_gmail()
        messages = fetch_emails(service)
        if not messages:
            print('No messages with attachments found.')
            return
        for message in messages:
            save_attachments(service, message['id'])
    except Exception as error:
        print(f'An error occurred: {error}')

if __name__ == "__main__":
    main()