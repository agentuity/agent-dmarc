import base64
import binascii
import gzip
import io
import json
import logging
import os
import os.path
import zipfile

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']

def get_credentials_info_from_env():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON environment variable not set and credentials.json not found")
    return json.loads(creds_json)

def authenticate_gmail():
    """
    Authenticates and returns an authorized Gmail API service object.
    In production, only GOOGLE_AUTH_TOKEN is allowed (no OAuth flow).
    In non-production, fallback to OAuth flow if needed.
    """
    creds = None
    logger = logging.getLogger("gmail_auth")
    env = os.environ.get("environment", "development")
    try:
        google_auth_token = os.environ.get('GOOGLE_AUTH_TOKEN')
        if google_auth_token:
            try:
                decoded = base64.b64decode(google_auth_token).decode('utf-8')
                token_data = json.loads(decoded)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            except Exception as e:
                logger.error("Failed to decode or parse GOOGLE_AUTH_TOKEN: %s", e)
                raise
        else:
            if env == "production":
                raise RuntimeError("In production, GOOGLE_AUTH_TOKEN environment variable must be set and valid. OAuth flow is not allowed.")
            logger.info("Looking for credentials info in environment variable (non-production)")
            credentials_info = get_credentials_info_from_env()
            flow = InstalledAppFlow.from_client_config(credentials_info, SCOPES)
            creds = flow.run_local_server(port=0)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if env == "production":
                    raise RuntimeError("In production, could not obtain valid credentials from GOOGLE_AUTH_TOKEN. OAuth flow is not allowed.")
                logger.info("Re-running OAuth flow for new credentials (non-production)")
                credentials_info = get_credentials_info_from_env()
                flow = InstalledAppFlow.from_client_config(credentials_info, SCOPES)
                creds = flow.run_local_server(port=0)
        return build('gmail', 'v1', credentials=creds)
    except Exception as error:
        logger.error(f"Gmail authentication failed: {error}", exc_info=True, stack_info=True)
        raise

def mark_as_read(service, message_id):
    """
    Marks a Gmail message as read by removing the 'UNREAD' label.
    
    Args:
        message_id: The unique identifier of the Gmail message to update.
    """
    try:
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
    except Exception as error:
        logging.getLogger("gmail_mark_as_read").error(f'Error marking message {message_id} as read: {error}', exc_info=True)

def get_unread_dmarc_emails(service, labelIds=None):
    """
    Retrieves unread emails with attachments from specified Gmail labels, handling pagination.
    """
    if labelIds is None:
        labelIds = ['INBOX']
    all_messages = []
    request = service.users().messages().list(userId='me', labelIds=labelIds, q="has:attachment is:unread")
    while request is not None:
        results = request.execute()
        messages = results.get('messages', [])
        all_messages.extend(messages)
        request = service.users().messages().list_next(request, results)

    if not all_messages:
        return []

    detailed_messages = []
    for message in all_messages:
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
    return detailed_messages

def format_email_info(email_data):
    """
    Returns a formatted string displaying email metadata for logging or notifications.
    
    Args:
        email_data (dict): Dictionary with keys 'id', 'from', 'subject', and 'date'.
    
    Returns:
        str: Multi-line string summarizing the email's ID, sender, subject, and date.
    """
    return (
        f"📧 Email Details:\n"
        f"  ID: {email_data['id']}\n"
        f"  Subject: {email_data['subject']}\n"
        f"  Date: {email_data['date']}"
    )

def get_dmarc_attachment_content(service, message_id):
    """
    Extracts DMARC report XML contents from email attachments.
    """
    msg = service.users().messages().get(userId='me', id=message_id).execute()
    payload = msg.get('payload', {})
    def iter_parts(part):
        if 'parts' in part:
            for p in part['parts']:
                yield from iter_parts(p)
        else:
            yield part

    parts = list(iter_parts(payload))
    
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
            
        try:
            file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
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
                
        except (UnicodeEncodeError, binascii.Error, zipfile.BadZipFile, gzip.BadGzipFile) as err:
            logging.getLogger("gmail_attachment").warning(
                "Failed to extract DMARC attachment %s from %s: %s",
                filename,
                message_id,
                err,
            )
            continue
            
    return xml_contents if xml_contents else None


def main():
    try:
        service = authenticate_gmail()
        messages = get_unread_dmarc_emails(service)
        if not messages:
            print('No unread emails with attachments found.')
            return
        
        print(f"Found {len(messages)} unread emails with attachments:")
        for email in messages:
            print("\n" + format_email_info(email))
            content = get_dmarc_attachment_content(service, email['id'])
            if content:
                print(f"✅ Contains DMARC report: {len(content)} attachment(s) found")
            else:
                print("❌ No DMARC report found in attachments")
    except Exception as error:
        print(f'An error occurred: {error}')

if __name__ == "__main__":
    main()