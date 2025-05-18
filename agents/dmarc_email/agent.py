from openai import AsyncOpenAI
from agentuity import AgentRequest, AgentResponse, AgentContext
from utils.gmail import get_unread_dmarc_emails, get_dmarc_attachment_content, authenticate_gmail, mark_as_read, format_email_info
from resources.templates import templates
from utils.slack import send_message
from utils.parser import parse_and_format_xml
import os

client = AsyncOpenAI()
KV_NAME = "dmarc-reports"

async def run(request: AgentRequest, response: AgentResponse, context: AgentContext):
    """
    Entry point for processing DMARC reports and returning an analysis summary.
    
    Triggers the DMARC report generation and analysis workflow using the provided agent context, then returns a summary message as a text response.
    """
    analysis = await generate_dmarc_report(context)
    summary = f"DMARC analysis complete: {analysis}"
    return response.text(summary)

async def generate_dmarc_report(context: AgentContext):
    """
    Fetches unread DMARC-related emails, extracts and analyzes DMARC reports, sends notifications for missing reports, and post-processes results.
    
    Retrieves unread emails containing DMARC reports, extracts report attachments, logs and notifies about emails lacking reports, analyzes valid reports, sends summaries to Slack, stores results, and marks processed emails as read. Returns the analysis results or a message if no reports are found.
    """
    service = authenticate_gmail()
    emails = get_unread_dmarc_emails(service)
    
    dmarc_reports = {}
    emails_without_dmarc = {}
    for email in emails:
        contents = get_dmarc_attachment_content(service, email['id'])
        if not contents:
            context.logger.error(f"No DMARC report found for email {email['id']}")
            emails_without_dmarc[email['id']] = email
            continue
        email_value = {
            'email': email,
            'dmarc_contents': contents}
        dmarc_reports[email['id']] = email_value
    
    if not dmarc_reports:
        return "No DMARC reports found"
    
    context.logger.info(f"Found {len(dmarc_reports)} DMARC reports to analyze")
    
    for email_id, email_data in emails_without_dmarc.items():
        formatted_email_info = format_email_info(email_data)
        context.logger.info(f"No DMARC report found for:\n{formatted_email_info}")
        slack_to_dmarc_channel(f"❌ No DMARC report found in the following email:\n{formatted_email_info}")
    
    results = await analyze_dmarc_and_slack_result(dmarc_reports, context)
    await post_process_dmarc_emails(service, results, context)
    return results

async def post_process_dmarc_emails(service, analyses, context: AgentContext):
    """
    Stores DMARC analysis results and marks corresponding emails as read.
    
    Iterates over analyzed email IDs, saving each analysis result to persistent storage and marking the associated email as read in Gmail. Errors during processing are logged, but do not interrupt processing of other emails.
    """
    for email_id in analyses:
        try:
            await context.kv.set(KV_NAME, f"email-id-{email_id}", analyses[email_id])
            mark_as_read(service, email_id)
            context.logger.info(f"Successfully processed and marked email {email_id} as read")
        except Exception as e:
            context.logger.error(
                f"Error processing email {email_id}: {e}",
                stack_info=True
            )
            continue

async def analyze_dmarc_and_slack_result(dmarc_reports, context: AgentContext):
    """
    Analyzes DMARC reports for each email, summarizes the results, and sends summaries to Slack.
    
    For each email, parses and analyzes all DMARC XML reports, aggregates the analyses into a summary, sends the summary to a Slack channel, and returns a dictionary mapping email IDs to their summaries.
    """
    results = {}
    for email_id, email_value in dmarc_reports.items():
        contents = email_value['dmarc_contents']
        email = email_value['email']
        all_analyses = []
        for xml_content in contents:
            try:
                formatted_report = parse_and_format_xml(xml_content)
                if formatted_report:
                    analysis = await analyze_dmarc_report(formatted_report)
                    all_analyses.append(analysis)
            except Exception as e:
                context.logger.error(f"Error analyzing DMARC report: {e}", stack_info=True)
                continue
        summary = await summarize_analysis(all_analyses, email)
        slack_to_dmarc_channel(summary)
        results[email_id] = summary
    return results

def slack_to_dmarc_channel(analysis):
    """
    Sends a DMARC analysis message to the configured Slack channel.
    
    Args:
        analysis: The analysis text to be posted to Slack.
    """
    slack_channel = os.getenv("DMARC_CHANNEL_ID")
    send_message(slack_channel, analysis)
    
async def analyze_dmarc_report(dmarc_report):
    """
    Analyzes a single DMARC report using an OpenAI GPT model.
    
    Substitutes the provided DMARC XML report into a predefined analysis prompt and sends it to the GPT-4o model for interpretation. Returns the generated analysis as a string.
    
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
    template = templates["summarize-analysis"]
    compiled_prompt = template.substitute(analysis=results, email=email)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": compiled_prompt}
        ]
    )
    return response.choices[0].message.content

if __name__ == "__main__":
    import asyncio
    
    async def main():
        """
        Runs the DMARC report processing pipeline and prints the result.
        
        This function serves as the entry point for standalone execution, invoking the main DMARC processing workflow and outputting the summary to standard output.
        """
        result = await run(None, None, None)
        print(result)
        
    asyncio.run(main())