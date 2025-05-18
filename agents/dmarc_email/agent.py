from openai import AsyncOpenAI
from agentuity import AgentRequest, AgentResponse, AgentContext
from utils.gmail import fetch_emails, get_dmarc_attachment_content, authenticate_gmail, mark_as_read
from resources.templates import templates
from utils.slack import send_message
from utils.parser import parse_and_format_xml
import os

client = AsyncOpenAI()

async def run(request: AgentRequest, response: AgentResponse, context: AgentContext):
    analysis = await generate_dmarc_report(context)
    summary = f"Total DMARC reports analyzed: {len(analysis)}"
    return response.text(summary)

async def generate_dmarc_report(context: AgentContext):
    service = authenticate_gmail()
    emails = fetch_emails(service)
    
    dmarc_reports = {}
    
    for email in emails:
        contents = get_dmarc_attachment_content(service, email['id'])
        if not contents:
            context.logger.error(f"No DMARC report found for email {email['id']}")
            continue
        email_value = {
            'email': email,
            'dmarc_contents': contents}
        dmarc_reports[email['id']] = email_value
    
    if not dmarc_reports:
        return "No DMARC reports found"
    
    context.logger.info(f"Found {len(dmarc_reports)} DMARC reports to analyze")
    
    results = await analyze_dmarc_and_slack_result(dmarc_reports)
    await post_process_dmarc_emails(service, dmarc_reports, results, context)
    return results

async def post_process_dmarc_emails(service, dmarc_reports, analyses, context):
    """
    Post-process DMARC report emails after analysis:
    1. Store DMARC reports and their analyses in the database
    2. Mark processed emails as read to prevent reprocessing
    
    Args:
        service: Gmail API service instance
        dmarc_reports (dict): Dictionary mapping email IDs to their DMARC report contents
        analyses (list): List of analysis results for the DMARC reports
        context (AgentContext): Agent context for logging and database access
    
    Note:
        - Database storage implementation is left for manual implementation
        - Each email is marked as read only after successful database storage
        - Errors during processing are logged but don't stop the processing of other emails
    """
    for email_id in dmarc_reports:
        try:
            # TODO: Implement database storage logic here
            # Store both the DMARC report and its analysis
            # await store_dmarc_report(dmarc_reports[email_id], analyses, context)
            
            # After successful storage, mark email as read
            # mark_as_read(service, email_id)
            context.logger.info(f"Successfully processed and marked email {email_id} as read")
        except Exception as e:
            context.logger.error(f"Error processing email {email_id}: {e}")
            continue

async def analyze_dmarc_and_slack_result(dmarc_reports):
    "Analyze the DMARC reports for each email and send the results to Slack"
    for email_id, email_value in dmarc_reports.items():
        contents = email_value['dmarc_contents']
        all_analyses = []
        for xml_content in contents:
            try:
                formatted_report = parse_and_format_xml(xml_content)
                if formatted_report:
                    analysis = await analyze_dmarc_report(formatted_report)
                    all_analyses.append(analysis)
            except Exception as e:
                print(f"Error analyzing DMARC report: {e}")
                continue
        summary = await summarize_analysis(all_analyses)
        slack_dmarc_analysis(summary)
    return all_analyses

def slack_dmarc_analysis(analysis):
    "Send the DMARC analysis to Slack"
    slack_channel = os.getenv("DMARC_CHANNEL_ID")
    # Turn this on once its done testing
    # send_message(slack_channel, analysis)
    print("Yo Slack, I'm sending you a DMARC analysis")
    print(analysis)
    
async def analyze_dmarc_report(dmarc_report):
    "Analyze a single DMARC report"
    template = templates["analyze-dmarc"]
    compiled_prompt = template.substitute(xml=dmarc_report)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": compiled_prompt}]
    )
    return response.choices[0].message.content

async def summarize_analysis(results):
    """
    Summarize multiple DMARC analysis results into one concise report
    """
    template = templates["summarize-analysis"]
    compiled_prompt = template.substitute(analysis=results)
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
        result = await run(None, None, None)
        print(result)
        
    asyncio.run(main())