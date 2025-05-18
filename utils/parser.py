import os
import glob
import parsedmarc
import json

def parse_dmarc_xml(file_path):
    """
    Parses a DMARC XML file from the specified path and returns the parsed data.
    
    Args:
        file_path: Path to the DMARC XML file.
    
    Returns:
        The parsed DMARC report data as returned by parsedmarc, or None if parsing fails.
    """
    try:
        parsed = parsedmarc.parse_report_file(file_path)
        return parsed
    except Exception as e:
        print(f"❌ Error parsing {file_path}: {e}")
        return None

def format_structure(parsed):
    """
    Transforms parsed DMARC report data into a structured dictionary for AI processing.
    
    Args:
        parsed: The parsed DMARC report data as returned by parsedmarc.
    
    Returns:
        A dictionary containing report metadata, published policy, and a list of
        formatted records with key DMARC fields extracted for each record.
    """
    report_data = parsed.get('report', {})
    
    formatted_records = []
    for record in report_data.get("records", []):
        source = record.get("source", {})
        identifiers = record.get("identifiers", {})
        policy = record.get("policy_evaluated", {})
        auth_results = record.get("auth_results", {})

        formatted_records.append({
            "source_ip": source.get("ip_address"),
            "source_country": source.get("country"),
            "source_domain": source.get("base_domain"),
            "source_name": source.get("name"),
            "source_type": source.get("type"),
            "count": record.get("count"),
            "header_from": identifiers.get("header_from"),
            "envelope_from": identifiers.get("envelope_from"),
            "envelope_to": identifiers.get("envelope_to"),
            "spf_result": policy.get("spf"),
            "dkim_result": policy.get("dkim"),
            "disposition": policy.get("disposition"),
            "spf_auth": auth_results.get("spf", []),
            "dkim_auth": auth_results.get("dkim", []),
            "alignment": record.get("alignment", {})
        })

    return {
        "report_metadata": report_data.get("report_metadata"),
        "policy_published": report_data.get("policy_published"),
        "records": formatted_records
    }

def parse_and_format_all(folder_path):
    """
    Parses and formats all DMARC XML files in a specified folder.
    
    Iterates through each `.xml` file in the given folder, parses the DMARC report, formats the parsed data, and returns a list of formatted report structures.
    
    Args:
        folder_path: Path to the folder containing DMARC XML files.
    
    Returns:
        A list of dictionaries, each representing a formatted DMARC report.
    """
    all_formatted = []
    for xml_file in glob.glob(os.path.join(folder_path, "*.xml")):
        parsed = parse_dmarc_xml(xml_file)
        if parsed:
            formatted = format_structure(parsed)
            all_formatted.append(formatted)
    return all_formatted

def parse_and_format_xml(xml_string):
    """
    Parses a DMARC XML string and returns a structured summary.
    
    Args:
        xml_string: The DMARC XML content as a string.
    
    Returns:
        A dictionary containing formatted report metadata, published policy, and records.
    """
    parsed = parsedmarc.parse_report_file(xml_string)
    return format_structure(parsed)

def main():
    """
    Processes all DMARC XML files in the 'resources/examples' folder and writes the formatted results to 'dmarc_ai_input.json'.
    
    Iterates through each XML file in the specified folder, parses and formats the DMARC reports, and saves the aggregated output as a JSON file. Prints a confirmation message upon successful completion.
    """
    folder_path = "resources/examples" 
    all_reports = parse_and_format_all(folder_path)

    with open("dmarc_ai_input.json", "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2)

    print("✅ Parsed and formatted all reports. Saved to dmarc_ai_input.json.")

if __name__ == "__main__":
    main()
