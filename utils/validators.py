import defusedxml.ElementTree as ET
import json
from typing import Optional
from config import config

class ValidationError(Exception):
    """Raised when input validation fails"""
    pass

def validate_attachment_size(size_bytes: int, filename: str) -> None:
    """
    Validates attachment size is within configured limits.

    Args:
        size_bytes: Size of the attachment in bytes
        filename: Name of the attachment file

    Raises:
        ValidationError: If attachment exceeds size limit
    """
    max_bytes = config.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValidationError(
            f"Attachment '{filename}' size ({size_bytes / 1024 / 1024:.1f}MB) "
            f"exceeds limit ({config.MAX_ATTACHMENT_SIZE_MB}MB)"
        )

def validate_xml_structure(xml_content: str) -> None:
    """
    Validates XML is well-formed and appears to be a DMARC report.

    Args:
        xml_content: The XML content as a string

    Raises:
        ValidationError: If XML is malformed or doesn't look like a DMARC report
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        raise ValidationError(f"Invalid XML structure: {e}")

    # Check for DMARC report root element
    if root.tag != 'feedback':
        raise ValidationError(
            f"XML does not appear to be a DMARC report (root element is '{root.tag}', expected 'feedback')"
        )

    # Verify it has the basic DMARC structure
    if root.find('report_metadata') is None:
        raise ValidationError("XML missing required 'report_metadata' element")

def validate_gpt_response(response: str) -> Optional[dict]:
    """
    Validates and parses GPT JSON response.

    Args:
        response: The GPT response string (should be JSON)

    Returns:
        Parsed JSON dict if valid, None otherwise

    Raises:
        ValidationError: If response is invalid JSON or missing required fields
    """
    try:
        data = json.loads(response)
    except json.JSONDecodeError as e:
        raise ValidationError(f"GPT response is not valid JSON: {e}")

    # Check for special status responses (empty or not a DMARC report)
    if "status" in data:
        valid_statuses = ["empty", "not_dmarc_report"]
        if data["status"] not in valid_statuses:
            raise ValidationError(
                f"Invalid status value: {data['status']} (expected one of {valid_statuses})"
            )
        return data

    # Check for required keys in full DMARC analysis
    required_keys = ["summary", "failures", "remediation", "conclusion"]
    missing = [key for key in required_keys if key not in data]
    if missing:
        raise ValidationError(f"GPT response missing required keys: {missing}")

    return data
