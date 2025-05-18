from string import Template

analyze_dmarc_template = '''You are an expert in email authentication and DMARC analysis.

Given a DMARC aggregate report in JSON format, analyze it and produce a JSON-structured summary.
The goal is to provide a concise analysis of the report -- specifically spot problems that are included
in the report.

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

You will be given 1 or more DMARC analysis reports. Return ONLY valid JSON in this exact format:

{
    "analysis_summary": {
        "total_reports": number,
        "reports_with_issues": number,
        "failure_details": string[],
        "health_status": "good" | "needs_attention" | "critical",
        "timestamp": string  // ISO-8601 format
    },
    "metrics": {
        "success_rate": number,  // 0-1 ratio
        "health_score": number   // 0-100 score
    }
}

Raw Analysis:
$analysis
'''

templates = {
    "analyze-dmarc": Template(analyze_dmarc_template),
    "summarize-analysis": Template(summarize_analysis_template)
}