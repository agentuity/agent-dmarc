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

def mark_as_read(service, message_id):
    """Mark a message as read by removing the UNREAD label."""
    try:
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
    except Exception as error:
        print(f'Error marking message {message_id} as read: {error}')

def fetch_unread_emails(service, labelIds=['INBOX', 'UNREAD']):
    results = service.users().messages().list(userId='me', labelIds=labelIds, q="has:attachment is:unread").execute()
    messages = results.get('messages', [])
    
    if not messages:
        return []
    
    detailed_messages = []
    for message in messages:
        msg = service.users().messages().get(userId='me', id=message['id'], format='metadata', 
                                            metadataHeaders=['From', 'Subject', 'Date']).execute()
        headers = msg['payload']['headers']
        email_data = {
            'id': message['id'],
            'threadId': message['threadId'],
            'subject': next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject'),
            'from': next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender'),
            'date': next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown Date')
        }
        detailed_messages.append(email_data)
    
    print(detailed_messages)
    return detailed_messages

def get_dmarc_attachment_content(service, message_id):
    """
    Retrieve DMARC report content from email attachments.
    Returns a list of XML contents from all valid attachments found.
    Handles .xml, .zip, and .gz files containing DMARC reports.
    """
    msg = service.users().messages().get(userId='me', id=message_id).execute()
    payload = msg.get('payload', {})
    parts = payload.get('parts', [])
    
    xml_contents = []
    
    for part in parts: 
        filename = part.get('filename', '')
        body = part.get('body', {})
        
        if not (filename.endswith('.xml') or filename.endswith('.zip') or filename.endswith('.gz')):
            continue
            
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
            
        file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
        
        try:
            if filename.endswith('.xml'):
                xml_contents.append(file_data)
                
            elif filename.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(file_data)) as zip_file:
                    xml_files = [f for f in zip_file.namelist() if f.endswith('.xml')]
                    for xml_file in xml_files:
                        xml_content = zip_file.read(xml_file)
                        xml_contents.append(xml_content)
                        
            elif filename.endswith('.gz'):
                xml_content = gzip.decompress(file_data)
                xml_contents.append(xml_content)
                
        except (zipfile.BadZipFile, gzip.BadGzipFile) as e:
            continue
            
    return xml_contents if xml_contents else None


def main():
    try:
        service = authenticate_gmail()
        messages = fetch_unread_emails(service)
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