import os
import zipfile
import io
import hashlib
import defusedxml.ElementTree as ET
from datetime import datetime, timezone
from agentuity import AgentRequest, AgentResponse, AgentContext
from agentuity.io.email import Email
from openai import AsyncOpenAI, RateLimitError, APIError, APITimeoutError
from resources.templates import templates
from config import config

from utils.slack import send_message
from utils.retry import async_retry
from utils.validators import validate_attachment_size, validate_xml_structure, ValidationError
import gzip

client = AsyncOpenAI()

async def run(request: AgentRequest, response: AgentResponse, context: AgentContext):
    """
    Entry point for processing DMARC reports and returning an analysis summary.
    """
    try:
        # Check for emails from request data
        email = await request.data.email()
        if email:
            context.logger.info('Processing email: %s', email.subject)
            analysis, slack_delivered = await generate_dmarc_report_from_email(email, context)
            return response.json({
                "summary": analysis,
                "slack_delivered": slack_delivered
            })
        else:
            return response.text("No email found")
    except Exception as e:
        context.logger.error("Error processing email: %s", str(e))
        return response.text(f"Failed to process email: {str(e)}")

async def generate_dmarc_report_from_email(email: Email, context: AgentContext):
    """
    Processes an email and returns a summary of the DMARC report.
    """
    context.logger.info(f"Processing email with {len(email.attachments)} attachments")
    context.logger.info(f"Email from: {email.from_email}, Subject: {email.subject}")

    dmarc_contents = []
    
    # Extract DMARC XML content from attachments
    for attachment in email.attachments:
        context.logger.info(f"Processing attachment: {attachment.filename}")
        
        # Skip non-DMARC related attachments
        if not (attachment.filename.endswith('.xml') or 
                attachment.filename.endswith('.xml.gz') or 
                attachment.filename.endswith('.zip') or
                'dmarc' in attachment.filename.lower()):
            context.logger.info(f"Skipping non-DMARC attachment: {attachment.filename}")
            continue
            
        try:
            context.logger.info(f"Attempting to read attachment data for: {attachment.filename}")
            data = await attachment.data()
            content = await data.binary()

            # Validate attachment size
            try:
                validate_attachment_size(len(content), attachment.filename)
            except ValidationError as e:
                context.logger.warning(f"Skipping attachment due to validation error: {e}")
                continue

            # Handle different attachment formats (XML, gzipped XML, zip files)
            if attachment.filename.endswith('.xml'):
                xml_content = content.decode('utf-8')

                # Validate XML structure
                try:
                    validate_xml_structure(xml_content)
                except ValidationError as e:
                    context.logger.warning(f"Skipping '{attachment.filename}': {e}")
                    continue

                dmarc_contents.append(xml_content)
                context.logger.info(f"Processed XML attachment: {attachment.filename}")

            elif attachment.filename.endswith('.xml.gz'):
                xml_content = gzip.decompress(content).decode('utf-8')

                # Validate XML structure
                try:
                    validate_xml_structure(xml_content)
                except ValidationError as e:
                    context.logger.warning(f"Skipping '{attachment.filename}': {e}")
                    continue

                dmarc_contents.append(xml_content)
                context.logger.info(f"Processed gzipped XML attachment: {attachment.filename}")

            elif attachment.filename.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(content), 'r') as zip_file:
                    for file_name in zip_file.namelist():
                        if file_name.endswith('.xml'):
                            xml_content = zip_file.read(file_name).decode('utf-8')

                            # Validate XML structure
                            try:
                                validate_xml_structure(xml_content)
                            except ValidationError as e:
                                context.logger.warning(f"Skipping '{file_name}' from zip: {e}")
                                continue

                            dmarc_contents.append(xml_content)
                            context.logger.info(f"Extracted XML file '{file_name}' from zip: {attachment.filename}")

        except ValidationError as e:
            context.logger.warning(f"Validation failed for '{attachment.filename}': {e}")
            continue
        except Exception as e:
            error_message = str(e)
            context.logger.error(f"Error processing attachment '{attachment.filename}': {error_message}")
            continue
    
    if not dmarc_contents:
        context.logger.warning("No DMARC XML content found in email attachments")
        return "❌ No DMARC reports found in email attachments", False
    
    # Analyze DMARC reports
    context.logger.info(f"Found {len(dmarc_contents)} DMARC reports to analyze")
    all_analyses = []
    
    for xml_content in dmarc_contents:
        try:
            analysis = await analyze_dmarc_report(xml_content)
            all_analyses.append(analysis)
        except Exception as e:
            context.logger.error(f"Error analyzing DMARC report: {e}", stack_info=True)
            continue
    
    if not all_analyses:
        return "❌ Unable to analyze DMARC reports - analysis failed", False
    
    # Generate summary
    email_metadata = {
        "subject": email.subject, 
        "from": email.from_email, 
        "date": email.date.isoformat() if hasattr(email.date, 'isoformat') else str(email.date)
    }
    summary = await summarize_analysis(all_analyses, email_metadata)
    
    # Store analysis results in key-value store
    try:
        await store_dmarc_analysis(context, email_metadata, dmarc_contents, all_analyses, summary)
        context.logger.info("Successfully stored DMARC analysis results in key-value store")
    except Exception as e:
        context.logger.error(f"Failed to store analysis in key-value store: {e}")
    
    # Send to Slack if configured
    slack_success = False
    try:
        slack_to_dmarc_channel(summary)
        slack_success = True
        context.logger.info("Successfully sent DMARC analysis to Slack")
    except Exception as e:
        context.logger.error(f"Failed to send to Slack: {e}")

    return summary, slack_success

async def store_dmarc_analysis(context: AgentContext, email_metadata: dict, dmarc_contents: list, analyses: list, summary: str):
    """
    Stores DMARC analysis results in the key-value store.

    Args:
        context: The agent context providing access to storage
        email_metadata: Metadata about the email (subject, from, date)
        dmarc_contents: List of DMARC XML content strings
        analyses: List of individual analysis results
        summary: The final summarized analysis
    """
    # Extract report metadata from first DMARC XML for storage key
    report_metadata = None
    if dmarc_contents:
        for xml_content in dmarc_contents:
            report_metadata = extract_report_metadata(xml_content)
            if report_metadata and report_metadata.get('report_id'):
                # Found valid metadata, use it
                context.logger.info(f"Using report_id for storage key: {report_metadata.get('report_id')}")
                break

    # Generate storage key using report metadata (or fallback to timestamp)
    storage_key = generate_storage_key(report_metadata, email_metadata)
    
    # Prepare data to store
    storage_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "email_metadata": email_metadata,
        "individual_analyses": analyses,
        "summary": summary,
        "report_count": len(analyses)
    }
    
    # Store in key-value storage
    await context.kv.set(config.KV_STORE_NAME, storage_key, storage_data)

def extract_report_metadata(xml_content: str) -> dict:
    """
    Extracts key metadata from DMARC XML report for storage key generation.

    Args:
        xml_content: The DMARC XML report content as a string.

    Returns:
        Dictionary with report_id, org_name, domain, and date_begin, or None if parsing fails.
    """
    try:
        root = ET.fromstring(xml_content)
        metadata = root.find('report_metadata')
        policy = root.find('policy_published')

        if metadata is None:
            return None

        result = {}

        # Extract report ID (most important for uniqueness)
        report_id_elem = metadata.find('report_id')
        result['report_id'] = report_id_elem.text if report_id_elem is not None else None

        # Extract organization name
        org_name_elem = metadata.find('org_name')
        result['org_name'] = org_name_elem.text if org_name_elem is not None else None

        # Extract domain from policy
        if policy is not None:
            domain_elem = policy.find('domain')
            result['domain'] = domain_elem.text if domain_elem is not None else None
        else:
            result['domain'] = None

        # Extract date range start
        date_range = metadata.find('date_range')
        if date_range is not None:
            begin_elem = date_range.find('begin')
            result['date_begin'] = begin_elem.text if begin_elem is not None else None
        else:
            result['date_begin'] = None

        return result
    except Exception as e:
        # XML parsing failed, return None
        return None

def generate_storage_key(report_metadata: dict = None, email_metadata: dict = None) -> str:
    """
    Generates a unique storage key for DMARC analysis, preferring report_id from XML.
    Fallback uses timestamp + hash of email metadata for uniqueness.

    Args:
        report_metadata: Metadata extracted from DMARC XML (report_id, org_name, domain).
        email_metadata: Email metadata as fallback (subject, from, date).

    Returns:
        Unique storage key string.
    """
    # Ideal: use report_id from DMARC XML (guaranteed unique per sender)
    if report_metadata and report_metadata.get('report_id'):
        report_id = report_metadata['report_id']
        domain = report_metadata.get('domain', 'unknown')
        org = report_metadata.get('org_name', 'unknown')
        # Sanitize org name for use in key
        org_sanitized = org.replace('.', '_').replace('/', '_').replace(' ', '_')
        return f"{domain}_{org_sanitized}_{report_id}"

    # Fallback: timestamp + email hash for uniqueness
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
    if email_metadata:
        email_hash = hashlib.md5(
            f"{email_metadata.get('subject', '')}{email_metadata.get('from', '')}".encode()
        ).hexdigest()[:8]
        return f"dmarc_{timestamp}_{email_hash}"
    return f"dmarc_{timestamp}"

def slack_to_dmarc_channel(analysis):
    """
    Sends a DMARC analysis message to the configured Slack channel.

    Args:
        analysis: The analysis text to be posted to Slack.
    """
    if not config.DMARC_CHANNEL_ID:
        raise RuntimeError("DMARC_CHANNEL_ID is not configured")
    send_message(config.DMARC_CHANNEL_ID, analysis)
    
@async_retry(
    max_attempts=config.OPENAI_MAX_RETRIES,
    exceptions=(RateLimitError, APIError, APITimeoutError)
)
async def analyze_dmarc_report(dmarc_report):
    """
    Analyzes a single DMARC report using an OpenAI GPT model.
    Includes automatic retry logic for rate limits, API errors, and timeouts.

    Args:
        dmarc_report: The DMARC XML report content to be analyzed.

    Returns:
        A string containing the GPT-generated analysis of the DMARC report.
    """
    template = templates["analyze-dmarc"]
    compiled_prompt = template.substitute(xml=dmarc_report)
    response = await client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[{"role": "user", "content": compiled_prompt}],
        timeout=config.OPENAI_TIMEOUT
    )
    return response.choices[0].message.content

@async_retry(
    max_attempts=config.OPENAI_MAX_RETRIES,
    exceptions=(RateLimitError, APIError, APITimeoutError)
)
async def summarize_analysis(results, email):
    """
    Generates a concise summary of multiple DMARC analysis results using OpenAI GPT.
    Includes automatic retry logic for rate limits, API errors, and timeouts.

    Args:
        results: A list of individual DMARC analysis strings.
        email: Metadata or identifying information for the email being summarized.

    Returns:
        A single summarized report string generated by the GPT model.
    """
    if not results:
        summary = "❌ Unable to analyse DMARC report(s) – parsing failed."
        return summary
    template = templates["summarize-analysis"]
    compiled_prompt = template.substitute(analysis=results, email=email)
    response = await client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {"role": "user", "content": compiled_prompt}
        ],
        timeout=config.OPENAI_TIMEOUT
    )
    return response.choices[0].message.content
