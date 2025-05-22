import os
import os.path
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import tempfile
import zipfile
import gzip
import io
import logging

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']

def get_credentials_file_from_env():
    if os.path.exists("credentials.json"):
        return "credentials.json"
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON environment variable not set and credentials.json not found")
    with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.json') as tmp:
        tmp.write(creds_json)
        return tmp.name

def authenticate_gmail():
    """
    Authenticates and returns an authorized Gmail API service object.
    
    Checks for existing OAuth2 credentials in 'token.json', refreshes them if expired, or initiates a new authentication flow if necessary. Saves updated credentials for future use.
    Logs and raises clear errors if authentication fails or credentials file is not found.
    If 'token.json' does not exist, checks for GOOGLE_AUTH_TOKEN environment variable and uses its contents.
    """
    creds = None
    logger = logging.getLogger("gmail_auth")
    try:
        token_path = 'token.json'
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        else:
            google_auth_token = os.environ.get('GOOGLE_AUTH_TOKEN')
            if google_auth_token:
                with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.json') as tmp_token:
                    tmp_token.write(google_auth_token)
                    tmp_token_path = tmp_token.name
                creds = Credentials.from_authorized_user_file(tmp_token_path, SCOPES)
            else:
                logger.error("GOOGLE_AUTH_TOKEN environment variable not set and token.json not found")
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Failed to refresh credentials: {e}")
                    raise RuntimeError(f"Failed to refresh credentials: {e}")
            else:
                logger.info("Looking for credentials file in environment variable")
                try:
                    credentials_path = get_credentials_file_from_env()
                except Exception as e:
                    logger.error(f"Credentials file not found or invalid: {e}")
                    raise FileNotFoundError(f"Credentials file not found or invalid: {e}")
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Failed to authenticate with Gmail: {e}")
                    raise RuntimeError(f"Failed to authenticate with Gmail: {e}")
            try:
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.error(f"Failed to save token.json: {e}")
                raise IOError(f"Failed to save token.json: {e}")
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
        print(f'Error marking message {message_id} as read: {error}')

def get_unread_dmarc_emails(service, labelIds=None):
    """
    Retrieves unread emails with attachments from specified Gmail labels, handling pagination.

    Fetches metadata for each matching email, including sender, subject, and date.
    Returns a list of dictionaries containing message ID, thread ID, and header details.
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
        f"  From: {email_data['from']}\n"
        f"  Subject: {email_data['subject']}\n"
        f"  Date: {email_data['date']}"
    )

def get_dmarc_attachment_content(service, message_id):
    """
    Extracts DMARC report XML contents from email attachments.
    
    Retrieves and processes attachments with .xml, .zip, or .gz extensions from the specified email. Returns a list of XML content bytes extracted from all valid attachments, or None if no valid DMARC reports are found.
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
                
        except (zipfile.BadZipFile, gzip.BadGzipFile) as err:
            logging.getLogger("gmail_attachment").warning(
                "Failed to extract DMARC attachment %s from %s: %s",
                filename,
                message_id,
                err,
            )
            continue
            
    return xml_contents if xml_contents else None


def main():
    """
    Authenticates with Gmail, retrieves unread emails with attachments, and extracts DMARC reports.
    
    Fetches unread emails containing attachments, displays their metadata, and attempts to extract DMARC report contents from their attachments. Prints the results and handles errors during execution.
    """
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