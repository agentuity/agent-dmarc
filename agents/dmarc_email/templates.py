templates = {
    "analyze-dmarc": """You are an expert in email authentication and DMARC analysis.

Given a DMARC aggregate report in XML format, analyze it and generate a summary report:

1. If **any message fails** DMARC (due to SPF or DKIM failure, or misalignment with the header `From` domain):
   - Highlight the issues clearly
   - List offending IPs, failing authentication methods, and whether alignment failed
   - Suggest possible remediation steps (e.g., updating SPF/DKIM records, fixing alignment, etc.)

2. If **no issues are found**, generate a **short, simple summary** confirming all messages passed DMARC with proper alignment.

Use bullet points or clear formatting for readability.

Use green tick emoji for passing and red X emoji for failing as visual indicator.

Here is the DMARC report:

{xml}
""",
    "summarize-analysis": """
    You are a concise and accurate summarizer.

    You are given a list of DMARC analysis results.

    Your job is to summarize the DMARC analysis results in a concise manner.

    {analysis}
    """
}