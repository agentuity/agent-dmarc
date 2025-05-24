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

def get_google_creds():
    """
    Returns credentials info as a dict, from the GOOGLE_CREDENTIALS_JSON env var (if set),
    or from a local credentials.json file (if present). Raises an error if neither is available.
    """
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        return json.loads(creds_json)
    elif os.path.exists("credentials.json"):
        with open("credentials.json", "r") as f:
            return json.load(f)
    else:
        raise ValueError("GOOGLE_CREDENTIALS_JSON environment variable not set and credentials.json not found")

def is_production() -> bool:
    """Returns True if running in production environment."""
    return os.environ.get("ENVIRONMENT", "development").lower() == "production"

def parse_google_auth_token(token: str, logger: logging.Logger) -> dict:
    """
    Decodes a base64-encoded JSON string from the environment variable.
    Falls back to raw JSON if not base64.
    """
    try:
        decoded = base64.b64decode(token).decode('utf-8')
        return json.loads(decoded)
    except Exception as base64_err:
        try:
            return json.loads(token)
        except Exception as json_err:
            logger.error("Failed to decode GOOGLE_AUTH_TOKEN as base64 (%s) or JSON (%s)", base64_err, json_err)
            raise ValueError("GOOGLE_AUTH_TOKEN is neither valid base64 nor valid JSON")

def authenticate_gmail() -> object:
    """
    Authenticates and returns an authorized Gmail API service object.
    In production, only GOOGLE_AUTH_TOKEN is allowed (no OAuth flow).
    In non-production, fallback to OAuth flow if needed.
    """
    logger = logging.getLogger("gmail_auth")
    logger.info("Starting Gmail authentication. Environment: %s", os.environ.get("ENVIRONMENT", "development"))
    google_auth_token = os.environ.get('GOOGLE_AUTH_TOKEN')
    creds = None

    if google_auth_token:
        token_data = parse_google_auth_token(google_auth_token, logger)
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    elif is_production():
        raise RuntimeError("In production, GOOGLE_AUTH_TOKEN environment variable must be set and valid. OAuth flow is not allowed.")
    else:
        logger.info("Looking for credentials info in environment variable (non-production)")
        credentials_info = get_google_creds()
        flow = InstalledAppFlow.from_client_config(credentials_info, SCOPES)
        creds = flow.run_local_server(port=0)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif is_production():
            raise RuntimeError("In production, could not obtain valid credentials from GOOGLE_AUTH_TOKEN. OAuth flow is not allowed.")
        else:
            logger.info("Re-running OAuth flow for new credentials (non-production)")
            credentials_info = get_google_creds()
            flow = InstalledAppFlow.from_client_config(credentials_info, SCOPES)
            creds = flow.run_local_server(port=0)

    return build('gmail', 'v1', credentials=creds)

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
