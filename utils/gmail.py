import os
import os.path
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import zipfile
import gzip
import io

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']

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

def fetch_emails(service, labelIds=['INBOX']):
    results = service.users().messages().list(userId='me', labelIds=labelIds, q="has:attachment").execute()
    messages = results.get('messages', [])
    return messages

def get_dmarc_attachment_content(service, message_id):
    msg = service.users().messages().get(userId='me', id=message_id).execute()
    payload = msg.get('payload', {})
    parts = payload.get('parts', [])
    
    for part in parts: 
        filename = part.get('filename', '')
        body = part.get('body', {})
        
        # Check if it's a DMARC report (zip or gzip)
        if not (filename.endswith('.zip') or filename.endswith('.gz')):
            continue
            
        # Get attachment data
        attachment_id = body.get('attachmentId')
        if attachment_id:
            attachment = service.users().messages().attachments().get(
                userId='me', messageId=message_id, id=attachment_id
            ).execute()
            data = attachment.get('data')
        else:
            data = body.get('data')
            
        if not data:
            continue
            
        # Decode base64 data
        file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
        
        # Handle based on file type
        try:
            if filename.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(file_data)) as zip_file:
                    # Get the first XML file in the zip
                    xml_files = [f for f in zip_file.namelist() if f.endswith('.xml')]
                    if xml_files:
                        return zip_file.read(xml_files[0])
                        
            elif filename.endswith('.gz'):
                return gzip.decompress(file_data)
                
        except (zipfile.BadZipFile, gzip.BadGzipFile) as e:
            continue  # Skip corrupted archives
            
    return None


def main():
    try:
        service = authenticate_gmail()
        messages = fetch_emails(service)
        if not messages:
            print('No messages with attachments found.')
            return
        for message in messages:
            content = get_dmarc_attachment_content(service, message['id'])
            print(content)
    except Exception as error:
        print(f'An error occurred: {error}')

if __name__ == "__main__":
    main()