import os
from agentuity import AgentRequest, AgentResponse, AgentContext
from agentuity.io.email import Email
from openai import AsyncOpenAI
from resources.templates import templates
from utils.gmail import (
	authenticate_gmail,
	format_email_info,
	get_dmarc_attachment_content,
	get_unread_dmarc_emails,
	mark_as_read
)
from utils.slack import send_message
import gzip

client = AsyncOpenAI()
KV_NAME = "dmarc-reports"

async def run(request: AgentRequest, response: AgentResponse, context: AgentContext):
    """
    Entry point for processing DMARC reports and returning an analysis summary.
    """
    
    # Check for emails from request data
    email = await request.data.email()
    if email:
        print(f"email: {email}")
        context.logger.info('email subject: %s', email.subject)
        analysis = await generate_dmarc_report_from_email(email, context)
        summary = f"DMARC analysis complete: {analysis}"
        return response.json({"summary": summary})
    else:
        return response.text("No email found")

async def generate_dmarc_report_from_email(email: Email, context: AgentContext):
    """
    Processes an email and returns a summary of the DMARC report.
    """
    context.logger.info(f"Processing email with {len(email.attachments)} attachments")
    
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
            data = await attachment.data()
            content = await data.binary()
            # Handle different attachment formats (XML, gzipped XML, zip files)
            if attachment.filename.endswith('.xml'):
                xml_content = content.decode('utf-8')
                dmarc_contents.append(xml_content)
            elif attachment.filename.endswith('.xml.gz'):
                xml_content = gzip.decompress(content).decode('utf-8')
                dmarc_contents.append(xml_content)
            elif attachment.filename.endswith('.zip'):
                import zipfile
                import io
                with zipfile.ZipFile(io.BytesIO(content), 'r') as zip_file:
                    for file_name in zip_file.namelist():
                        if file_name.endswith('.xml'):
                            xml_content = zip_file.read(file_name).decode('utf-8')
                            dmarc_contents.append(xml_content)
                            
        except Exception as e:
            context.logger.error(f"Error processing attachment {attachment.filename}: {e}")
            continue
    
    if not dmarc_contents:
        context.logger.warning("No DMARC XML content found in email attachments")
        return "❌ No DMARC reports found in email attachments"
    
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
        return "❌ Unable to analyze DMARC reports - analysis failed"
    
    # Generate summary
    summary = await summarize_analysis(all_analyses, {"subject": email.subject, "from": email.from_email, "date": email.date})
    
    # Send to Slack if configured
    try:
        slack_to_dmarc_channel(summary)
    except Exception as e:
        context.logger.error(f"Failed to send to Slack: {e}")
    
    return summary

def slack_to_dmarc_channel(analysis):
    """
    Sends a DMARC analysis message to the configured Slack channel.
    
    Args:
        analysis: The analysis text to be posted to Slack.
    """
    slack_channel = os.getenv("DMARC_CHANNEL_ID")
    if not slack_channel:
        raise RuntimeError("Environment variable DMARC_CHANNEL_ID is not set")
    send_message(slack_channel, analysis)
    
async def analyze_dmarc_report(dmarc_report):
    """
    Analyzes a single DMARC report using an OpenAI GPT model.
    
    Args:
        dmarc_report: The DMARC XML report content to be analyzed.

    Returns:
        A string containing the GPT-generated analysis of the DMARC report.
    """
    template = templates["analyze-dmarc"]
    compiled_prompt = template.substitute(xml=dmarc_report)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": compiled_prompt}]
    )
    return response.choices[0].message.content

async def summarize_analysis(results, email):
    """
    Generates a concise summary of multiple DMARC analysis results using OpenAI GPT.
    
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
        model="gpt-4o",
        messages=[
            {"role": "user", "content": compiled_prompt}
        ]
    )
    return response.choices[0].message.content
