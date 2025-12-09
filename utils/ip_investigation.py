"""
IP Investigation Utilities for DMARC Analysis

This module provides functionality to:
1. Extract failed IPs from DMARC XML reports
2. Score IP risk based on authentication failures
3. Invoke the IP analyzer agent in parallel with timeout
4. Manage whitelist of known-good IP sources
"""

import asyncio
import json
import defusedxml.ElementTree as ET
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from agentuity import AgentContext
from agentuity.server.data import Data, StringStreamReader
from openai import AsyncOpenAI

# OpenAI client for parsing IP analysis results
openai_client = AsyncOpenAI()


@dataclass
class IPRecord:
    """Represents an IP address record from DMARC report with authentication results"""
    ip: str
    count: int
    spf_result: str  # pass, fail, neutral, etc.
    dkim_result: str  # pass, fail, neutral, etc.
    spf_aligned: bool
    dkim_aligned: bool
    disposition: str  # none, quarantine, reject
    source_domain: str  # The domain that sent the email


@dataclass
class IPInvestigationResult:
    """Result from IP analyzer agent investigation"""
    ip: str
    summary: str  # Short summary (1-2 sentences)
    risk_level: str  # critical, high, medium, low
    recommendation: str  # block, monitor, ignore
    full_analysis: str  # Complete analysis text
    error: Optional[str] = None  # Error if investigation failed


def extract_failed_ips_from_xml(xml_content: str) -> List[IPRecord]:
    """
    Extract IP addresses with authentication failures from DMARC XML report.

    Args:
        xml_content: DMARC report XML string

    Returns:
        List of IPRecord objects for IPs with failures
    """
    try:
        root = ET.fromstring(xml_content)
        failed_ips = []

        # Iterate through all record elements
        for record in root.findall(".//record"):
            # Extract IP address
            source_ip_elem = record.find(".//source_ip")
            if source_ip_elem is None or not source_ip_elem.text:
                continue

            ip = source_ip_elem.text.strip()

            # Extract count
            count_elem = record.find(".//count")
            count = int(count_elem.text) if count_elem is not None else 1

            # Extract authentication results
            auth_results = record.find(".//auth_results")
            if auth_results is None:
                continue

            # SPF result
            spf_elem = auth_results.find(".//spf/result")
            spf_result = spf_elem.text if spf_elem is not None else "unknown"

            # DKIM result
            dkim_elem = auth_results.find(".//dkim/result")
            dkim_result = dkim_elem.text if dkim_elem is not None else "unknown"

            # Check alignment
            spf_aligned = spf_result == "pass"
            dkim_aligned = dkim_result == "pass"

            # Extract disposition
            policy_eval = record.find(".//policy_evaluated")
            disposition_elem = policy_eval.find(".//disposition") if policy_eval is not None else None
            disposition = disposition_elem.text if disposition_elem is not None else "none"

            # Extract identifiers (from domain)
            identifiers = record.find(".//identifiers")
            header_from = identifiers.find(".//header_from") if identifiers is not None else None
            source_domain = header_from.text if header_from is not None else "unknown"

            # Only include IPs with failures (either SPF or DKIM failed)
            if spf_result != "pass" or dkim_result != "pass":
                failed_ips.append(IPRecord(
                    ip=ip,
                    count=count,
                    spf_result=spf_result,
                    dkim_result=dkim_result,
                    spf_aligned=spf_aligned,
                    dkim_aligned=dkim_aligned,
                    disposition=disposition,
                    source_domain=source_domain
                ))

        return failed_ips

    except Exception as e:
        # If XML parsing fails, return empty list
        # Errors are logged by the caller
        return []


def calculate_risk_score(record: IPRecord) -> int:
    """
    Calculate risk score (0-100) for an IP based on authentication failures.

    Higher scores indicate higher risk.

    Scoring factors:
    - Both SPF and DKIM fail: +50 points (likely spoofing)
    - Only one fails: +25 points (misconfiguration or forwarding)
    - Disposition (quarantine/reject): +20 points (already blocked)
    - High message count (>10): +15 points (systematic abuse)
    - Medium count (5-10): +10 points

    Args:
        record: IPRecord to score

    Returns:
        Risk score from 0-100
    """
    score = 0

    # Both authentication methods failed (highest risk)
    if record.spf_result == "fail" and record.dkim_result == "fail":
        score += 50
    # Only one failed (medium risk - could be forwarding or misconfiguration)
    elif record.spf_result == "fail" or record.dkim_result == "fail":
        score += 25

    # Disposition already triggered protective action
    if record.disposition in ["quarantine", "reject"]:
        score += 20

    # High volume indicates systematic abuse
    if record.count > 10:
        score += 15
    elif record.count >= 5:
        score += 10

    return min(score, 100)  # Cap at 100


def filter_high_risk_ips(
    failed_ips: List[IPRecord],
    max_ips: int,
    min_risk_score: int
) -> Tuple[List[IPRecord], bool]:
    """
    Filter failed IPs to identify high-risk ones worth investigating.

    Args:
        failed_ips: List of all failed IP records
        max_ips: Maximum number of IPs to investigate
        min_risk_score: Minimum risk score to investigate

    Returns:
        Tuple of (high_risk_ips, excessive_failures_flag)
        - high_risk_ips: List of IPRecord objects to investigate
        - excessive_failures_flag: True if there are more failures than normal
    """
    # Calculate risk score for each IP
    scored_ips = [(record, calculate_risk_score(record)) for record in failed_ips]

    # Sort by risk score (descending)
    scored_ips.sort(key=lambda x: x[1], reverse=True)

    # Filter by minimum risk score
    high_risk = [record for record, score in scored_ips if score >= min_risk_score]

    # Check for excessive failures
    excessive_failures = len(failed_ips) > max_ips

    # Limit to max_ips
    high_risk = high_risk[:max_ips]

    return high_risk, excessive_failures


async def investigate_ip_with_agent(
    ip: str,
    context: AgentContext,
    timeout: float = 60.0
) -> IPInvestigationResult:
    """
    Investigate a single IP address using the IP analyzer agent.

    The IP analyzer returns plain text analysis, which is then parsed using
    GPT-4o-mini to extract structured fields (risk_level, recommendation, summary).

    Args:
        ip: IP address to investigate
        context: Agentuity agent context
        timeout: Timeout in seconds (default 60)

    Returns:
        IPInvestigationResult with analysis
    """
    try:
        # Get the IP analyzer agent
        agent = context.get_agent({"name": "ip-analyzer"})

        # Create data payload with the investigation request
        data = Data(
            "text/plain",
            StringStreamReader(f"Investigate {ip} and assess if it seems suspicious")
        )

        # Invoke agent with timeout
        result = await asyncio.wait_for(
            agent.run(data),
            timeout=timeout
        )

        # Extract response text
        full_analysis = await result.data.text()

        # Parse the analysis using GPT-4o-mini to extract structured data
        parsed_data = await parse_ip_analysis_with_llm(full_analysis)

        return IPInvestigationResult(
            ip=ip,
            summary=parsed_data.get("summary", "Analysis completed"),
            risk_level=parsed_data.get("risk_level", "medium"),
            recommendation=parsed_data.get("recommendation", "monitor"),
            full_analysis=full_analysis,
            error=None
        )

    except asyncio.TimeoutError:
        return IPInvestigationResult(
            ip=ip,
            summary=f"Investigation timed out after {timeout}s",
            risk_level="unknown",
            recommendation="monitor",
            full_analysis="",
            error=f"Timeout after {timeout} seconds"
        )
    except Exception as e:
        return IPInvestigationResult(
            ip=ip,
            summary=f"Investigation failed: {str(e)}",
            risk_level="unknown",
            recommendation="monitor",
            full_analysis="",
            error=str(e)
        )


async def parse_ip_analysis_with_llm(analysis_text: str) -> dict:
    """
    Parse IP analysis text using GPT-4o-mini to extract structured data.

    This replaces the previous heuristic-based keyword matching with a robust
    LLM-based approach. Cost: ~$0.000165 per IP (~$0.003 for 20 IPs).

    Args:
        analysis_text: The full text analysis from IP analyzer agent

    Returns:
        Dictionary with:
        - risk_level: "critical", "high", "medium", "low", or "unknown"
        - recommendation: "block", "monitor", or "ignore"
        - summary: Brief one-sentence summary (max 150 chars)
    """
    try:
        prompt = f"""Extract the following information from this IP investigation analysis:

1. risk_level: Classify as "critical", "high", "medium", "low", or "unknown"
   - critical: Confirmed malicious activity, immediate threat
   - high: Strong indicators of suspicious activity
   - medium: Some concerns but unclear
   - low: Legitimate infrastructure or normal activity
   - unknown: Insufficient information

2. recommendation: What action to take - "block", "monitor", or "ignore"
   - block: IP should be blocked immediately
   - monitor: Watch for suspicious activity
   - ignore: No action needed, legitimate traffic

3. summary: One clear sentence (max 150 characters) summarizing the key finding

IP Analysis:
{analysis_text}

Return ONLY valid JSON with exactly these three fields. No additional text."""

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,  # Low temperature for consistent parsing
            max_tokens=150,   # We only need a small response
        )

        parsed = json.loads(response.choices[0].message.content)

        # Validate and normalize the response
        risk_level = parsed.get("risk_level", "medium").lower()
        if risk_level not in ["critical", "high", "medium", "low", "unknown"]:
            risk_level = "medium"

        recommendation = parsed.get("recommendation", "monitor").lower()
        if recommendation not in ["block", "monitor", "ignore"]:
            recommendation = "monitor"

        summary = parsed.get("summary", "Analysis completed")[:150]

        return {
            "risk_level": risk_level,
            "recommendation": recommendation,
            "summary": summary
        }

    except json.JSONDecodeError as e:
        # If JSON parsing fails, return safe defaults
        return {
            "risk_level": "medium",
            "recommendation": "monitor",
            "summary": "Unable to parse analysis results"
        }
    except Exception as e:
        # For any other errors, return safe defaults
        return {
            "risk_level": "medium",
            "recommendation": "monitor",
            "summary": f"Error parsing analysis: {str(e)[:100]}"
        }


async def investigate_ips_parallel(
    ip_records: List[IPRecord],
    context: AgentContext,
    timeout: float = 60.0
) -> Dict[str, IPInvestigationResult]:
    """
    Investigate multiple IPs in parallel using the IP analyzer agent.

    Args:
        ip_records: List of IPRecord objects to investigate
        context: Agentuity agent context
        timeout: Timeout per IP investigation (default 60s)

    Returns:
        Dictionary mapping IP address to IPInvestigationResult
    """
    # Create investigation tasks for all IPs
    tasks = [
        investigate_ip_with_agent(record.ip, context, timeout)
        for record in ip_records
    ]

    # Run all investigations in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Build result dictionary
    investigation_results = {}
    for i, result in enumerate(results):
        ip = ip_records[i].ip

        if isinstance(result, Exception):
            # Handle exceptions from gather
            investigation_results[ip] = IPInvestigationResult(
                ip=ip,
                summary=f"Investigation failed: {str(result)}",
                risk_level="unknown",
                recommendation="monitor",
                full_analysis="",
                error=str(result)
            )
        else:
            investigation_results[ip] = result

    return investigation_results


async def filter_and_investigate_ips(
    dmarc_xml: str,
    context: AgentContext,
    max_ips: int,
    timeout: float,
    min_risk_score: int
) -> Tuple[Dict[str, IPInvestigationResult], bool, int]:
    """
    Complete workflow: Extract IPs, filter high-risk, and investigate in parallel.

    Args:
        dmarc_xml: DMARC XML report content
        context: Agentuity agent context
        max_ips: Maximum number of IPs to investigate
        timeout: Timeout per IP investigation
        min_risk_score: Minimum risk score to investigate

    Returns:
        Tuple of (investigation_results, excessive_failures_flag, total_failed_ips)
    """
    # Step 1: Extract failed IPs from DMARC XML
    failed_ips = extract_failed_ips_from_xml(dmarc_xml)
    total_failed_ips = len(failed_ips)

    context.logger.info(f"Extracted {total_failed_ips} failed IPs from DMARC report")

    if not failed_ips:
        return {}, False, 0

    # Step 2: Filter high-risk IPs
    high_risk_ips, excessive_failures = filter_high_risk_ips(
        failed_ips,
        max_ips=max_ips,
        min_risk_score=min_risk_score
    )

    context.logger.info(
        f"Identified {len(high_risk_ips)} high-risk IPs to investigate "
        f"(excessive_failures={excessive_failures})"
    )

    if not high_risk_ips:
        context.logger.info("No high-risk IPs found, skipping investigation")
        return {}, excessive_failures, total_failed_ips

    # Step 3: Investigate IPs in parallel
    context.logger.info(f"Starting parallel IP investigation for {len(high_risk_ips)} IPs...")
    investigation_results = await investigate_ips_parallel(
        high_risk_ips,
        context,
        timeout=timeout
    )

    context.logger.info(f"Completed IP investigation for {len(investigation_results)} IPs")

    return investigation_results, excessive_failures, total_failed_ips
