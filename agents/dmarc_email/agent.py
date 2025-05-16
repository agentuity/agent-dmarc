from openai import AsyncOpenAI
from agentuity import AgentRequest, AgentResponse, AgentContext
from utils.gmail import fetch_emails, get_dmarc_attachment_content, authenticate_gmail
from resources.templates import templates

client = AsyncOpenAI()

async def run(request: AgentRequest, response: AgentResponse, context: AgentContext):
    report_summary = await get_dmarc_reports(context)
    return response.text(report_summary)

async def get_dmarc_reports(context: AgentContext):
    service = authenticate_gmail()
    emails = fetch_emails(service)
    dmarc_reports = []
    
    for email in emails:
        content = get_dmarc_attachment_content(service, email['id'])
        if not content:
            context.logger.error(f"No DMARC report found for email {email['id']}")
            continue
        dmarc_reports.append(content)
    
    if not dmarc_reports:
        return "No DMARC reports found"
        
    dmarc_analysis = await analyze_dmarc(dmarc_reports)
    summary = await summarize_analysis(dmarc_analysis)
    return summary

async def analyze_dmarc(dmarc_reports):
    """
    Analyze the DMARC reports and return a list of analysis results
    """
    analysis = []
    for dmarc_report in dmarc_reports:
        template = templates["analyze-dmarc"]
        compiled_prompt = template.format(xml=dmarc_report)
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "user", "content": compiled_prompt}
            ]
        )
        analysis.append(response.choices[0].message.content)
    return analysis

async def summarize_analysis(analysis):
    """
    Summarize the DMARC analysis results into one concise report
    """
    template = templates["summarize-analysis"]
    compiled_prompt = template.format(analysis=analysis)
    response = await client.chat.completions.create(
        model="gpt-4",
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