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

analyze_dmarc_with_ip_context_template = '''You are an expert in email authentication and DMARC analysis.

Given a DMARC aggregate report in XML format AND IP investigation results for suspicious IPs,
analyze it and produce a JSON-structured summary that incorporates the IP intelligence.

The IP investigation results provide critical context about whether failed IPs are:
- Legitimate infrastructure with misconfigurations (LOW RISK - ignore or monitor)
- Suspicious sources that could be spoofing (HIGH RISK - block)
- Known good services with forwarding issues (LOW RISK - ignore)

Use the IP context to make ACTIONABLE recommendations in your analysis.

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
                "from_domain": string,
                "risk_assessment": {
                    "level": "critical" | "high" | "medium" | "low" | "unknown",
                    "summary": string,
                    "recommendation": "block" | "monitor" | "ignore"
                }
            }
        ]
    },
    "remediation": {
        "suggestions": string[],
        "priority": "low" | "medium" | "high" | "critical"
    },
    "conclusion": {
        "status": "satisfactory" | "needs_attention" | "critical",
        "message": string
    }
}

Here is the DMARC report:

$xml

IP Investigation Results (for high-risk IPs):

$ip_investigations

Use the IP investigation context to enrich your analysis and provide specific, actionable recommendations.
'''

summarize_analysis_with_ip_template = '''You are a concise and accurate summarizer specializing in security analysis.

You will be given 1 or more DMARC analysis reports with IP investigation context.
Return human readable text summarizing the results in a format suitable for Slack notification.

The summary should be ACTIONABLE - employees should know exactly what to do (if anything).

Format the summary with clear sections and use emojis for visual clarity:
- 🔴 for CRITICAL issues (require immediate action)
- 🟡 for MEDIUM risk (monitor)
- 🟢 for LOW risk (no action needed)

Structure:
1. Brief header with overall status
2. Email metadata (subject, date, from)
3. Overview stats (passed/failed messages)
4. Critical issues section (if any) - with specific IPs and actions
5. Medium risk section (if any) - with monitoring suggestions
6. Low risk section (if any) - brief note
7. Recommendations section - numbered list of actions

If there are no issues, keep it short: "DMARC report is healthy ❤️"
If critical issues exist, lead with: "🚨 CRITICAL: DMARC report requires immediate attention"

Here is the data to summarize:
Raw Analysis:
$analysis

The DMARC analysis above is for the email below (this contains email metadata like date, subject, and from address):
$email
'''

templates = {
    "analyze-dmarc": Template(analyze_dmarc_template),
    "analyze-dmarc-with-ip-context": Template(analyze_dmarc_with_ip_context_template),
    "summarize-analysis": Template(summarize_analysis_template),
    "summarize-analysis-with-ip": Template(summarize_analysis_with_ip_template)
}