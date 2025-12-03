from string import Template

analyze_dmarc_template = '''You are an expert in email authentication and DMARC analysis.

Given a DMARC aggregate report in XML format, analyze it and produce a JSON-structured summary.
The goal is to provide a concise analysis of the report -- specifically spot problems that are included
in the report.

If the report is empty, or is not a DMARC report, return an empty JSON object with the following structure:

{
    "status": "empty" | "not_dmarc_report"
}

Return ONLY valid JSON in this exact format:

{
    "summary": {
        "total_messages": number,
        "passing_messages": number,
        "failing_messages": number,
        "failure_details": string[],
        "other_issues": string[]
    },
    "failures": {
        "ips": [
            {
                "ip": string,
                "count": number,
                "spf_status": "pass" | "fail" | "neutral",
                "dkim_status": "pass" | "fail" | "neutral",
                "alignment": {
                    "dkim_aligned": boolean,
                    "spf_aligned": boolean
                },
                "from_domain": string
            }
        ]
    },
    "remediation": {
        "suggestions": string[],
        "priority": "low" | "medium" | "high"
    },
    "conclusion": {
        "status": "satisfactory" | "needs_attention" | "critical",
        "message": string
    }
}

Here is the DMARC report:

$xml
'''

summarize_analysis_template = '''You are a concise and accurate summarizer.

You will be given 1 or more DMARC analysis reports. Return human readable text summarizing the results.

Keep it short and concise when the report shows perfect results.

Otherwise, include some details about the issues found in the report.

If there are no issues, just say "DMARC report is healthy ❤️" for the summary.
If the report is critical, say "DMARC report is critical ❌" for the summary.

In the summary, please include the metadata of the email in a nice format.

The summary should be in the following format:
# Start of summary
[A brief, professional notification that a new DMARC report has been received and analyzed]

Subject: ...Subject of the email...
Date: ...Date of the email...

Summary: ...Summary of the DMARC report...
# End of summary

Here is the data to summarize:
Raw Analysis:
$analysis

The DMARC analysis above is for the email below (this contains email metadata like date, subject, and from address):
$email
'''

templates = {
    "analyze-dmarc": Template(analyze_dmarc_template),
    "summarize-analysis": Template(summarize_analysis_template)
}